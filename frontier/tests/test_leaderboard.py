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
