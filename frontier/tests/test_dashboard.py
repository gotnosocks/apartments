import datetime as dt
import json

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


def test_snapshots_keep_a_frontier_per_tier(tmp_path):
    slow_full = entry(tmp_path, "full", 300.0, 3000.0, at(1))
    quick = entry(tmp_path, "quick", 400.0, 600.0, at(2))
    quick["tier"] = {"name": "exploration"}
    entries = dashboard.assign_keys([slow_full, quick])
    (_, last) = dashboard.snapshots(entries)
    gpu = last["by_class"]["gpu"]
    # The exploration fit beats the full fit on the one board, yet the full
    # fit still heads its own tier's frontier.
    assert gpu["frontier"] == ["quick"]
    assert gpu["frontier_by_tier"] == {"exploration": ["quick"], "full": ["full"]}


def test_the_exploration_line_counts_unconverged_fits(tmp_path):
    slow_full = entry(tmp_path, "full", 300.0, 3000.0, at(1))
    failing_full = entry(tmp_path, "ffull", 500.0, 2000.0, at(1), passes=False)
    quick = entry(tmp_path, "quick", 400.0, 600.0, at(2), passes=False)
    quick["tier"] = {"name": "exploration"}
    entries = dashboard.assign_keys([slow_full, failing_full, quick])
    gpu = dashboard.snapshots(entries)[-1]["by_class"]["gpu"]
    # Ben, 2026-10-05: unconverged exploration fits are on their line; the
    # full line keeps the gate, and the board-wide frontier is unchanged.
    assert gpu["frontier_by_tier"] == {"exploration": ["quick"], "full": ["full"]}
    assert gpu["frontier"] == ["full"]
    assert quick["passes_checks"] is False


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


def test_sizes_of_reads_the_rows_fits_record(tmp_path):
    run = tmp_path / "rows"
    run.mkdir()
    sizes = {"rows": 10, "features": 3, "months": 12, "buildings": 2, "units": 4}
    (run / "result.json").write_text(json.dumps({"sizes": sizes}))
    other = tmp_path / "units"
    other.mkdir()
    (other / "result.json").write_text("{}")
    entry = {"splits": {"units": {"_dir": str(other)}, "rows": {"_dir": str(run)}}}
    assert dashboard.sizes_of(entry) == sizes
    assert dashboard.sizes_of({"splits": {"units": {"_dir": str(other)}}}) is None
    assert (
        dashboard.sizes_of({"splits": {"rows": {"_dir": str(tmp_path / "x")}}}) is None
    )


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


def test_samplers_of_one_design_share_its_structure():
    def e(design, line, features="base-v1"):
        return {"model": {"name": design}, "line": line, "feature_set": features}

    assert dashboard.structure(e("m0q", "numpyro")) == "m0q/base-v1"
    assert dashboard.structure(e("m0q", "frontier")) == "m0q/base-v1"
    assert dashboard.structure(e("m1q", "frontier", "desc-v1")) == "m1q/desc-v1"
    # Designs without listing features share one key across samplers.
    nuts_l0 = {
        "model": {"name": "L0-mean", "features": False},
        "line": "numpyro",
        "feature_set": "base-v1",
    }
    assert dashboard.structure(nuts_l0) == "L0-mean/none"
    assert dashboard.structure(e("L0-mean", "pymc", "none")) == "L0-mean/none"


def test_data_quality_counts_each_rules_rows_by_action(monkeypatch, tmp_path):
    rules = tmp_path / "q.jsonl"
    rules.write_text(
        "".join(
            json.dumps(r) + "\n"
            for r in (
                {
                    "audit_id": "a",
                    "building": "b1",
                    "action": "quarantine_nonresidential",
                },
                {
                    "audit_id": "b",
                    "building": "b1",
                    "action": "quarantine_product_scope",
                },
                {
                    "audit_id": "c",
                    "building": "b2",
                    "action": "quarantine_product_scope",
                },
            )
        )
    )
    summary = tmp_path / "summary"
    summary.mkdir()
    (summary / "complete.json").write_text(json.dumps({"rows": 10, "rows_in_fit": 9}))
    config = tmp_path / "repo" / "config"
    config.mkdir(parents=True)
    (config / "main-analysis.json").write_text(
        json.dumps(
            {
                "run": "r",
                "data_rules": ["unit-labels-v1", "quarantine-v1"],
                "summary": str(summary),
            }
        )
    )
    monkeypatch.setattr(dashboard, "REPO", tmp_path / "repo")
    monkeypatch.setitem(dashboard.data_module.RULE_SOURCES, "quarantine-v1", rules)
    out = dashboard.data_quality()
    assert (
        out["app_run"] == "r" and out["app_rows"] == 10 and out["app_rows_in_fit"] == 9
    )
    by_rule = {r["rule"]: r for r in out["rules"]}
    q = by_rule["quarantine-v1"]
    assert q["in_app_model"] and q["rows"] == 3 and q["buildings"] == 2
    assert [(a["label"], a["rows"]) for a in q["actions"]] == [
        ("Not a whole apartment on the open market", 2),
        ("Not a home", 1),
    ]
    assert by_rule["unit-labels-v1"]["text"].startswith("One apartment, one id")
    assert "rows" not in by_rule["unit-labels-v1"]  # merges units, drops no rows


def test_data_quality_survives_a_malformed_selection(monkeypatch, tmp_path):
    config = tmp_path / "repo" / "config"
    config.mkdir(parents=True)
    (config / "main-analysis.json").write_text(json.dumps([1, 2]))
    monkeypatch.setattr(dashboard, "REPO", tmp_path / "repo")
    out = dashboard.data_quality()
    assert out["app_run"] is None and out["app_rules"] == [] and out["app_rows"] is None
    (config / "main-analysis.json").write_text(
        json.dumps({"data_rules": None, "summary": 3})
    )
    assert dashboard.data_quality()["app_rules"] == []


def test_serve_check_gives_autoselects_reason_or_a_note(tmp_path):
    from rentfrontier import autoselect

    e = entry(tmp_path, "cpu-fit", 10.0, 100.0, at(1))
    e["hardware"] = "thelio CPU"
    reason = dashboard.serve_check(e, frozenset())
    assert reason == (
        f"it did not run on the {' or '.join(autoselect.SERVING_HARDWARE)} row split"
    )
    e["hardware"] = autoselect.TARGET_HARDWARE
    # its run directory has no result.json to read the data rules from
    assert dashboard.serve_check(e, frozenset()) == (
        "its record cannot be read (FileNotFoundError)"
    )


def test_selection_decision(monkeypatch, tmp_path):
    from rentfrontier import autoselect

    repo = tmp_path / "repo"
    monkeypatch.setattr(dashboard, "REPO", repo)
    assert dashboard.selection_decision([]) is None  # no selection file
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "main-analysis.json").write_text(json.dumps({"run": "served"}))
    calls = []

    def decide(entries, run):
        calls.append(run)
        return {"action": "keep", "reason": "the incumbent ranks first"}

    monkeypatch.setattr(autoselect, "decide", decide)
    assert dashboard.selection_decision(["e"]) == {
        "action": "keep",
        "reason": "the incumbent ranks first",
    }
    assert calls == ["served"]

    def broken(entries, run):
        raise ValueError("no pointwise file")

    monkeypatch.setattr(autoselect, "decide", broken)
    assert dashboard.selection_decision([]) == {
        "error": "ValueError: no pointwise file"
    }


def test_selection_decision_ignores_a_selection_that_is_not_an_object(
    monkeypatch, tmp_path
):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "main-analysis.json").write_text("[1, 2]")
    monkeypatch.setattr(dashboard, "REPO", repo)
    assert dashboard.selection_decision([]) is None


def test_data_quality_counts_corrections_as_corrected_not_left_out(
    monkeypatch, tmp_path
):
    fixes = tmp_path / "c.jsonl"
    fixes.write_text(
        "".join(
            json.dumps({"audit_id": a, "building": b, "action": "correct_bedrooms"})
            + "\n"
            for a, b in (("a", "b1"), ("b", "b2"))
        )
    )
    monkeypatch.setattr(dashboard, "REPO", tmp_path / "repo")
    monkeypatch.setitem(dashboard.data_module.RULE_SOURCES, "bedrooms-ad-v1", fixes)
    rule = {r["rule"]: r for r in dashboard.data_quality()["rules"]}["bedrooms-ad-v1"]
    assert "rows" not in rule and rule["corrected"] == 2 and rule["buildings"] == 2
    assert rule["actions"][0]["label"] == "Bedrooms corrected from the ad"


def test_versus_served_pairs_full_passing_fits(monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "main-analysis.json").write_text(
        json.dumps({"run": "s-rows"})
    )
    monkeypatch.setattr(dashboard, "REPO", tmp_path)
    monkeypatch.setattr(
        dashboard.leaderboard,
        "paired_loo",
        lambda a, b: (10.0 if a == "a" else 1.0, 3.0, 0.5),
    )
    entries = [
        {
            "_key": "s",
            "splits": {"rows": {"run": "s-rows"}},
            "psis": {"_dir": "s"},
            "passes_checks": True,
        },
        {
            "_key": "a",
            "splits": {"rows": {"run": "a"}},
            "psis": {"_dir": "a"},
            "passes_checks": True,
        },
        {
            "_key": "b",
            "splits": {"rows": {"run": "b"}},
            "psis": {"_dir": "b"},
            "passes_checks": True,
        },
        {"_key": "x", "splits": {}, "psis": {"_dir": "x"}, "passes_checks": False},
        {
            "_key": "e",
            "splits": {},
            "psis": {"_dir": "e"},
            "passes_checks": True,
            "tier": {"name": "exploration"},
        },
    ]
    result = dashboard.versus_served(entries)
    assert result["run"] == "s-rows"
    out = result["fits"]
    assert (
        set(out) == {"a", "b"} and abs(out["a"]["pm"] - (3.0**2 + 0.5**2) ** 0.5) < 1e-9
    )
    assert out["a"]["delta"] == 10.0 and not out["a"]["tie"] and out["b"]["tie"]


def test_prior_scores_pair_unscored_fits_with_the_earlier_baseline():
    loos = {
        dashboard.PRIOR_BASELINE: {"_dir": "base"},
        "old": {"_dir": "old-dir"},
        "now": {"_dir": "now-dir"},
        "bad": {"_dir": "bad-dir"},
    }

    def paired(a, b):
        assert b == "base"
        if a == "bad-dir":
            raise ValueError("rows differ")
        return 50.0, 5.0, 1.0

    def entry(key, run, psis=None):
        return {"_key": key, "splits": {"rows": {"run": run}}, "psis": psis}

    entries = [
        entry("a", "old"),
        entry("b", "now", psis={"delta": 3.0}),  # scored now: left alone
        entry("c", "bad"),  # pairs with neither baseline
        entry("d", "no-loo"),
    ]
    out = dashboard.prior_scores(entries, loos=loos, paired=paired)
    assert out == {
        "a": {
            "delta": 50.0,
            "se": 5.0,
            "mcse": 1.0,
            "baseline": dashboard.PRIOR_BASELINE,
            "dataset": dashboard.PRIOR_DATASET,
        }
    }


def test_predictions_score_landed_fits_against_the_fit_they_name(monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    rows = [
        {
            "design": "m/a",
            "against": "s-rows",
            "delta_elpd": [0, 40],
            "clears_2se": False,
        },
        {
            "design": "m/b",
            "against": "s-rows",
            "delta_elpd": [20, 80],
            "clears_2se": None,
        },
        {
            "design": "m/c",
            "against": "s-rows",
            "delta_elpd": [-10, 10],
            "clears_2se": False,
        },
        {"design": "m/a", "split": "latest", "against": "s-rows", "delta_elpd": None},
        {"design": "m/a", "delta_elpd": [-40, 0], "clears_2se": False},
    ]
    (tmp_path / "config" / "predictions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows) + "{not json\n"
    )
    monkeypatch.setattr(dashboard, "REPO", tmp_path)
    paired = {"a": (12.0, 10.0, 1.0), "b": (50.0, 10.0, 1.0)}
    monkeypatch.setattr(
        dashboard.leaderboard, "paired_loo", lambda here, base: paired[here]
    )

    def entry(key, fs, splits):
        return {
            "_key": key,
            "model": {"name": "m"},
            "feature_set": fs,
            "splits": {s: {"run": f"{key}-{s}"} for s in splits},
            "psis": {"_dir": key},
            "passes_checks": True,
        }

    entries = [
        entry("s", "base", ["rows"]),
        entry("a", "a", ["rows", "latest"]),
        entry("b", "b", ["rows"]),
    ]
    entries[0]["splits"]["rows"]["run"] = "s-rows"
    a, b, c, latest, no_against, bad = dashboard.predictions(entries)
    # +12 ± 10 is in [0, 40] and a tie, as predicted.
    assert a["outcome"] == "hit" and a["result"]["clears_2se"] is False
    # +50 ± 10 is in range; no prediction about clearing.
    assert b["outcome"] == "hit" and b["result"]["clears_2se"] is True
    assert c["outcome"] == "pending" and c["result"] is None
    assert latest["run"] == "a-latest" and latest["outcome"] is None
    # No `against`: nothing to pair with, so no outcome.
    assert no_against["outcome"] is None and no_against["result"] is None
    assert "error" in bad
    paired["a"] = (60.0, 10.0, 1.0)
    assert dashboard.predictions(entries)[0]["outcome"] == "miss"
    # A predicted tie that turns out a clear loss misses even inside the range.
    rows[0]["delta_elpd"] = [-40, 0]
    (tmp_path / "config" / "predictions.jsonl").write_text(json.dumps(rows[0]) + "\n")
    paired["a"] = (-39.0, 10.0, 1.0)
    (a,) = dashboard.predictions(entries)
    assert a["result"]["in_range"] and a["outcome"] == "miss"


def test_predictions_prefer_the_latest_full_passing_fit(monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "predictions.jsonl").write_text(
        json.dumps({"design": "m/a", "against": "s-rows", "delta_elpd": None}) + "\n"
    )
    monkeypatch.setattr(dashboard, "REPO", tmp_path)
    monkeypatch.setattr(dashboard.leaderboard, "paired_loo", lambda h, b: (0, 1, 0))

    def entry(key, run, at, passes=True, tier="full"):
        return {
            "_key": key,
            "model": {"name": "m"},
            "feature_set": "a",
            "splits": {"rows": {"run": run, "_at": dt.datetime(2026, 10, at)}},
            "psis": {"_dir": key},
            "passes_checks": passes,
            "tier": {"name": tier},
        }

    entries = [
        entry("s", "s-rows", 1),
        entry("old", "old", 2),
        entry("new", "new", 3),
        entry("subset", "subset", 4, tier="subset"),
        entry("failed", "failed", 5, passes=False),
    ]
    entries[0]["feature_set"] = "base"
    assert dashboard.predictions(entries)[0]["key"] == "new"


def test_the_recorded_predictions_parse():
    path = dashboard.REPO / "config" / "predictions.jsonl"
    for line in path.read_text().splitlines():
        p = json.loads(line)
        assert "/" in p["design"] and p["by"] and p["written"] and p["prediction"]
        lo, hi = p["delta_elpd"] or (None, None)
        assert lo is None or hi is None or lo <= hi
