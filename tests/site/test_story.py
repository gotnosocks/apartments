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
    for figure in ("compose-figure", "effects-figure", "build-figure"):
        assert f'id="{figure}"' in html
    # Every figure is an image with a text alternative and a table beside it.
    assert html.count('role="img"') == 3
    assert all(label.strip() for label in re.findall(r'aria-label="([^"]*)"', html))
    assert html.count('class="table-view"') == 3
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
