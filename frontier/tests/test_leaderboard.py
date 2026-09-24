import json

import numpy as np
import pytest
from rentfrontier import leaderboard


def heldout(folder, ids, lpd):
    folder.mkdir(parents=True)
    np.savez(folder / "heldout.npz", audit_id=np.array(ids, dtype=object), lpd=lpd)


def test_paired_refuses_differing_row_sets(tmp_path):
    heldout(tmp_path / "a", ["r1", "r2", "r3"], np.array([1.0, 2.0, 3.0]))
    heldout(tmp_path / "b", ["r1", "r2"], np.array([0.5, 1.0]))
    with pytest.raises(ValueError, match="Held-out rows differ"):
        leaderboard.paired(tmp_path / "a", tmp_path / "b")


def test_paired_refuses_duplicate_audit_ids(tmp_path):
    heldout(tmp_path / "a", ["r1", "r1", "r2"], np.array([1.0, 2.0, 3.0]))
    heldout(tmp_path / "b", ["r1", "r2"], np.array([0.5, 1.0]))
    with pytest.raises(ValueError, match="Duplicate"):
        leaderboard.paired(tmp_path / "a", tmp_path / "b")


def test_paired_sums_differences_on_identical_rows(tmp_path):
    heldout(tmp_path / "a", ["r1", "r2", "r3"], np.array([1.0, 2.0, 4.0]))
    heldout(tmp_path / "b", ["r3", "r1", "r2"], np.array([3.0, 0.0, 1.0]))
    delta, se = leaderboard.paired(tmp_path / "a", tmp_path / "b")
    assert delta == pytest.approx(3.0)
    assert se == pytest.approx(0.0)


def screen(root, name, split, lpd, rhat, seconds=60.0):
    folder = root / "feature-screen-x" / name
    heldout(folder, ["r1", "r2", "r3"], lpd)
    result = {
        "method": "nuts",
        "split": split,
        "seconds": seconds,
        "heldout": {"elpd": float(lpd.sum()), "elpd_se": 1.0},
        "diagnostics": {"max_rhat": rhat, "min_ess_bulk": 1000.0, "divergences": 0},
    }
    (folder / "result.json").write_text(json.dumps(result))


def test_screens_group_by_split_and_grade_by_gate(tmp_path, monkeypatch):
    refs = {
        "rows": tmp_path / "feature-screen-x" / "nuts-hwalk" / "heldout.npz",
        "units": tmp_path / "feature-screen-x" / "nuts-hwalk-units" / "heldout.npz",
    }
    screen(tmp_path, "nuts-hwalk", "rows", np.zeros(3), 1.0)
    screen(tmp_path, "nuts-hwalk-units", "units", np.zeros(3), 1.0)
    screen(tmp_path, "good-rows", "rows", np.ones(3), 1.005)
    screen(tmp_path, "good-units", "units", np.full(3, 2.0), 1.005)
    screen(tmp_path, "rough-rows", "rows", np.ones(3), 1.2)
    monkeypatch.setattr(leaderboard, "SCREENS", tmp_path)
    monkeypatch.setattr(leaderboard, "REFERENCES", refs)
    entries = {e["id"]: e for e in leaderboard.screen_entries()}
    assert set(entries) == {"pymc/good", "pymc/rough"}  # references excluded
    good, rough = entries["pymc/good"], entries["pymc/rough"]
    assert set(good["splits"]) == {"rows", "units"}
    assert good["splits"]["rows"]["delta"] == pytest.approx(3.0)
    assert good["splits"]["units"]["delta"] == pytest.approx(6.0)
    assert good["grade"] == "full" and good["passes_checks"]
    assert rough["grade"] == "screen" and not rough["passes_checks"]
    assert good["hardware"] == "thelio CPU" and good["commit"] is None
    assert not good["commits_differ"]


def test_annotations_are_listed_without_changing_scores(tmp_path, monkeypatch):
    path = tmp_path / "annotations.json"
    path.write_text(
        json.dumps({"entries": {"m/x@abc": ["fit on an H100"]}, "footer": ["foot"]})
    )
    monkeypatch.setattr(leaderboard, "ANNOTATIONS", path)
    a = leaderboard.load_annotations()
    split = {
        "delta": 5.0,
        "delta_se": 1.0,
        "elpd": 10.0,
        "max_rhat": 1.001,
        "min_ess": 1000,
        "group_rhat_max": 1.01,
    }
    entry = {
        "id": "m/x@abc",
        "line": "frontier",
        "model": {"name": "m"},
        "feature_set": "x",
        "splits": {"rows": split},
        "fit_seconds": 10.0,
        "cost_usd": 0.0,
        "hardware": "local",
        "grade": "full",
        "interpretable": True,
        "current_best": True,
        "frontier": True,
        "note": "",
        "annotations": a["entries"]["m/x@abc"],
    }
    other = {**entry, "id": "m/y@abc", "annotations": [], "current_best": False}
    md = leaderboard.markdown(
        {
            "entries": [entry, other],
            "footer": a["footer"],
            "promoted": leaderboard.PROMOTED,
        }
    )
    assert "| see [1] |" in md
    assert "- [1] `m/x@abc`:\n  - fit on an H100" in md
    assert "[2]" not in md
    assert md.rstrip().endswith("foot")
    monkeypatch.setattr(leaderboard, "ANNOTATIONS", tmp_path / "missing.json")
    assert leaderboard.load_annotations() == {"entries": {}, "footer": []}
