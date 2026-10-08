"""The research story (/research/story): its figures come from the served data."""

import json
import re

from apartments.site import story
from apartments.site.web import create_app


def _page(client) -> str:
    response = client.get("/research/story")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_story_page_has_its_figures_and_their_tables(client):
    html = _page(client)
    for figure in ("compose-figure", "effects-figure", "build-figure", "trials-figure"):
        assert f'id="{figure}"' in html
    # Every figure is an image with a text alternative and a table beside it.
    assert html.count('role="img"') == 4
    assert all(label.strip() for label in re.findall(r'aria-label="([^"]*)"', html))
    assert html.count('class="table-view"') == 4
    # No inline style: the site's CSP allows none.
    assert "style=" not in html


def test_story_is_in_the_research_nav(client):
    html = _page(client)
    assert 'href="/research/story" aria-current="page"' in html


def test_layers_follow_the_served_design_with_shares(client):
    html = _page(client)
    # The test entry has a variance breakdown, so the shares are shown.
    assert "share of the spread in asks" in html
    assert 'id="shares-pending"' not in html
    assert (
        html.index("The market")
        < html.index("The building")
        < html.index("What&#39;s left")
    )


def test_shares_wait_for_the_served_fits_breakdown(site_root, research_file):
    data = json.loads(research_file.read_text())
    for e in data["entries"]:
        e.pop("variance", None)
    research_file.write_text(json.dumps(data))
    client = create_app(site_root, research_data=research_file).test_client()
    html = _page(client)
    assert 'id="shares-pending"' in html
    assert "share of the spread in asks" not in html


def test_build_up_ends_at_the_estimate(client):
    html = _page(client)
    m = re.search(r'class="story-svg buildup"[^>]*aria-label="([^"]*)"', html)
    assert m and "estimate $" in m.group(1) and "the ask $" in m.group(1)


def test_build_up_steps_sum_to_the_estimate():
    listing = {
        "contributions": json.dumps(
            [
                {"term": "market", "usd": 3000.0, "lower": 2900, "upper": 3100},
                {"term": "bedrooms", "usd": 500.0, "lower": 450, "upper": 550},
                {"term": "views", "usd": 12.0, "lower": -5, "upper": 30},
                {"term": "pets", "usd": -8.0, "lower": -20, "upper": 4},
                {"term": "building", "usd": -200.0, "lower": -400, "upper": 0},
            ]
        ),
        "ask": 3400.0,
        "pred_lower_95": 2800.0,
        "pred_upper_95": 3900.0,
    }
    b = story.build_up(listing, {"bedrooms": "Bedrooms"})
    assert [s["term"] for s in b["steps"]] == [
        "market",
        "bedrooms",
        "building",
        "minor",
    ]
    assert (
        b["steps"][-1]["usd"] == 4.0 and b["steps"][-1]["label"] == "2 smaller details"
    )
    assert b["estimate"] == 3304.0
    assert b["steps"][2]["css"] == "g-building"


def test_headline_effects_skip_unknowns_and_nulls():
    rows = [
        {
            "feature": "bedrooms=0",
            "feature_group": "bedrooms",
            "pct": -23.0,
            "pct_lower": -24.0,
            "pct_upper": -22.0,
        },
        {
            "feature": "sqft_unknown",
            "feature_group": "size",
            "pct": -5.0,
            "pct_lower": -6.0,
            "pct_upper": -4.0,
        },
        {
            "feature": "view_park",
            "feature_group": "views",
            "pct": 0.4,
            "pct_lower": -1.0,
            "pct_upper": 2.0,
        },
        {
            "feature": "West Village",
            "feature_group": "neighbourhood",
            "pct": 12.0,
            "pct_lower": 10.0,
            "pct_upper": 14.0,
        },
        {
            "feature": "log_sqft_vs_bedroom_median",
            "feature_group": "size",
            "pct": 29.4,
            "pct_lower": 28.0,
            "pct_upper": 31.0,
        },
    ]
    effects = story.headline_effects(rows, {}, "Chelsea")
    words = [e["words"] for e in effects]
    assert words == [
        "the West Village",
        "10% more space than usual for the bedrooms",
        "a studio",
    ]
    assert effects[0]["against"] == "Chelsea"
    assert effects[2]["against"] == "a one-bedroom"
    # 29.4% per log unit is about 2.5% per 10% more space.
    assert round(effects[1]["pct"], 1) == 2.5


LEDGER = """# Feature and model tests

| Date | Change | What | Kind | ΔPSIS-LOO | Verdict | Retest | Dataset (rows) | PR | Test run | Reference run |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-05 | `+bednoise` | a residual scale by bedroom group | | +347.0 ± 30.1 | gain | | d (1) | #300 | `a` | `b` |
| 2026-10-04 | `nb3-parks-v1` | parks within reach | location | -6.2 ± 9.0 | no clear gain | next neighbourhood | d (1) | #250 | `c` | `d` |
| 2026-10-03 | `nb3-parks-v1` | parks within reach | location | +3.0 ± 9.5 | no clear gain | | d (1) | #250 | `e` | `f` |
| 2026-10-03 | `nb-prevprice-v1` | how the unit's previous listing was repriced | listing | +747.0 ± 40.0 | PSIS-LOO leaks; judged on the latest split | | d (1) | | `g` | `h` |

## Paired by hand

| Date | Change | What | Feature set | ΔPSIS-LOO | Verdict | PR | Test run | Reference run |
|---|---|---|---|---|---|---|---|---|
| 2026-10-06 | `unit-splits-v1` | a unit's history splits | `nb3-coded-v2` | +475.0 ± 50.0 | gain | #400 | | |
"""


def test_theories_keep_every_test_and_the_latest_verdict():
    entries = story.theories(story.parse_ledger(LEDGER))
    by = {t["change"]: t for t in entries}
    assert [t["kind"] for t in entries] == ["model", "listing", "location", "data"]
    parks = by["nb3-parks-v1"]
    assert len(parks["tests"]) == 2 and parks["diff"] == -6.2
    assert parks["verdict"] == "null" and parks["first"] == "2026-10-03"
    assert by["nb-prevprice-v1"]["verdict"] == "blocked"
    assert by["+bednoise"]["words"] == story.PLAIN["+bednoise"]
    assert sorted(t["seq"] for t in entries) == [0, 1, 2, 3]


def test_theories_chapter_reads_the_ledger(site_root, research_file, tmp_path):
    ledger = tmp_path / "feature-tests.md"
    ledger.write_text(LEDGER)
    app = create_app(site_root, research_data=research_file, feature_tests=ledger)
    html = _page(app.test_client())
    assert 'id="theories"' in html
    assert "So far 4 ideas have been tried, in 5 paired fits." in html
    assert (
        "2 helped, 1\nmade no clear difference and 1 made it worse or were set aside."
        in html
    )
    assert "1 of the 1 ideas about where a building sits," in html
    assert html.count('class="trial ') == 4
    assert "Some ideas scored brilliantly" in html
