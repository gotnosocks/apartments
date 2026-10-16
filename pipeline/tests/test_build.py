import hashlib
import importlib.util
import json
import os
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
def build(monkeypatch, tmp_path):
    """`build.build` from ops/pipeline, with the environment it sets restored afterwards and an
    empty corrections ledger."""
    (tmp_path / "ledger").mkdir()
    monkeypatch.setenv("PIPELINE_EXPORT", "")
    monkeypatch.setenv("PIPELINE_STATE", "")
    monkeypatch.setenv("PIPELINE_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setenv("PIPELINE_MEMORY", "1GB")
    return load("build", BUILD).build


def test_build_writes_hashed_files_and_a_catalog_line(tmp_path, build):
    export = copy_export(tmp_path)
    first = build(export, tmp_path / "state", tmp_path / "out")
    frames = {}
    for stem, key, model in (
        ("rows", "rows", "analysis.rows"),
        ("ads", "ads_file", "analysis.ads"),
    ):
        path = tmp_path / "out" / first[key]["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == first[key]["sha256"]
        assert path.name == f"{stem}-{first[key]['sha256'][:16]}.parquet"
        frame = frames[stem] = pd.read_parquet(path)
        assert len(frame) == first[key]["rows"] == first["models"][model]["rows"]
        assert frame.listing_id.is_monotonic_increasing
    assert frames["ads"].listing_id.is_unique
    assert set(frames["ads"].listing_id[frames["ads"].in_rows]) == set(
        frames["rows"].listing_id
    )
    assert first["ads"]["files"] == {
        str(path.relative_to(export)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (export / "ads").glob("*/*.parquet")
    }
    city = Path(os.environ["PIPELINE_CITY"])
    assert first["city"] == {
        "archive": str(city),
        "files": {
            str(path.relative_to(city)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in city.glob("*/*.*")
        },
    }
    assert all(model["seconds"] is not None for model in first["models"].values())
    # A second build from the same export rebuilds nothing and writes the same file.
    second = build(export, tmp_path / "state", tmp_path / "out")
    assert second["rows"] == first["rows"] and second["ads_file"] == first["ads_file"]
    assert all(model["seconds"] is None for model in second["models"].values())
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        first["ads_file"]["path"],
        "catalog.ndjson",
        first["rows"]["path"],
    ]
    catalog = (tmp_path / "out" / "catalog.ndjson").read_text().splitlines()
    assert [json.loads(line) for line in catalog] == [first, second]


def test_topup_build_equals_a_full_build(tmp_path, build):
    """Building runs 2 and 3, then adding run 4, writes the same rows file and ads file as
    building runs 2 to 4 into an empty state."""
    export = copy_export(tmp_path, keep=lambda line: line["run"] < 4)
    build(export, tmp_path / "state", tmp_path / "out")
    shutil.copy(FIXTURE / "export" / "manifest.ndjson", export / "manifest.ndjson")
    topup = build(export, tmp_path / "state", tmp_path / "out")
    full = build(export, tmp_path / "fresh", tmp_path / "out-fresh")
    assert topup["rows"] == full["rows"] and topup["ads_file"] == full["ads_file"]
    assert topup["ads"] == full["ads"] and topup["buildings"] == full["buildings"]
    assert {name: m["rows"] for name, m in topup["models"].items()} == {
        name: m["rows"] for name, m in full["models"].items()
    }


def test_failed_audit_writes_nothing(tmp_path, build):
    """An export file repeating an answer fails the audit of ads.answers. The build stops, and
    OUT keeps only the first build's files and catalog line."""
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
    assert sorted(before) == [
        first["ads_file"]["path"],
        "catalog.ndjson",
        first["rows"]["path"],
    ]
    after = {path.name: path.read_bytes() for path in (tmp_path / "out").iterdir()}
    assert after == before


def test_failed_janitor_warns(tmp_path, build, monkeypatch, capsys):
    """The janitor raises after the build writes its files and catalog line. They stay in place,
    and the build returns its line with a warning on stderr."""
    import sqlmesh

    def fail(self, ignore_ttl):
        raise RuntimeError("planted")

    monkeypatch.setattr(sqlmesh.Context, "run_janitor", fail)
    line = build(copy_export(tmp_path), tmp_path / "state", tmp_path / "out")
    assert (tmp_path / "out" / line["rows"]["path"]).exists()
    assert (tmp_path / "out" / line["ads_file"]["path"]).exists()
    catalog = (tmp_path / "out" / "catalog.ndjson").read_text().splitlines()
    assert [json.loads(entry) for entry in catalog] == [line]
    assert "janitor failed: planted" in capsys.readouterr().err
