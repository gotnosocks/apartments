import json

import pytest
from rentfrontier import autoselect, data

RULES = frozenset({"unit-labels-v1", "quarantine-v2"})


def test_current_rules_take_the_latest_version_of_each_family():
    assert autoselect.current_rules(
        ["unit-labels-v1", "quarantine-v1", "quarantine-v2"]
    ) == frozenset({"unit-labels-v1", "quarantine-v2"})
    assert autoselect.current_rules(["quarantine-v10", "quarantine-v9"]) == {
        "quarantine-v10"
    }
    assert autoselect.current_rules(["legacy", "quarantine-v1"]) == {
        "legacy",
        "quarantine-v1",
    }


def record(rules):
    """A run record with the current hashes of its rule files."""
    return {
        "data_rules": sorted(rules),
        "data_rule_sources": {
            r: {"sha256": data.sha256(data.RULE_SOURCES[r])}
            for r in rules
            if r in data.RULE_SOURCES
        },
    }


def entry(tmp_path, name, delta, seconds, rules=RULES, **kw):
    run = tmp_path / "runs" / name
    run.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps(record(rules)))
    e = {
        "splits": {"rows": {"run": name, "_dir": str(run)}},
        "psis": {"delta": delta, "_dir": name},
        "fit_seconds": seconds,
        "passes_checks": True,
        "interpretable": True,
        "hardware": autoselect.TARGET_HARDWARE,
        "model": {"name": name},
        "feature_set": "f",
    }
    e.update(kw)
    return e


def paired_from(deltas):
    """A paired_loo stand-in: the difference of the entries' deltas, SE 1."""

    def paired(a, b):
        return deltas[a] - deltas[b], 1.0, 0.0

    return paired


def no_heldout_loss(a, b):
    return 0.0, 1.0


def test_eligible_needs_gate_hardware_window_and_current_rules(tmp_path):
    ok = entry(tmp_path, "ok", 10, 1300)
    out = [
        entry(tmp_path, "gate", 10, 1300, passes_checks=False),
        entry(tmp_path, "cpu", 10, 1300, hardware="thelio CPU (Ryzen 5 3600X)"),
        entry(tmp_path, "slow", 10, 2000),
        entry(
            tmp_path, "old-rules", 10, 1300, rules={"unit-labels-v1", "quarantine-v1"}
        ),
        entry(tmp_path, "unscored", None, 1300),
    ]
    assert autoselect.eligible([ok, *out], RULES) == [ok]


def test_ranked_prefers_the_fastest_tie_but_not_on_timing_noise(tmp_path):
    deltas = {"top": 10.0, "tie-fast": 9.0, "tie-noise": 9.5, "worse": 0.0}
    es = [
        entry(tmp_path, "top", 10.0, 1300),
        entry(tmp_path, "tie-fast", 9.0, 600),
        entry(tmp_path, "tie-noise", 9.5, 640),
        entry(tmp_path, "worse", 0.0, 100),
    ]
    order = [
        e["splits"]["rows"]["run"] for e in autoselect.ranked(es, paired_from(deltas))
    ]
    # tie-fast and tie-noise are within TIME_TIE of each other: the higher PSIS wins.
    assert order == ["tie-noise", "tie-fast", "top", "worse"]


def test_an_eligible_incumbent_is_kept_on_a_tie(tmp_path):
    deltas = {"inc": 10.0, "new": 11.0}
    es = [entry(tmp_path, "inc", 10.0, 1300), entry(tmp_path, "new", 11.0, 1290)]
    d = autoselect.decide(es, "inc", RULES, paired_from(deltas), no_heldout_loss)
    assert d["action"] == "keep" and d["run"] == "inc"


def test_a_clearly_better_challenger_replaces_the_incumbent(tmp_path):
    deltas = {"inc": 10.0, "new": 20.0}
    es = [entry(tmp_path, "inc", 10.0, 1300), entry(tmp_path, "new", 20.0, 1300)]
    d = autoselect.decide(es, "inc", RULES, paired_from(deltas), no_heldout_loss)
    assert d["action"] == "switch" and d["run"] == "new"


def test_an_ineligible_incumbent_is_replaced_by_the_best_that_passes_heldout(tmp_path):
    deltas = {"inc": 10.0, "a": 12.0, "b": 11.5}
    es = [
        entry(tmp_path, "inc", 10.0, 1300, rules={"unit-labels-v1", "quarantine-v1"}),
        entry(tmp_path, "a", 12.0, 1300),
        entry(tmp_path, "b", 11.5, 1300),
    ]

    def heldout(a, b):
        return (-9.0, 1.0) if a.name == "a" else (0.0, 1.0)

    d = autoselect.decide(es, "inc", RULES, paired_from(deltas), heldout)
    assert d["action"] == "switch" and d["run"] == "b"
    assert d["checked"][0]["refused"].startswith("held-out")
    assert "quarantine-v1" in d["reason"] and "not the current" in d["reason"]


def test_no_candidate_keeps_the_incumbent(tmp_path):
    es = [entry(tmp_path, "inc", 10.0, 1300, rules={"unit-labels-v1"})]
    d = autoselect.decide(es, "inc", RULES, paired_from({"inc": 10.0}), no_heldout_loss)
    assert d["action"] == "keep" and d["reason"].startswith("no eligible fit;")
    assert "not the current" in d["reason"]


@pytest.mark.parametrize("bad", ["other-run"])
def test_selection_record_refuses_another_runs_bundle(tmp_path, bad):
    run = tmp_path / "run"
    run.mkdir()
    (run / "result.json").write_text(json.dumps({"name": "r1"}))
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "complete.json").write_text(json.dumps({"run": bad}))
    with pytest.raises(SystemExit):
        autoselect.selection_record(run, bundle, tmp_path, {"checked": []})


def test_a_changed_rule_file_makes_a_fit_ineligible(tmp_path):
    e = entry(tmp_path, "stale", 10.0, 1300)
    rec = record(RULES)
    rec["data_rule_sources"]["quarantine-v2"]["sha256"] = "0" * 64
    (tmp_path / "runs" / "stale" / "result.json").write_text(json.dumps(rec))
    assert "cannot be re-applied" in autoselect.why_not(e, RULES)
    assert autoselect.eligible([e], RULES) == []


def test_an_unscored_incumbent_is_replaced_without_pairing(tmp_path):
    es = [
        entry(tmp_path, "inc", None, 1300),
        entry(tmp_path, "new", 10.0, 1300),
    ]

    def never(a, b):
        raise AssertionError("an unscored incumbent cannot be paired")

    d = autoselect.decide(es, "inc", RULES, paired_from({"new": 10.0}), never)
    assert d["action"] == "switch" and d["run"] == "new"
    assert "no paired PSIS-LOO score" in d["reason"]


def test_a_lower_ranked_fit_that_clearly_beats_the_incumbent_is_chosen(
    tmp_path, monkeypatch
):
    # a ties the incumbent (judged as simple, not faster) and ranks first, b is
    # clearly better than the incumbent.
    judged(monkeypatch, {("inc", "a"): "equal"})
    es = [
        entry(tmp_path, "inc", 10.0, 1300),
        entry(tmp_path, "a", 10.5, 1300),
        entry(tmp_path, "b", 10.4, 1300),
    ]

    def paired(x, y):
        d = {("a", "b"): 0.1, ("b", "a"): -0.1, ("inc", "a"): -0.5, ("a", "inc"): 0.5}
        if (x, y) == ("b", "inc"):
            return 5.0, 1.0, 0.0  # beyond the tolerance of 2
        return d.get((x, y), 0.0), 1.0, 0.0

    d = autoselect.decide(es, "inc", RULES, paired, no_heldout_loss)
    assert d["action"] == "switch" and d["run"] == "b"
    assert d["checked"][0]["refused"].startswith("does not clearly beat")


def test_keep_reasons_are_specific(tmp_path):
    only = [entry(tmp_path, "inc", 10.0, 1300)]
    d = autoselect.decide(
        only, "inc", RULES, paired_from({"inc": 10.0}), no_heldout_loss
    )
    assert d["reason"] == "the incumbent is the only eligible fit"


def test_single_listing_coverage(tmp_path):
    import pandas as pd

    pd.DataFrame(
        {
            "in_fit": [True, True, True, False],
            "unit_fit_rows": [1, 1, 2, 1],
            "pit": [0.5, 0.99, 0.5, 0.5],
        }
    ).to_parquet(tmp_path / "rows.parquet")
    assert autoselect.single_listing_coverage(tmp_path) == 0.5


def test_fits_ranked_below_an_eligible_incumbent_do_not_replace_it(tmp_path):
    # X ties I, I ties C, C does not tie X: the board's choice is I (fastest of
    # those tied with the top); C is faster than I but ranks below it.
    es = [
        entry(tmp_path, "X", 100.0, 1500),
        entry(tmp_path, "I", 95.0, 1000),
        entry(tmp_path, "C", 55.0, 800),
    ]

    def paired(a, b):
        d = {"X": 100.0, "I": 95.0, "C": 55.0}
        return d[a] - d[b], 20.0, 0.0  # tolerance 40

    order = [e["splits"]["rows"]["run"] for e in autoselect.ranked(es, paired)]
    assert order[0] == "I"
    d = autoselect.decide(es, "I", RULES, paired, no_heldout_loss)
    assert d["action"] == "keep" and d["run"] == "I"


def test_an_incumbent_that_ranks_first_says_so(tmp_path):
    es = [entry(tmp_path, "inc", 20.0, 1300), entry(tmp_path, "low", 0.0, 1300)]
    d = autoselect.decide(
        es, "inc", RULES, paired_from({"inc": 20.0, "low": 0.0}), no_heldout_loss
    )
    assert d["action"] == "keep" and d["reason"] == "the incumbent ranks first"


def test_tuning_rules_are_not_served(tmp_path):
    assert autoselect.current_rules(["tune-b35-v1", "unit-labels-v1"]) == {
        "unit-labels-v1"
    }
    e = entry(
        tmp_path,
        "tuned",
        10.0,
        600,
        rules={"unit-labels-v1", "quarantine-v2", "tune-b35-v1"},
    )
    assert "tuning fit" in autoselect.why_not(e, RULES)


def test_a_fit_on_another_dataset_is_not_served(tmp_path, monkeypatch):
    e = entry(tmp_path, "old", 10.0, 1300)
    rec = json.loads((tmp_path / "runs" / "old" / "result.json").read_text())
    rec["dataset"] = str(tmp_path / "chelsea-only")
    (tmp_path / "runs" / "old" / "result.json").write_text(json.dumps(rec))
    monkeypatch.setattr(autoselect.data, "DATASET", tmp_path / "combined")
    assert "not the current combined" in autoselect.why_not(e, RULES)


def judged(monkeypatch, verdicts):
    """Simplicity judgements for test entries: {(a, b): winner or "equal"}."""
    table = {}
    for (a, b), v in verdicts.items():
        ids = [f"{a}/f", f"{b}/f"]
        table[frozenset(ids)] = {
            "designs": ids,
            "verdict": "equal" if v == "equal" else f"{v}/f",
            "reason": "test",
        }
    monkeypatch.setattr(autoselect.simplicity, "judgements", lambda *a: table)


def test_ranked_prefers_the_simpler_tie_before_the_faster(tmp_path, monkeypatch):
    judged(monkeypatch, {("top", "simple"): "simple", ("simple", "fast"): "simple"})
    deltas = {"top": 10.0, "simple": 9.0, "fast": 9.5}
    es = [
        entry(tmp_path, "top", 10.0, 1300),
        entry(tmp_path, "simple", 9.0, 1500),
        entry(tmp_path, "fast", 9.5, 600),
    ]
    order = [
        e["splits"]["rows"]["run"] for e in autoselect.ranked(es, paired_from(deltas))
    ]
    assert order == ["simple", "fast", "top"]


def test_a_tied_simpler_challenger_replaces_the_incumbent(tmp_path, monkeypatch):
    judged(monkeypatch, {("inc", "new"): "new"})
    deltas = {"inc": 10.0, "new": 9.5}
    es = [entry(tmp_path, "inc", 10.0, 1300), entry(tmp_path, "new", 9.5, 1500)]
    d = autoselect.decide(es, "inc", RULES, paired_from(deltas), no_heldout_loss)
    assert d["action"] == "switch" and d["run"] == "new"


def test_a_tied_faster_but_less_simple_challenger_does_not(tmp_path, monkeypatch):
    judged(monkeypatch, {("inc", "new"): "inc"})
    deltas = {"inc": 10.0, "new": 10.5}
    es = [entry(tmp_path, "inc", 10.0, 1300), entry(tmp_path, "new", 10.5, 600)]
    d = autoselect.decide(es, "inc", RULES, paired_from(deltas), no_heldout_loss)
    assert d["action"] == "keep" and d["run"] == "inc"


def test_a_tied_equally_simple_and_much_faster_challenger_replaces(
    tmp_path, monkeypatch
):
    judged(monkeypatch, {("inc", "new"): "equal"})
    deltas = {"inc": 10.0, "new": 10.5}
    es = [entry(tmp_path, "inc", 10.0, 1300), entry(tmp_path, "new", 10.5, 600)]
    d = autoselect.decide(es, "inc", RULES, paired_from(deltas), no_heldout_loss)
    assert d["action"] == "switch" and d["run"] == "new"
    assert "judged as simple" in d["reason"] and "faster" in d["reason"]


def test_an_unjudged_tie_waits_for_a_judgement(tmp_path, monkeypatch):
    judged(monkeypatch, {})
    deltas = {"inc": 10.0, "new": 10.5}
    es = [entry(tmp_path, "inc", 10.0, 1300), entry(tmp_path, "new", 10.5, 600)]
    d = autoselect.decide(es, "inc", RULES, paired_from(deltas), no_heldout_loss)
    assert d["action"] == "keep"
    assert "no simplicity judgement" in d["checked"][0]["refused"]
    assert d["pending_judgements"] == [("inc/f", "new/f")]


def test_a_tie_with_the_incumbent_outside_the_top_band_is_pending(
    tmp_path, monkeypatch
):
    # top is refused by the held-out guard; new ties the incumbent but not top.
    judged(monkeypatch, {})
    deltas = {"inc": 10.0, "new": 10.5, "top": 20.0}
    es = [
        entry(tmp_path, "inc", 10.0, 1300),
        entry(tmp_path, "new", 10.5, 600),
        entry(tmp_path, "top", 20.0, 1300),
    ]

    def heldout(a, b):
        return (-9.0, 1.0) if a.name == "top" else (0.0, 1.0)

    d = autoselect.decide(es, "inc", RULES, paired_from(deltas), heldout)
    assert d["action"] == "keep"
    assert d["pending_judgements"] == [("inc/f", "new/f")]
