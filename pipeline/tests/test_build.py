import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import duckdb
import pandas as pd
import pytest

FIXTURE = Path(__file__).resolve().parent / "fixture"
BUILD = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "build.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of test_pipeline.py load the same way.
helpers = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py"))
copy_export, append_answers = helpers.copy_export, helpers.append_answers


@pytest.fixture
def build(monkeypatch):
    """`build.build` from ops/pipeline, with the environment it sets restored afterwards."""
    monkeypatch.setenv("PIPELINE_EXPORT", "")
    monkeypatch.setenv("PIPELINE_STATE", "")
    monkeypatch.setenv("PIPELINE_MEMORY", "1GB")
    return load("build", BUILD).build


def test_build_writes_hashed_rows_and_a_catalog_line(tmp_path, build):
    export = copy_export(tmp_path)
    first = build(export, tmp_path / "state", tmp_path / "out")
    rows = tmp_path / "out" / first["rows"]["path"]
    assert hashlib.sha256(rows.read_bytes()).hexdigest() == first["rows"]["sha256"]
    assert rows.name == f"rows-{first['rows']['sha256'][:16]}.parquet"
    frame = pd.read_parquet(rows)
    assert (
        len(frame) == first["rows"]["rows"] == first["models"]["analysis.rows"]["rows"]
    )
    assert frame.listing_id.is_monotonic_increasing
    assert first["ads"]["files"] == {
        str(path.relative_to(export)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (export / "ads").glob("*/*.parquet")
    }
    assert all(model["seconds"] is not None for model in first["models"].values())
    # A second build from the same export rebuilds nothing and writes the same file.
    second = build(export, tmp_path / "state", tmp_path / "out")
    assert second["rows"] == first["rows"]
    assert all(model["seconds"] is None for model in second["models"].values())
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        "catalog.ndjson",
        rows.name,
    ]
    catalog = (tmp_path / "out" / "catalog.ndjson").read_text().splitlines()
    assert [json.loads(line) for line in catalog] == [first, second]


def test_topup_build_equals_a_full_build(tmp_path, build):
    """Building runs 2 and 3, then adding run 4, writes the same rows file as building runs 2
    to 4 into an empty state."""
    export = copy_export(tmp_path, keep=lambda line: line["run"] < 4)
    build(export, tmp_path / "state", tmp_path / "out")
    shutil.copy(FIXTURE / "export" / "manifest.ndjson", export / "manifest.ndjson")
    topup = build(export, tmp_path / "state", tmp_path / "out")
    full = build(export, tmp_path / "fresh", tmp_path / "out-fresh")
    assert topup["rows"] == full["rows"]
    assert topup["ads"] == full["ads"] and topup["buildings"] == full["buildings"]
    assert {name: m["rows"] for name, m in topup["models"].items()} == {
        name: m["rows"] for name, m in full["models"].items()
    }


def test_failed_audit_writes_nothing(tmp_path, build):
    """An export file repeating an answer fails the audit of ads.answers. The build stops, and
    OUT keeps only the first build's rows file and catalog line."""
    export = copy_export(tmp_path)
    first = build(export, tmp_path / "state", tmp_path / "out")
    before = {path.name: path.read_bytes() for path in (tmp_path / "out").iterdir()}
    repeated = (
        duckdb.connect(config={"TimeZone": "UTC"})
        .execute(
            "SELECT * FROM read_parquet(?) ORDER BY response_id LIMIT 1",
            [str(FIXTURE / "export/ads/run-0002/*.parquet")],
        )
        .df()
    )
    append_answers(export, repeated)
    with pytest.raises(SystemExit, match="build stopped"):
        build(export, tmp_path / "state", tmp_path / "out")
    assert sorted(before) == ["catalog.ndjson", first["rows"]["path"]]
    after = {path.name: path.read_bytes() for path in (tmp_path / "out").iterdir()}
    assert after == before
