import json
import os
import sys

import pandas as pd
import pytest

from rentfrontier import data, kit, rentmap, step_key


@pytest.fixture
def run_dir(tmp_path):
    run = tmp_path / "runs" / "r"
    run.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps({"run": "r"}))
    (run / "posterior.npz").write_bytes(b"draws")
    return run


@pytest.fixture
def summary_dir(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "complete.json").write_text(json.dumps({"run": "r"}))
    return bundle


def test_file_sha256_is_kept_until_the_file_changes(tmp_path):
    path, cache = tmp_path / "f", tmp_path / "cache"
    path.write_bytes(b"one")
    assert step_key.file_sha256(path, cache) == data.sha256(path)
    (entry,) = cache.iterdir()
    record = json.loads(entry.read_text())
    entry.write_text(json.dumps(record | {"sha256": "kept"}))
    assert step_key.file_sha256(path, cache) == "kept"
    path.write_bytes(b"two!")
    os.utime(path, ns=(1, 1))
    assert step_key.file_sha256(path, cache) == data.sha256(path)


def test_sources_cover_every_loaded_module():
    found = step_key.sources()
    for name, module in list(sys.modules.items()):
        if name.startswith("rentfrontier.") and getattr(module, "__file__", None):
            relative = os.path.relpath(module.__file__, step_key.PACKAGE)
            assert relative in found, name
    assert "uv.lock" in found


def test_the_key_follows_every_input(run_dir, summary_dir, tmp_path):
    cache = tmp_path / "cache"

    def digest(step="kit", options=None):
        record = step_key.inputs(step, run_dir, summary_dir, options or {}, cache)
        return step_key.key(record)

    first = digest()
    assert digest() == first
    assert digest(step="rentmap") != first
    assert digest(options={"draws": 250}) != first
    (summary_dir / "design-parts.npz").write_bytes(b"parts")
    with_parts = digest()
    assert with_parts != first
    (run_dir / "posterior.npz").write_bytes(b"other draws")
    assert digest() != with_parts


def test_recorded_refuses_an_output_of_another_key(tmp_path):
    path = tmp_path / "complete.json"
    assert not step_key.recorded(path, "abc")
    path.write_text(json.dumps({"key": "abc"}))
    assert step_key.recorded(path, "abc")
    with pytest.raises(SystemExit):
        step_key.recorded(path, "abd")


@pytest.fixture
def steps(monkeypatch, run_dir, tmp_path):
    monkeypatch.setattr(step_key, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(kit, "KITS", tmp_path / "kits")
    monkeypatch.setattr(rentmap, "MAPS", tmp_path / "maps")
    monkeypatch.setattr(kit.draws, "run", lambda name: (run_dir, {}))
    for module in (kit, rentmap):
        monkeypatch.setattr(
            module, "git", lambda *a: "" if a[0] == "status" else "c" * 40
        )
    return tmp_path


def test_the_kit_is_made_once_per_key(steps, summary_dir, monkeypatch):
    record = {"run": "r", "period": "2026-10", "summary_sha256": "s", "draws": 2}
    buildings = pd.DataFrame({"building_id": ["b"], "level": [1.0]})
    units = pd.DataFrame({"unit_id": ["u"], "level": [0.5]})
    made = []

    def build(run, summary, allow_failing):
        made.append(run)
        return record, buildings, units

    monkeypatch.setattr(kit, "build_kit", build)
    argv = ["r", "--summary", str(summary_dir)]
    kit.main(argv)
    (out,) = (steps / "kits").iterdir()
    complete = json.loads((out / "complete.json").read_text())
    assert out.name == f"r-{complete['key'][:7]}"
    assert complete["key"] == step_key.key(complete["key_inputs"])
    assert complete["key_inputs"]["options"] == {"allow_failing": False}

    complete["created_at"] = "2026-01-01T00:00:00+00:00"
    (out / "complete.json").write_text(json.dumps(complete))
    kit.main(argv)
    assert made == ["r"]
    kept = json.loads((out / "complete.json").read_text())
    assert kept["built_at"] == "2026-01-01T00:00:00+00:00"
    assert kept["created_at"] > kept["built_at"]

    kit.main([*argv, "--allow-failing"])
    assert made == ["r", "r"]
    assert len(list((steps / "kits").iterdir())) == 2


def test_the_rent_map_is_made_once_per_key(steps, summary_dir, monkeypatch):
    made = []

    def compute(run, summary, keep):
        made.append(keep)
        return {"run": run}

    monkeypatch.setattr(rentmap, "compute", compute)
    argv = ["r", "--summary", str(summary_dir)]
    rentmap.main(argv)
    (path,) = (steps / "maps").glob("*/map.json")
    out = json.loads(path.read_text())
    assert path.parent.name == f"r-{out['key'][:7]}"
    assert out["key"] == step_key.key(out["key_inputs"])

    os.utime(path, ns=(1, 1))
    rentmap.main(argv)
    assert made == [kit.DRAWS]
    assert path.stat().st_mtime_ns > 1

    rentmap.main([*argv, "--draws", "0"])
    assert made == [kit.DRAWS, None]
