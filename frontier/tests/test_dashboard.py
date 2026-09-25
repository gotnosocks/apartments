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


def pointwise(folder, elpd, mcse=0.01):
    folder.mkdir(parents=True)
    np.savez(
        folder / "pointwise.npz",
        audit_id=np.array([f"t{i}" for i in range(len(elpd))], dtype=object),
        elpd_loo=np.asarray(elpd, float),
        mcse=np.full(len(elpd), mcse),
    )
    return str(folder)


def entry(tmp_path, name, delta, fit, landed, passes=True, units=None, noise=None):
    per_row = np.full(50, delta / 50) + (noise if noise is not None else 0.0)
    splits = {
        "rows": {
            "run": f"{name}-rows",
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
        "hardware_class": "gpu",
        "line": "frontier",
        "interpretable": True,
        "passes_checks": passes,
        "fit_seconds": fit,
        "splits": splits,
        "psis": {"delta": delta, "_dir": pointwise(tmp_path / name / "loo", per_row)},
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
    # A failing unit-split fit fails the entry; fit time stays the scored fit's.
    assert not late["passes_checks"] and late["fit_seconds"] == 60.0


def test_snapshots_replay_the_board_rules_over_time(tmp_path):
    slow_good = entry(tmp_path, "slow", 300.0, 3000.0, at(1))
    fast_ok = entry(tmp_path, "fast", 100.0, 100.0, at(2))
    better = entry(tmp_path, "better", 600.0, 2000.0, at(3))
    failing = entry(tmp_path, "failing", 900.0, 50.0, at(4), passes=False)
    entries = dashboard.assign_keys([slow_good, fast_ok, better, failing])
    snaps = dashboard.snapshots(entries)
    assert [s["by_class"]["gpu"]["best"] for s in snaps] == [
        "slow",
        "slow",
        "better",
        "better",
    ]
    assert sorted(snaps[1]["by_class"]["gpu"]["frontier"]) == ["fast", "slow"]
    # "better" is faster and more accurate than "slow": slow leaves the frontier.
    assert sorted(snaps[2]["by_class"]["gpu"]["frontier"]) == ["better", "fast"]
    # A gate-failing entry never joins the frontier or becomes best.
    assert (
        "failing" not in snaps[3]["by_class"]["gpu"]["frontier"]
        and snaps[3]["by_class"]["gpu"]["entries"] == 4
    )


def test_shared_ids_get_unique_keys_and_snapshots_use_them(tmp_path):
    first = entry(tmp_path, "m6", 400.0, 1800.0, at(1), passes=False)
    solo = entry(tmp_path, "m6-solo-dir", 400.0, 2400.0, at(2), passes=True)
    solo["id"] = first["id"] = "m6/base@abc"
    first["splits"]["rows"]["run"] = "m6-rows-abc"
    solo["splits"]["rows"]["run"] = "m6-rows-abc-solo"
    dashboard.assign_keys([first, solo])
    assert first["_key"] == "m6/base@abc [m6-rows-abc]"
    assert solo["_key"] == "m6/base@abc [m6-rows-abc-solo]"
    snaps = dashboard.snapshots([first, solo])
    # Only the passing rerun is best and on the frontier, never its twin.
    assert snaps[-1]["by_class"]["gpu"]["best"] == solo["_key"]
    assert snaps[-1]["by_class"]["gpu"]["frontier"] == [solo["_key"]]


def test_parse_pr_only_takes_a_trailing_pr_number():
    assert dashboard.parse_pr("Land the board (#8)") == ("Land the board", 8)
    assert dashboard.parse_pr("x (#12) (follow-up)") is None
    assert dashboard.parse_pr("Plain commit") is None


def test_completed_at_rules(tmp_path):
    import json
    import os

    run = tmp_path / "run"
    run.mkdir()
    (run / "result.json").write_text(
        json.dumps(
            {
                "started_at": "2026-09-23T15:00:00+0000",
                "seconds": {"prepare": 10.0, "fit_total": 50.0},
            }
        )
    )
    assert dashboard.completed_at({"_dir": run}) == dt.datetime(
        2026, 9, 23, 15, 1, tzinfo=dt.UTC
    )
    screen = tmp_path / "screen"
    screen.mkdir()
    (screen / "result.json").write_text("{}")
    (screen / "remote-run.json").write_text(
        json.dumps({"result": {"finished_at": "2026-09-24T07:00:00Z"}})
    )
    assert dashboard.completed_at({"_dir": screen}) == dt.datetime(
        2026, 9, 24, 7, tzinfo=dt.UTC
    )
    local = tmp_path / "local"
    local.mkdir()
    (local / "result.json").write_text("{}")
    os.utime(local / "result.json", (1_790_000_000, 1_790_000_000))
    assert dashboard.completed_at({"_dir": local}).timestamp() == 1_790_000_000


def test_best_is_the_fastest_entry_tied_with_the_top_score(tmp_path):
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 0.5, 50)
    top = entry(tmp_path, "top", 600.0, 3000.0, at(1), noise=noise)
    tied_fast = entry(tmp_path, "tied", 590.0, 1000.0, at(2), noise=-noise)
    far = entry(tmp_path, "far", 100.0, 10.0, at(3))
    entries = dashboard.assign_keys([top, tied_fast, far])
    snaps = dashboard.snapshots(entries)
    # 590 is within two combined SE of 600 (noise makes the paired SE ~7), so
    # the faster one is best; 100 is far outside and never ties.
    assert (
        snaps[1]["by_class"]["gpu"]["best"] == "tied"
        and snaps[2]["by_class"]["gpu"]["best"] == "tied"
    )
    assert sorted(snaps[2]["by_class"]["gpu"]["frontier"]) == ["far", "tied", "top"]


def test_frontier_and_best_are_per_hardware_class(tmp_path):
    gpu = entry(tmp_path, "gpu-slow", 600.0, 3000.0, at(1))
    cpu = entry(tmp_path, "cpu-fast", 100.0, 60.0, at(2))
    cpu["hardware_class"] = "cpu"
    snaps = dashboard.snapshots(dashboard.assign_keys([gpu, cpu]))
    last = snaps[-1]["by_class"]
    # Each class has its own frontier: the fast CPU entry does not knock the
    # slow GPU entry off the GPU frontier, and vice versa.
    assert last["gpu"]["frontier"] == ["gpu-slow"] and last["gpu"]["best"] == "gpu-slow"
    assert last["cpu"]["frontier"] == ["cpu-fast"] and last["cpu"]["best"] == "cpu-fast"


def test_ladder_rungs_share_the_structure_of_their_gibbs_design():
    def e(design, line, features="base-v1"):
        return {"model": {"name": design}, "line": line, "feature_set": features}

    assert dashboard.structure(e("L6-units", "pymc")) == "m0q/base-v1"
    assert dashboard.structure(e("L6-units", "numpyro")) == "m0q/base-v1"
    assert dashboard.structure(e("m0q", "frontier")) == "m0q/base-v1"
    assert dashboard.structure(e("L2-trend", "pymc", "none")) == "L2-trend/none"
    # A Gibbs design named like a rung is not remapped.
    assert dashboard.structure(e("m1q", "frontier", "desc-v1")) == "m1q/desc-v1"
