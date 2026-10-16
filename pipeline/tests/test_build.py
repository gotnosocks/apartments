import importlib.util
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

FIXTURE = Path(__file__).resolve().parent / "fixture"
BUILD = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "build.py"


@pytest.fixture
def build(monkeypatch):
    """`build.build` from ops/pipeline, with the environment it sets restored afterwards."""
    monkeypatch.setenv("PIPELINE_EXPORT", "")
    monkeypatch.setenv("PIPELINE_STATE", "")
    monkeypatch.setenv("PIPELINE_MEMORY", "1GB")
    spec = importlib.util.spec_from_file_location("build", BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build


def export_with(tmp_path, keep):
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "export", export)
    lines = (export / "manifest.ndjson").read_text().splitlines(keepends=True)
    (export / "manifest.ndjson").write_text(
        "".join(line for line in lines if keep(json.loads(line)))
    )
    return export


def test_build_writes_hashed_rows_and_a_catalog_line(tmp_path, build):
    export = export_with(tmp_path, keep=lambda line: True)
    first = build(export, tmp_path / "state", tmp_path / "out")
    rows = tmp_path / "out" / first["rows"]["path"]
    assert rows.name == f"rows-{first['rows']['sha256'][:16]}.parquet"
    frame = pd.read_parquet(rows)
    assert (
        len(frame) == first["rows"]["rows"] == first["models"]["analysis.rows"]["rows"]
    )
    assert frame.listing_id.is_monotonic_increasing
    assert set(first["ads"]["files"]) == {
        str(path.relative_to(export)) for path in (export / "ads").glob("*/*.parquet")
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
    export = export_with(tmp_path, keep=lambda line: line["run"] < 4)
    build(export, tmp_path / "state", tmp_path / "out")
    shutil.copy(FIXTURE / "export" / "manifest.ndjson", export / "manifest.ndjson")
    topup = build(export, tmp_path / "state", tmp_path / "out")
    full = build(export, tmp_path / "fresh", tmp_path / "out-fresh")
    assert topup["rows"] == full["rows"]
    assert topup["ads"] == full["ads"] and topup["buildings"] == full["buildings"]
    assert {name: m["rows"] for name, m in topup["models"].items()} == {
        name: m["rows"] for name, m in full["models"].items()
    }
