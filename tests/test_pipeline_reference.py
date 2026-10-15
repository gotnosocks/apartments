import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "pipeline" / "reference.py"


@pytest.fixture
def reference(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("pipeline_reference", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path / "reference")
    return module


def test_blob_copies_once_read_only(reference, tmp_path):
    source = tmp_path / "rules.jsonl"
    source.write_text('{"audit_id": "a"}\n')
    first = reference.blob(str(source), expected=reference.sha256(source))
    again = reference.blob(str(source), expected="0" * 64)
    stored = reference.ROOT / "blobs" / first["sha256"]
    assert stored.read_text() == source.read_text()
    assert stored.stat().st_mode & 0o222 == 0
    assert first["matches_record"] and not again["matches_record"]
    assert sorted(p.name for p in stored.parent.iterdir()) == [first["sha256"]]


def test_verify_reports_a_changed_output(reference, tmp_path, capsys):
    source = tmp_path / "observations.jsonl"
    source.write_text("{}\n")
    out = reference.ROOT / "ref"
    out.mkdir(parents=True)
    rows = out / "rows.parquet"
    rows.write_bytes(b"rows")
    manifest = {
        "inputs": {"observations": reference.blob(str(source))},
        "outputs": {"rows.parquet": {"sha256": reference.sha256(rows)}},
    }
    (out / "manifest.json").write_text(json.dumps(manifest))
    assert reference.verify("ref") == 0
    rows.write_bytes(b"rows, edited")
    assert reference.verify("ref") == 1
    assert "rows.parquet changed" in capsys.readouterr().out


def test_traced_columns(reference, monkeypatch):
    def build(name, frame, train):
        values = np.column_stack([frame.a, frame["b"]]).astype(float)
        return types.SimpleNamespace(names=("a", "b"), values=values)

    def prepare(frame, heldout, feats):
        frame.groupby("c").size()

    package = types.ModuleType("rentfrontier")
    package.features = types.SimpleNamespace(build=build)
    package.model = types.SimpleNamespace(prepare=prepare)
    monkeypatch.setitem(sys.modules, "rentfrontier", package)
    getitem = pd.DataFrame.__getitem__
    frame = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": ["x", "y"], "d": [0, 0]})
    out = reference.traced_columns(frame, np.array([False, True]), {"features": "set"})
    assert out == {
        "features.build": ["a", "b"],
        "model.prepare": ["c"],
        "unread": ["d"],
        "same_without_unread": True,
    }
    assert pd.DataFrame.__getitem__ is getitem
