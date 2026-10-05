"""The served model's runners-up, with paired PSIS-LOO against it (playtest round 2)."""

import json

from apartments.site.web import create_app


def test_runners_up_are_ranked_by_their_paired_difference(site_root, research_file):
    data = json.loads(research_file.read_text())
    other = next(e for e in data["entries"] if e["id"] == "m-other")
    other["vs_served"] = {"delta": 12.0, "se": 4.0, "mcse": 1.0, "tie": False}
    failing = next(e for e in data["entries"] if e["id"] == "m-failing")
    failing["vs_served"] = {"delta": -3.0, "se": 4.0, "mcse": 1.0, "tie": True}
    data["autoselect"] = {
        "action": "keep",
        "reason": "x",
        "eligible": [{"run": "m-test-run"}],
    }
    research_file.write_text(json.dumps(data))
    html = " ".join(
        create_app(site_root, research_data=research_file)
        .test_client()
        .get("/research/model")
        .get_data(as_text=True)
        .split()
    )
    assert 'id="runners-up"' in html
    assert "It was the only fit eligible under the current rules" in html
    assert html.index("+12.0 ± 4.0") < html.index("-3.0 ± 4.0")
    assert "<td>better</td>" in html and "<td>a tie</td>" in html


def test_no_runners_up_section_without_the_data(client):
    assert 'id="runners-up"' not in client.get("/research/model").get_data(as_text=True)
