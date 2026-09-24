import datetime as dt

import numpy as np
from rentfrontier import dashboard


def at(hour):
    return dt.datetime(2026, 9, 23, hour, tzinfo=dt.UTC)


def heldout(folder, lpd):
    folder.mkdir(parents=True)
    np.savez(
        folder / "heldout.npz",
        audit_id=np.array([f"r{i}" for i in range(len(lpd))], dtype=object),
        lpd=np.asarray(lpd, float),
    )
    return str(folder)


def entry(tmp_path, name, delta, fit, landed, passes=True, units=None):
    splits = {
        "rows": {
            "delta": delta,
            "fit_seconds": fit,
            "passes": passes,
            "_at": landed,
            "_dir": heldout(
                tmp_path / name / "rows", np.full(50, delta / 50) + np.arange(50) * 1e-3
            ),
        }
    }
    if units is not None:
        u_delta, u_landed = units
        splits["units"] = {
            "delta": u_delta,
            "fit_seconds": fit,
            "passes": passes,
            "_at": u_landed,
            "_dir": heldout(tmp_path / name / "units", np.full(50, u_delta / 50)),
        }
    return {
        "id": name,
        "line": "frontier",
        "interpretable": True,
        "passes_checks": passes,
        "fit_seconds": fit,
        "splits": splits,
    }


def test_as_of_counts_entries_from_their_row_result_and_only_landed_splits(tmp_path):
    e = entry(tmp_path, "a", 100.0, 60.0, at(1), passes=True, units=(50.0, at(3)))
    e["splits"]["units"]["passes"] = False
    e["splits"]["units"]["fit_seconds"] = 900.0
    assert dashboard.as_of([e], at(0)) == []
    (early,) = dashboard.as_of([e], at(2))
    assert set(early["splits"]) == {"rows"} and early["passes_checks"]
    assert early["fit_seconds"] == 60.0
    (late,) = dashboard.as_of([e], at(4))
    assert not late["passes_checks"] and late["fit_seconds"] == 900.0


def test_snapshots_replay_the_board_rules_over_time(tmp_path):
    slow_good = entry(tmp_path, "slow", 300.0, 3000.0, at(1))
    fast_ok = entry(tmp_path, "fast", 100.0, 100.0, at(2))
    better = entry(tmp_path, "better", 600.0, 2000.0, at(3))
    failing = entry(tmp_path, "failing", 900.0, 50.0, at(4), passes=False)
    snaps = dashboard.snapshots([slow_good, fast_ok, better, failing])
    assert [s["best"] for s in snaps] == ["slow", "slow", "better", "better"]
    assert sorted(snaps[1]["frontier"]) == ["fast", "slow"]
    # "better" is faster and more accurate than "slow": slow leaves the frontier.
    assert sorted(snaps[2]["frontier"]) == ["better", "fast"]
    # A gate-failing entry never joins the frontier or becomes best.
    assert "failing" not in snaps[3]["frontier"] and snaps[3]["entries"] == 4
