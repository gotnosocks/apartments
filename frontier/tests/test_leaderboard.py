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


def test_paired_scores_cleaning_on_the_rows_both_keep(tmp_path, monkeypatch):
    # r3 is a row a data rule drops: pair on r1 and r2, whether or not a run
    # has it (one population). r4 is not: refuse.
    monkeypatch.setattr(leaderboard.data, "dropped_rows", lambda: frozenset({"r3"}))
    heldout(tmp_path / "a", ["r1", "r2", "r3"], np.array([1.0, 2.0, 3.0]))
    heldout(tmp_path / "b", ["r2", "r1"], np.array([1.0, 0.5]))
    heldout(tmp_path / "d", ["r3", "r1", "r2"], np.array([0.0, 0.0, 0.0]))
    delta, _ = leaderboard.paired(tmp_path / "a", tmp_path / "b")
    assert delta == pytest.approx(1.5)
    delta, _ = leaderboard.paired(tmp_path / "a", tmp_path / "d")
    assert delta == pytest.approx(3.0)
    heldout(tmp_path / "c", ["r1", "r2", "r4"], np.array([1.0, 2.0, 3.0]))
    with pytest.raises(ValueError, match="Held-out rows differ"):
        leaderboard.paired(tmp_path / "c", tmp_path / "b")


def test_vs_reference_pairs_the_shared_rows_less_the_dropped_ones(
    tmp_path, monkeypatch
):
    # The reference lacks r4 (as the promoted runs dropped a few rows); r3 is
    # quarantined: pair on r1 and r2 only.
    monkeypatch.setattr(leaderboard.data, "dropped_rows", lambda: frozenset({"r3"}))
    heldout(tmp_path / "run", ["r1", "r2", "r3", "r4"], np.array([1.0, 2.0, 9.0, 9.0]))
    heldout(tmp_path / "ref", ["r2", "r1", "r3"], np.array([1.0, 0.0, 0.0]))
    out = leaderboard.vs_reference(tmp_path / "run", tmp_path / "ref" / "heldout.npz")
    assert out["paired_rows"] == 2
    assert out["delta_elpd"] == pytest.approx(2.0)


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
    assert good["hardware"] == leaderboard.THELIO_CPU and good["commit"] is None
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


def test_hardware_class_uses_the_device_the_fit_ran_on():
    host = {
        "cpu": "AMD Ryzen 5 3600X 6-Core Processor",
        "gpu": "NVIDIA GeForce RTX 2060 SUPER",
    }
    cpu_run = {"hardware": {**host, "jax_devices": ["cpu:0"]}}
    gpu_run = {"hardware": {**host, "jax_devices": ["cuda:0"]}}
    modal = {
        "hardware": {"gpu": "NVIDIA H100 80GB HBM3", "jax_devices": ["cuda:0"]},
        "remote": {"gpu_reported": "NVIDIA H100 80GB HBM3, 580.95.05"},
    }
    assert leaderboard.hardware_class(cpu_run) == leaderboard.THELIO_CPU
    assert leaderboard.hardware_class(gpu_run) == "thelio RTX 2060 SUPER"
    assert leaderboard.hardware_class(modal) == "Modal H100"
    # The same design on two machines is two entries.
    base = {
        "commit": "abc",
        "model": {"name": "m0"},
        "feature_set": "x",
        "sampler": "gibbs",
        "sampler_settings": {},
    }
    assert leaderboard.design_key({**base, **cpu_run}) != leaderboard.design_key(
        {**base, **gpu_run}
    )


def test_secondary_split_on_other_hardware_joins_the_row_split_entry():
    base = {
        "commit": "abc",
        "model": {"name": "m5"},
        "feature_set": "x",
        "sampler": "gibbs",
        "sampler_settings": {},
    }
    h100 = {
        "hardware": {"gpu": "NVIDIA H100", "jax_devices": ["cuda:0"]},
        "remote": {"gpu_reported": "NVIDIA H100"},
    }
    h200 = {
        "hardware": {"gpu": "NVIDIA H200", "jax_devices": ["cuda:0"]},
        "remote": {"gpu_reported": "NVIDIA H200"},
    }
    rows = {**base, **h100, "split": "rows", "name": "r"}
    units = {**base, **h200, "split": "units", "name": "u"}
    groups = leaderboard.group_runs([units, rows])
    assert len(groups) == 1
    (by_split,) = groups.values()
    assert set(by_split) == {"rows", "units"}
    # Row splits on two hardware classes stay two entries.
    rows2 = {**base, **h200, "split": "rows", "name": "r2"}
    assert len(leaderboard.group_runs([rows, rows2, units])) == 2


def test_latest_record_is_the_newest_scoring_commit_not_the_newest_file(tmp_path):
    old, new = "5cc0809", leaderboard.git("rev-parse", "HEAD")
    for folder, commit in (("a-new", new), ("b-old", old), ("c-unknown", "0" * 40)):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "result.json").write_text(
            json.dumps({"source_run": "r", "commit": commit, "tag": folder})
        )
    # b-old and c-unknown were written last (newest files); a-new still wins.
    assert leaderboard.latest_records(tmp_path)["r"]["tag"] == "a-new"


def test_runs_that_differ_only_in_data_rules_do_not_collide():
    from rentfrontier.leaderboard import design_key

    run = {
        "hardware": {"jax_devices": ["cuda:0"], "gpu": "NVIDIA GeForce RTX 2060 SUPER"},
        "commit": "abc1234",
        "model": {"name": "m0q"},
        "feature_set": "base-v1",
        "sampler": "nuts",
        "sampler_settings": {"chains": 4},
    }
    ruled = run | {"data_rules": ["unit-labels-v1"]}
    assert design_key(run) != design_key(ruled)
    assert design_key(run) == design_key(run | {"data_rules": []})


def test_an_entry_that_cannot_be_paired_loses_its_score_not_the_board():
    base = {"id": "base", "psis": {"_dir": "b"}}
    good = {"id": "good", "psis": {"_dir": "g"}, "note": ""}
    odd = {"id": "odd", "psis": {"_dir": "o"}}

    def paired(a, b):
        if a == "o":
            raise ValueError("Training rows differ: o (10) vs b (12), 2 not dropped")
        return 1.0, 0.5, 0.1

    leaderboard.pair_with_baseline([base, good, odd], base, paired=paired)
    assert base["psis"]["delta"] == 0.0 and good["psis"]["delta"] == 1.0
    assert odd["psis"] is None
    assert odd["unpaired"].startswith("PSIS-LOO not paired: Training rows differ")


def test_a_tuning_fit_is_not_scored_on_the_board():
    base = {"id": "base", "psis": {"_dir": "b"}}
    tuned = {
        "id": "tuned",
        "psis": {"_dir": "t"},
        "data_rules": ["unit-labels-v1", "tune-b35-v1"],
        "passes_checks": True,
        "interpretable": True,
        "fit_seconds": 600,
    }
    leaderboard.pair_with_baseline(
        [base, tuned], base, paired=lambda a, b: (1.0, 0.5, 0.1)
    )
    assert tuned["psis"] is None and "tune-b35-v1" in tuned["unpaired"]
    assert not leaderboard.on_frontier([tuned])[0]


def _board_entry(name, delta, seconds):
    return {
        "id": name,
        "model": {"name": name},
        "feature_set": "f",
        "psis": {"delta": delta, "delta_se": 1.0, "delta_mcse": 0.0, "_dir": name},
        "fit_seconds": seconds,
        "passes_checks": True,
        "interpretable": True,
    }


def _judged(monkeypatch, verdicts):
    table = {}
    for (a, b), v in verdicts.items():
        ids = [f"{a}/f", f"{b}/f"]
        table[frozenset(ids)] = {
            "designs": ids,
            "verdict": "equal" if v == "equal" else f"{v}/f",
            "reason": "test",
        }
    monkeypatch.setattr(leaderboard.elegance, "judgements", lambda *a: table)


def test_the_best_is_the_most_elegant_tie_then_the_fastest(monkeypatch):
    _judged(
        monkeypatch,
        {
            ("top", "simple"): "simple",
            ("top", "simple-fast"): "simple-fast",
            ("simple", "simple-fast"): "equal",
        },
    )
    es = [
        _board_entry("top", 10.0, 600),
        _board_entry("simple", 9.5, 1500),
        _board_entry("simple-fast", 9.0, 900),
        _board_entry("worse", 0.0, 100),
    ]
    deltas = {e["id"]: e["psis"]["delta"] for e in es}

    def paired(a, b):
        return deltas[a] - deltas[b], 1.0, 0.0

    assert leaderboard.choose_best(es, paired=paired)["id"] == "simple-fast"


def test_the_frontier_keeps_a_beaten_fit_only_if_judged_more_elegant(monkeypatch):
    _judged(
        monkeypatch,
        {("best", "simple"): "simple", ("best", "dominated"): "best"},
    )
    es = [
        _board_entry("best", 10.0, 1500),
        _board_entry("simple", 5.0, 1500),
        _board_entry("dominated", 5.0, 1500),
        _board_entry("unjudged", 9.0, 1600),
    ]
    assert leaderboard.on_frontier(es) == [True, True, False, False]


def test_tier_of_reads_the_flag_or_the_legacy_label():
    run = {
        "name": "m0-base-base-v1-rows-e61a794-x-2060-100w300d-nb",
        "sampler_settings": {"draws": 300, "warmup": 100, "chains": 2},
        "data_rules": ["unit-labels-v1"],
    }
    assert leaderboard.tier_of(run) == {
        "name": "exploration",
        "draws": 300,
        "warmup": 100,
        "chains": 2,
        "subset": None,
    }
    full = run | {"name": "m0-base-base-v1-rows-e61a794-gibbs-2060-3600"}
    assert leaderboard.tier_of(full)["name"] == "full"
    tuned = full | {"tier": "exploration", "data_rules": ["tune-b35-v1"]}
    assert leaderboard.tier_of(tuned)["name"] == "exploration"
    assert leaderboard.tier_of(tuned)["subset"] == "tune-b35-v1"


def test_the_frontier_line_is_drawn_from_gate_passing_fits_only():
    quick = _board_entry("quick", 8.0, 300) | {
        "passes_checks": False,
        "tier": {"name": "exploration"},
    }
    passing_quick = _board_entry("pquick", 7.0, 400) | {
        "tier": {"name": "exploration"},
    }
    failed_full = _board_entry("failed", 9.0, 200) | {"passes_checks": False}
    slow = _board_entry("slow", 10.0, 1500)
    assert leaderboard.on_frontier([quick, passing_quick, failed_full, slow]) == [
        False,
        True,
        False,
        True,
    ]
    # The board's best still needs the gate.
    deltas = {"quick": 8.0, "failed": 9.0, "slow": 10.0}
    best = leaderboard.choose_best(
        [quick, failed_full, slow],
        paired=lambda a, b: (deltas[a] - deltas[b], 1.0, 0.0),
    )
    assert best["id"] == "slow"


def test_the_baseline_is_found_by_run_name_or_entry_id(monkeypatch):
    monkeypatch.setattr(leaderboard, "BASELINE", "m0-base-base-v1-rows-abc1234-x-run")
    by_run = {
        "id": "m0-base/base-v1/gibbs@abc1234",
        "splits": {"rows": {"run": "m0-base-base-v1-rows-abc1234-x-run"}},
    }
    other = {
        "id": "m0-base/base-v1/gibbs@abc1234",
        "splits": {"rows": {"run": "m0-base-base-v1-rows-abc1234-x-short"}},
    }
    assert leaderboard.is_baseline(by_run) and not leaderboard.is_baseline(other)
    monkeypatch.setattr(leaderboard, "BASELINE", "m0-base/base-v1/gibbs@5cc0809")
    assert leaderboard.is_baseline(
        {"id": "m0-base/base-v1/gibbs@5cc0809", "splits": {}}
    )


def test_a_short_fit_does_not_dominate_a_longer_fit_of_its_design():
    full = _board_entry("full", 10.0, 2800) | {
        "tier": {"name": "full", "draws": 4500},
        "data_rules": ["unit-labels-v1"],
    }
    short = _board_entry("full", 10.4, 360) | {
        "id": "short",
        "tier": {"name": "exploration", "draws": 300},
        "data_rules": ["unit-labels-v1"],
    }
    # Same design ("full/f") and rules: both stay on the frontier.
    assert leaderboard.on_frontier([full, short]) == [True, True]
    other = short | {"model": {"name": "other"}}
    assert leaderboard.on_frontier([full, other]) == [False, True]


def test_features_that_read_earlier_rents_are_off_the_frontier_line():
    e = {
        "interpretable": True,
        "passes_checks": True,
        "psis": {"delta": 750.0},
        "feature_set": "nb-prevprice-v1",
    }
    assert not leaderboard.frontier_candidate(e)
    assert leaderboard.frontier_candidate({**e, "feature_set": "nb-coded-v1"})
