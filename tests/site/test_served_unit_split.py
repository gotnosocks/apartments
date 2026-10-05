"""The served design's unit-split score on the validation page, marked
indicative when its fit did not pass the convergence gate."""

import json

from apartments.site.web import create_app, rules_of


def add_unit_split(research_file, passes):
    data = json.loads(research_file.read_text())
    served = next(e for e in data["entries"] if e["id"].startswith("m-test/"))
    split = dict(
        served,
        id="m-test/unitdesc-v1/nuts@bbbbbbb+quarantine-v1",
        key="m-test/unitdesc-v1/nuts@bbbbbbb+quarantine-v1 [m-test-units]",
        frontier=False,
        current_best=False,
        splits={
            "units": {
                "run": "m-test-units",
                "delta": 190.5,
                "delta_se": 23.5,
                "elpd": 8367.8,
                "max_rhat": 1.045 if not passes else 1.004,
                "min_ess": 48.3 if not passes else 900.0,
                "paired_rows": 657,
                "passes": passes,
                "completed_at": "2026-10-05T05:23:07+00:00",
            }
        },
    )
    served["key"] = (
        "m-test/unitdesc-v1/nuts@aaaaaaa+unit-labels-v3+quarantine-v1 [m-test-run]"
    )
    data["entries"].append(split)
    research_file.write_text(json.dumps(data))


def page(site_root, research_file):
    client = create_app(site_root, research_data=research_file).test_client()
    return " ".join(client.get("/research/validation").get_data(as_text=True).split())


def test_a_failing_unit_split_is_indicative(site_root, research_file):
    add_unit_split(research_file, passes=False)
    html = page(site_root, research_file)
    assert 'id="served-unit-split"' in html
    assert "+190.5 ± 23.5 held-out ΔELPD" in html
    assert "on the 657 held-out listings both models scored" in html
    assert "Indicative only:" in html and "did not pass the convergence gate" in html
    assert "largest R-hat 1.045; the gate needs below 1.01" in html
    assert "smallest effective sample size 48; the gate needs more than 400" in html
    assert "without unit-labels-v3" in html
    assert "indicative: did not pass the gate" in html  # the all-fits table


def test_a_passing_unit_split_is_not_flagged(site_root, research_file):
    add_unit_split(research_file, passes=True)
    html = page(site_root, research_file)
    assert 'id="served-unit-split"' in html and "Indicative only:" not in html


def test_only_the_thresholds_missed_are_given():
    from apartments.site.web import gate_misses

    gate = {"rhat": 1.01, "ess": 400}
    assert gate_misses({"max_rhat": 1.006, "min_ess": 3265}, gate) == []
    assert gate_misses({"max_rhat": 1.02, "min_ess": 3265}, gate) == [
        "largest R-hat 1.020; the gate needs below 1.01"
    ]
    assert gate_misses({}, gate) == [] and gate_misses({"max_rhat": 2}, {}) == []


def test_a_passing_fit_is_preferred_over_a_newer_failing_one(site_root, research_file):
    add_unit_split(research_file, passes=False)
    data = json.loads(research_file.read_text())
    older = dict(data["entries"][-1], key="m-test/unitdesc-v1/nuts@ccccccc [old]")
    older["splits"] = {
        "units": dict(
            older["splits"]["units"],
            delta=150.0,
            passes=True,
            max_rhat=1.004,
            min_ess=900.0,
            completed_at="2026-09-01T00:00:00+00:00",
        )
    }
    data["entries"].append(older)
    research_file.write_text(json.dumps(data))
    html = page(site_root, research_file)
    assert "+150.0 ± 23.5" in html.split('id="served-unit-split"')[1][:600]


def test_no_unit_split_no_section(client):
    html = client.get("/research/validation").get_data(as_text=True)
    assert 'id="served-unit-split"' not in html


def test_rules_of_a_board_key():
    assert rules_of({"key": "m/f/gibbs@abc+q-v5+b-v2 [run]"}) == ["q-v5", "b-v2"]
    assert rules_of({"key": "m/f/gibbs@abc"}) == []
