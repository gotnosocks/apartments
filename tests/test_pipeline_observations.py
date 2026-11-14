"""`ops/pipeline/observations.py` copies the build's catalog line into its manifest.

The dataset folder records the stale days and the label rule the build ran with, so a fit on a
`unit-labels-v18` build can be told apart from one on the default `unit-labels-v17`.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

OBSERVATIONS = (
    Path(__file__).resolve().parents[1] / "ops" / "pipeline" / "observations.py"
)


def observations():
    spec = importlib.util.spec_from_file_location("pipeline_observations", OBSERVATIONS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def catalog_line(folder: Path, name: str, label_rule: str | None) -> dict:
    rows = folder / f"{name}-rows.parquet"
    ads = folder / f"{name}-ads.parquet"
    rows.write_bytes(f"rows of {name}".encode())
    ads.write_bytes(f"ads of {name}".encode())
    line = {
        "built": "2026-11-14T12:00:00+00:00",
        "code": {"commit": name, "clean": True},
        "stale_days": 30,
        "rows": {
            "path": rows.name,
            "sha256": hashlib.sha256(rows.read_bytes()).hexdigest(),
        },
        "ads_file": {
            "path": ads.name,
            "sha256": hashlib.sha256(ads.read_bytes()).hexdigest(),
        },
    }
    if label_rule is not None:
        line["label_rule"] = label_rule
    return line


@pytest.fixture
def catalog(tmp_path):
    lines = [
        catalog_line(tmp_path, "old", None),
        catalog_line(tmp_path, "new", "unit-labels-v18"),
    ]
    text = "".join(json.dumps(line) + "\n" for line in lines)
    (tmp_path / "catalog.ndjson").write_text(text)
    return tmp_path


def test_manifest_carries_the_label_rule(catalog):
    files = observations().pick_build(catalog, None, None)
    assert files["catalog"]["label_rule"] == "unit-labels-v18"
    assert files["catalog"]["stale_days"] == 30
    assert files["rows"]["path"] == str((catalog / "new-rows.parquet").resolve())


def test_line_without_a_label_rule_gives_none(catalog):
    files = observations().pick_build(catalog, catalog / "old-rows.parquet", None)
    assert files["catalog"]["label_rule"] is None
    assert files["catalog"]["code"]["commit"] == "old"
