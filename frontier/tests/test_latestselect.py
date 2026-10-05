import json

import pytest
from rentfrontier import data, features, latestselect

RULES = frozenset({"unit-labels-v3", "quarantine-v5"})
M = "m7-test"


def write(root, name, **kw):
    rec = {
        "name": name,
        "split": "latest",
        "tier": "full",
        "diagnostics": {"passes": True},
        "dataset": str(data.DATASET),
        "data_rules": sorted(RULES),
        "model": {"name": M},
        "feature_set": "nb-coded-v1",
    }
    rec.update(kw)
    (root / name).mkdir(parents=True)
    (root / name / "result.json").write_text(json.dumps(rec))


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        latestselect.data, "recorded_rules", lambda r: tuple(r["data_rules"])
    )
    monkeypatch.setattr(latestselect, "RUNS", tmp_path)
    monkeypatch.setattr(features, "READS_EARLIER_RENTS", {"prev"})
    write(tmp_path, "cand", feature_set="prev")
    write(tmp_path, "ref")
    write(tmp_path, "serve", split="rows", feature_set="prev")
    entry = {"splits": {"rows": {"run": "serve", "_dir": str(tmp_path / "serve")}}}
    monkeypatch.setattr(
        latestselect.leaderboard, "build", lambda keep_dirs: {"entries": [entry]}
    )
    monkeypatch.setattr(
        latestselect.autoselect,
        "why_not",
        lambda e, rules: latestselect.READS_REASON + ", so its PSIS-LOO ...",
    )
    return tmp_path


INC = {"run": "served", "model": M, "feature_set": "nb-coded-v1"}


def test_a_clear_latest_split_win_switches_to_the_serving_run(runs):
    d = latestselect.decide(
        "cand", "ref", "serve", INC, RULES, paired=lambda a, b: (68.5, 15.1)
    )
    assert d["action"] == "switch" and d["run"] == "serve"
    assert "+68.5 ± 15.1" in d["reason"] and "not comparable" in d["reason"]


def test_within_two_se_keeps_the_incumbent(runs):
    d = latestselect.decide(
        "cand", "ref", "serve", INC, RULES, paired=lambda a, b: (20.0, 15.0)
    )
    assert d["action"] == "keep"


def test_an_invalid_pair_is_refused_before_scoring(runs):
    write(runs, "ref-rows", split="rows")
    write(runs, "cand-fail", feature_set="prev", diagnostics={"passes": False})
    write(
        runs,
        "serve-old",
        split="rows",
        feature_set="prev",
        data_rules=["unit-labels-v2"],
    )

    def never(a, b):
        raise AssertionError("scored an invalid pair")

    d = latestselect.decide("cand-fail", "ref-rows", "serve", INC, RULES, paired=never)
    assert d["action"] == "keep"
    assert "fails the convergence gate" in d["problems"]["candidate"]
    assert "not on the latest split" in d["problems"]["reference"]
    d = latestselect.decide("cand", "ref", "serve-old", INC, RULES, paired=never)
    assert "not on the current data rules" in d["problems"]["serve"]
    # the reference must be the served design
    other = dict(INC, feature_set="nb-relist-v1")
    d = latestselect.decide("cand", "ref", "serve", other, RULES, paired=never)
    assert "not the served design" in d["problems"]["reference"]


def test_every_part_of_the_pair_is_checked(runs, monkeypatch):
    def never(a, b):
        raise AssertionError("scored an invalid pair")

    write(runs, "cand-plain")  # reads no earlier rents
    write(runs, "cand-other-model", feature_set="prev", model={"name": "m5-test"})
    write(runs, "cand-old-data", feature_set="prev", dataset="/elsewhere")
    write(runs, "cand-explore", feature_set="prev", tier="exploration")
    write(runs, "serve-wrong-design", split="rows")
    cases = [
        (
            "cand-plain",
            "serve",
            "candidate",
            "its feature set does not read earlier rents",
        ),
        (
            "cand-other-model",
            "serve",
            "candidate",
            "a different model from the reference",
        ),
        ("cand-old-data", "serve", "candidate", "not on the current dataset"),
        ("cand-explore", "serve", "candidate", "not a full-tier fit"),
        ("cand", "serve-wrong-design", "serve", "not the candidate's design"),
    ]
    for cand, serve, part, problem in cases:
        d = latestselect.decide(cand, "ref", serve, INC, RULES, paired=never)
        assert d["action"] == "keep" and problem in d["problems"][part], (cand, serve)


def test_the_serving_run_must_pass_every_other_autoselect_check(runs, monkeypatch):
    def never(a, b):
        raise AssertionError("scored an invalid pair")

    monkeypatch.setattr(
        latestselect.autoselect,
        "why_not",
        lambda e, rules: "its fit took longer than the window",
    )
    d = latestselect.decide("cand", "ref", "serve", INC, RULES, paired=never)
    assert "its fit took longer than the window" in d["problems"]["serve"]
    write(runs, "serve-elsewhere", split="rows", feature_set="prev")
    d = latestselect.decide("cand", "ref", "serve-elsewhere", INC, RULES, paired=never)
    assert "not on the board" in d["problems"]["serve"]


def test_changed_rule_files_refuse_the_pair(runs, monkeypatch):
    def changed(r):
        raise SystemExit("rule file changed")

    monkeypatch.setattr(latestselect.data, "recorded_rules", changed)
    d = latestselect.decide(
        "cand", "ref", "serve", INC, RULES, paired=lambda a, b: (99.0, 1.0)
    )
    assert d["action"] == "keep"
    assert any("cannot be re-applied" in p for p in d["problems"]["serve"])
