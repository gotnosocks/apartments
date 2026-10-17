import pandas as pd

from rentfrontier import data, design


def _setup(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "pkg").mkdir()
    (repo / "config" / "rules.jsonl").write_text("a\n")
    (repo / "pkg" / "mod.py").write_text("x = 1\n")
    monkeypatch.setattr(data, "REPO", repo)
    monkeypatch.setattr(design, "PACKAGE", repo / "pkg")
    monkeypatch.setattr(data, "OUTPUT_ROOT", tmp_path / "out")
    calls = []

    def build(frame, split, rules, feature_set):
        calls.append(feature_set)
        return frame, [False], feature_set, {"n": len(calls)}

    monkeypatch.setattr(design, "_build", build)
    frame = pd.DataFrame({"a": [1]})
    frame.attrs["source_sha256"] = "abc"
    return repo, frame, calls


def test_design_cache_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("FRONTIER_DESIGN_CACHE", raising=False)
    _, frame, calls = _setup(monkeypatch, tmp_path)
    design.prepared(frame, "rows", (), "f1")
    design.prepared(frame, "rows", (), "f1")
    assert calls == ["f1", "f1"]
    assert not (tmp_path / "out").exists()


def test_design_cache_reads_until_an_input_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "1")
    repo, frame, calls = _setup(monkeypatch, tmp_path)
    first = design.prepared(frame, "rows", ("r1",), "f1")
    again = design.prepared(frame, "rows", ("r1",), "f1")
    assert calls == ["f1"]
    assert again[3] == first[3] and again[0].attrs == frame.attrs
    design.prepared(frame, "rows", ("r1",), "f2")
    design.prepared(frame, "rows", ("r2",), "f1")
    design.prepared(frame, "latest", ("r1",), "f1")
    assert len(calls) == 4
    (repo / "config" / "rules.jsonl").write_text("b\n")
    design.prepared(frame, "rows", ("r1",), "f1")
    (repo / "pkg" / "mod.py").write_text("x = 2\n")
    design.prepared(frame, "rows", ("r1",), "f1")
    other = frame.copy()
    other.attrs["source_sha256"] = "def"
    design.prepared(other, "rows", ("r1",), "f1")
    assert len(calls) == 7
    assert not list((tmp_path / "out" / "cache").glob("*.tmp"))


def test_a_fit_and_its_summary_come_to_the_same_key(monkeypatch, tmp_path):
    _, frame, _ = _setup(monkeypatch, tmp_path)
    for k in list(design.os.environ):
        if k.startswith("FRONTIER_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("FRONTIER_DATASET", "/d")
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "1")
    on_modal = design._key(frame, "rows", ("r1",), "f1")
    # The summary unit on thelio sets the output root and the range flags.
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "read")
    monkeypatch.setenv("FRONTIER_OUTPUT_ROOT", str(data.OUTPUT_ROOT))
    monkeypatch.setenv("FRONTIER_RANGE_ATOMS", "1")
    monkeypatch.setenv("FRONTIER_COMMIT", "abc")
    assert design._key(frame, "rows", ("r1",), "f1") == on_modal
    monkeypatch.setenv("FRONTIER_DESCRIPTIONS", "/other")
    assert design._key(frame, "rows", ("r1",), "f1") != on_modal
    monkeypatch.delenv("FRONTIER_DESCRIPTIONS")
    monkeypatch.setattr(data, "OUTPUT_ROOT", tmp_path / "elsewhere")
    assert design._key(frame, "rows", ("r1",), "f1") != on_modal


def test_a_read_only_cache_loads_a_saved_design_and_writes_none(monkeypatch, tmp_path):
    _, frame, calls = _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "read")
    design.prepared(frame, "rows", (), "f1")
    assert calls == ["f1"] and not (tmp_path / "out").exists()
    # A pickle in cache/ is a container's own; read mode loads only from designs/.
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "1")
    first = design.prepared(frame, "rows", (), "f1")
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "read")
    design.prepared(frame, "rows", (), "f1")
    assert calls == ["f1", "f1", "f1"]
    (pkl,) = (tmp_path / "out" / "cache").glob("design-*.pkl")
    saved = tmp_path / "out" / "designs" / pkl.name
    saved.parent.mkdir()
    pkl.rename(saved)
    assert design.prepared(frame, "rows", (), "f1")[3] == first[3]
    assert len(calls) == 3
    # A pickle this environment can't load is rebuilt, not raised.
    saved.write_bytes(b"not a pickle")
    design.prepared(frame, "rows", (), "f1")
    assert len(calls) == 4
    assert [p.name for p in saved.parent.iterdir()] == [saved.name]


def test_preparing_a_runs_design_keeps_the_pickle_its_summary_loads(
    monkeypatch, tmp_path, capsys
):
    import json

    import pytest

    from rentfrontier import run

    _, frame, calls = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    (tmp_path / "runs" / "r").mkdir(parents=True)
    result = {
        "dataset": str(tmp_path / "ds"),
        "dataset_observations_sha256": "abc",
        "split": "rows",
        "feature_set": "f1",
    }
    (tmp_path / "runs" / "r" / "result.json").write_text(json.dumps(result))
    loaded = []
    monkeypatch.setattr(data, "load", lambda path: loaded.append(path) or frame)
    monkeypatch.setattr(data, "recorded_rules", lambda result: ())
    monkeypatch.delenv("FRONTIER_DESIGN_CACHE", raising=False)
    with pytest.raises(SystemExit, match="FRONTIER_DESIGN_CACHE=1"):
        design.main(["r"])
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "1")
    design.main(["r"])
    record = json.loads(capsys.readouterr().out)
    assert loaded == [tmp_path / "ds"] and calls == ["f1"]
    # The summary, reading from designs/, finds it under the same name.
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "read")
    (tmp_path / "out" / "designs").mkdir()
    (tmp_path / "out" / "cache" / record["design"]).rename(
        tmp_path / "out" / "designs" / record["design"]
    )
    design.prepared(frame, "rows", (), "f1")
    assert calls == ["f1"]
    frame.attrs["source_sha256"] = "other"
    monkeypatch.setenv("FRONTIER_DESIGN_CACHE", "1")
    with pytest.raises(SystemExit, match="dataset differs"):
        design.main(["r"])
