import json

import pytest
from rentfrontier import autoselect

RULES = frozenset({"unit-labels-v1", "quarantine-v2"})


def test_current_rules_take_the_latest_version_of_each_family():
    assert autoselect.current_rules(
        ["unit-labels-v1", "quarantine-v1", "quarantine-v2"]
    ) == frozenset({"unit-labels-v1", "quarantine-v2"})
    assert autoselect.current_rules(["quarantine-v10", "quarantine-v9"]) == {
        "quarantine-v10"
    }


def entry(tmp_path, name, delta, seconds, rules=RULES, **kw):
    run = tmp_path / "runs" / name
    run.mkdir(parents=True)
    (run / "result.json").write_text(json.dumps({"data_rules": sorted(rules)}))
    e = {
        "splits": {"rows": {"run": name, "_dir": str(run)}},
        "psis": {"delta": delta, "_dir": name},
        "fit_seconds": seconds,
        "passes_checks": True,
        "interpretable": True,
        "hardware": autoselect.TARGET_HARDWARE,
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
    assert d["action"] == "keep" and d["reason"] == "no eligible fit"


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
