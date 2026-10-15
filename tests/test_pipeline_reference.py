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
    digest = reference.sha256(source)
    first = reference.blob(str(source), digest, expected=digest)
    again = reference.blob(str(source), digest, expected="0" * 64)
    stored = reference.ROOT / "blobs" / first["sha256"]
    assert stored.read_text() == source.read_text()
    assert stored.stat().st_mode & 0o222 == 0
    assert first["matches_record"] and not again["matches_record"]
    assert "matches_record" not in reference.blob(str(source), digest)
    assert sorted(p.name for p in stored.parent.iterdir()) == [first["sha256"]]


def test_blob_stops_on_a_changed_file(reference, tmp_path, monkeypatch):
    source = tmp_path / "rules.jsonl"
    source.write_text("read\n")
    read = reference.sha256(source)
    source.write_text("edited after the read\n")
    with pytest.raises(SystemExit, match="changed after the preparation read it"):
        reference.blob(str(source), read)

    def copy(src, dst):
        Path(dst).write_text("edited during the copy\n")

    monkeypatch.setattr(reference.shutil, "copyfile", copy)
    with pytest.raises(SystemExit, match="changed while it was copied"):
        reference.blob(str(source), reference.sha256(source))
    assert not list((reference.ROOT / "blobs").glob("[0-9a-f]*[0-9a-f]"))


def test_freeze_compares_with_the_record(reference, tmp_path, monkeypatch):
    observations = tmp_path / "observations.jsonl"
    observations.write_text("{}\n")
    rule = tmp_path / "quarantine.jsonl"
    rule.write_text("[]\n")
    read = {
        "observations": observations,
        "rule quarantine-v1": rule,
    }

    def child(argv, **kw):
        (Path(argv[-1]) / "rows.parquet").write_bytes(b"rows")
        prepared = {
            "rows_sha256": "rows",
            "rows": 1,
            "heldout": 0,
            "inputs": {
                role: {"path": str(path), "sha256": reference.sha256(path)}
                for role, path in read.items()
            },
            "seconds": 0.1,
        }
        return types.SimpleNamespace(
            returncode=0, stdout=json.dumps(prepared) + "\n", stderr=""
        )

    monkeypatch.setattr(reference, "tree", lambda commit: tmp_path)
    monkeypatch.setattr(reference.subprocess, "run", child)
    record = {
        "name": "fit",
        "rows_sha256": "rows",
        "dataset_observations_sha256": reference.sha256(observations),
        "data_rule_sources": {"quarantine-v1": {"sha256": reference.sha256(rule)}},
        "feature_sources": {},
    }

    def freeze(name, record):
        reference.freeze(name, {"commit": "c", "dataset": str(tmp_path)}, record)
        return json.loads((reference.ROOT / name / "manifest.json").read_text())

    matched = freeze("matched", record)
    assert matched["rows_sha256_matches_run"] and matched["inputs_match_run"]
    assert matched["inputs"]["rule quarantine-v1"]["matches_record"]
    unrecorded = freeze("unrecorded", {**record, "data_rule_sources": {}})
    assert not unrecorded["inputs_match_run"]
    assert "matches_record" not in unrecorded["inputs"]["rule quarantine-v1"]
    unread = {"basemap": {"sha256": "0" * 64}}
    assert not freeze("unread", {**record, "feature_sources": unread})[
        "inputs_match_run"
    ]
    other_rows = freeze("other-rows", {**record, "rows_sha256": "other"})
    assert not other_rows["rows_sha256_matches_run"]
    assert other_rows["inputs_match_run"]
    assert "run" not in freeze("spec", None)


def test_verify_reports_a_changed_output(reference, tmp_path, capsys):
    source = tmp_path / "observations.jsonl"
    source.write_text("{}\n")
    out = reference.ROOT / "ref"
    out.mkdir(parents=True)
    rows = out / "rows.parquet"
    rows.write_bytes(b"rows")
    manifest = {
        "inputs": {
            "observations": reference.blob(str(source), reference.sha256(source))
        },
        "outputs": {"rows.parquet": {"sha256": reference.sha256(rows)}},
    }
    (out / "manifest.json").write_text(json.dumps(manifest))
    assert reference.verify("ref") == 0
    rows.write_bytes(b"rows, edited")
    assert reference.verify("ref") == 1
    assert "rows.parquet changed" in capsys.readouterr().out


def steps(monkeypatch, prepare):
    def build(name, frame, train):
        values = np.column_stack([frame.a, frame["b"]]).astype(float)
        return types.SimpleNamespace(names=("a", "b"), values=values)

    package = types.ModuleType("rentfrontier")
    package.features = types.SimpleNamespace(build=build)
    package.model = types.SimpleNamespace(prepare=prepare)
    monkeypatch.setitem(sys.modules, "rentfrontier", package)


def test_traced_columns(reference, monkeypatch):
    def prepare(frame, heldout, feats):
        return types.SimpleNamespace(
            sizes=frame.groupby("c").size().to_numpy(), x=feats.values[~heldout]
        )

    steps(monkeypatch, prepare)
    getitem = pd.DataFrame.__getitem__
    frame = pd.DataFrame(
        {"audit_id": ["p", "q"], "a": [1, 2], "b": [3, 4], "c": ["x", "y"], "d": [0, 0]}
    )
    frozen = pd.DataFrame({"audit_id": ["p", "q"], "a": [1.0, 2.0], "b": [3.0, 4.0]})
    out = reference.traced_columns(
        frame, np.array([False, True]), {"features": "set"}, frozen
    )
    assert out == {
        "features.build": ["a", "b"],
        "model.prepare": ["c"],
        "unread": ["audit_id", "d"],
        "same_as_frozen": True,
        "same_without_unread": True,
    }
    assert pd.DataFrame.__getitem__ is getitem
    frozen.loc[1, "b"] = 5.0
    out = reference.traced_columns(
        frame, np.array([False, True]), {"features": "set"}, frozen
    )
    assert not out["same_as_frozen"]


def test_traced_columns_finds_an_unnoted_read(reference, monkeypatch):
    def prepare(frame, heldout, feats):
        # A read through the column index escapes the patches.
        return types.SimpleNamespace(offset=1.0 if "d" in frame.columns else 0.0)

    steps(monkeypatch, prepare)
    frame = pd.DataFrame({"a": [1, 2], "b": [3, 4], "d": [0, 0]})
    out = reference.traced_columns(frame, np.array([False, True]), {"features": "set"})
    assert out["unread"] == ["d"]
    assert out["same_without_unread"] is False
