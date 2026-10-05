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
                "min_ess": 48.3,
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
    assert "+190.5 ± 23.5 held-out ΔELPD" in html and "ELPD 8,367.8" in html
    assert "Indicative only:" in html and "did not pass the convergence gate" in html
    assert "largest R-hat 1.045 against the gate's 1.01" in html
    assert "smallest effective sample size 48 against 400" in html
    assert "without unit-labels-v3" in html
    assert "indicative: did not pass the gate" in html  # the all-fits table


def test_a_passing_unit_split_is_not_flagged(site_root, research_file):
    add_unit_split(research_file, passes=True)
    html = page(site_root, research_file)
    assert 'id="served-unit-split"' in html and "Indicative only:" not in html


def test_no_unit_split_no_section(client):
    html = client.get("/research/validation").get_data(as_text=True)
    assert 'id="served-unit-split"' not in html


def test_rules_of_a_board_key():
    assert rules_of({"key": "m/f/gibbs@abc+q-v5+b-v2 [run]"}) == ["q-v5", "b-v2"]
    assert rules_of({"key": "m/f/gibbs@abc"}) == []
