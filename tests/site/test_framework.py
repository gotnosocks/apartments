"""The Fable framework's explained share against the null (story) and the
predictions recorded before fitting (History), both from the research data."""

import json

from apartments.site.web import create_app


def edit(research_file, fn):
    data = json.loads(research_file.read_text())
    fn(data, next(e for e in data["entries"] if e["id"].startswith("m-test/")))
    research_file.write_text(json.dumps(data))


def family(explained, null_95, excess):
    return {
        "explained": explained,
        "null_mean": explained - excess,
        "null_95": null_95,
        "excess": excess,
    }


def with_explained(data, served):
    served["explained"] = {
        "nb-hpd-v1": {
            "commit": "abc",
            "buildings": 5415,
            "families": {"building condition": family(0.0138, -0.0007, 0.0154)},
        },
        "nb-noise-v1": {
            "commit": "abc",
            "buildings": 5415,
            "families": {"noise": family(0.009, -0.0001, 0.0105)},
        },
        # above the shuffled 95th percentile but below zero: explains nothing
        "nb-crime-v1": {
            "commit": "abc",
            "buildings": 5415,
            "families": {"safety": family(-0.0004, -0.0005, 0.0008)},
        },
    }


def test_story_shows_which_families_beat_chance(site_root, research_file):
    edit(research_file, with_explained)
    client = create_app(site_root, research_data=research_file).test_client()
    html = " ".join(client.get("/research/story").get_data(as_text=True).split())
    assert 'id="explained-figure"' in html
    assert (
        "Of 3 families tried on the served fit, 2 do: building condition (1.4%) and noise (0.9%)"
        in html
    )
    assert "safety 0.0% against -0.1% by chance, no better than chance" in html
    assert "Over 5,415 buildings." in html
    table = html.split("The families as a table", 1)[1].split("</table>", 1)[0]
    assert (
        table.index("Building condition") < table.index("Noise") < table.index("Safety")
    )
    assert table.count("<td>yes</td>") == 2 and table.count("<td>no</td>") == 1


def test_story_leaves_it_out_for_a_fit_without_screens(client):
    html = client.get("/research/story").get_data(as_text=True)
    assert 'id="explained"' not in html and "explained-figure" not in html


def test_story_says_when_no_family_beats_chance(site_root, research_file):
    def none_beat(data, served):
        served["explained"] = {
            "s": {"buildings": 10, "families": {"trees": family(-0.001, 0.002, -0.001)}}
        }

    edit(research_file, none_beat)
    client = create_app(site_root, research_data=research_file).test_client()
    html = " ".join(client.get("/research/story").get_data(as_text=True).split())
    assert "The one family tried on the served fit, trees, doesn't" in html


PREDICTIONS = [
    {
        "design": "m-a/set",
        "by": "Modeling",
        "written": "2026-10-10T20:10Z",
        "prediction": "Small gain, a tie at 2 SE",
        "delta_elpd": [10, 60],
        "clears_2se": False,
        "key": None,
        "outcome": "pending",
        "result": None,
    },
    {
        "design": "m-b/set",
        "by": "Modeling",
        "written": "2026-10-09T10:00Z",
        "prediction": "Beats the served fit",
        "delta_elpd": [-30, None],
        "clears_2se": None,
        "key": "m-test/x",
        "outcome": "hit",
        "result": {"delta": 41.25, "pm": 20.0},
    },
    {
        "design": "m-c/set",
        "by": "Data improvements",
        "written": "2026-10-09T11:00Z",
        "prediction": "A clear gain",
        "delta_elpd": [50, None],
        "clears_2se": True,
        "key": None,
        "outcome": "miss",
        "result": {"delta": 12.0, "pm": 15.0},
    },
    {"error": "KeyError: 'design'", "line": "{}"},
]


def test_history_lists_the_predictions_with_hit_or_miss(site_root, research_file):
    edit(research_file, lambda data, served: data.update(predictions=PREDICTIONS))
    client = create_app(site_root, research_data=research_file).test_client()
    html = " ".join(client.get("/research/history").get_data(as_text=True).split())
    assert "Predictions made before fitting" in html
    assert "3 recorded: 1 hit and 1 miss so far, 1 waiting" in html
    card = html.split('id="predictions"', 1)[1].split("</section>", 1)[0]
    assert card.index("m-a/set") < card.index("m-c/set") < card.index("m-b/set")
    assert "+10 to +60, a tie" in card and "at least -30" in card
    assert "at least +50, clears the bar" in card
    assert '+41.2 <span class="muted">± 20.0' in card
    assert "<strong>miss</strong>" in card and "waiting for the fit" in card
    assert "KeyError" not in card


def test_history_has_no_predictions_card_without_them(client):
    html = client.get("/research/history").get_data(as_text=True)
    assert 'id="predictions"' not in html
