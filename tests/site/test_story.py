"""The research story (/research/story): its figures come from the served data."""

import json
import re

import pytest

from apartments.site import story
from apartments.site.web import create_app


def _page(client) -> str:
    response = client.get("/research/story")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_story_page_has_its_figures_and_their_tables(client):
    html = _page(client)
    for figure in (
        "compose-figure",
        "effects-figure",
        "build-figure",
        "trials-figure",
        "history-figure",
        "cleaning-figure",
    ):
        assert f'id="{figure}"' in html
    # Every figure is an image with a text alternative and a table beside it.
    assert html.count('role="img"') == 6
    assert all(label.strip() for label in re.findall(r'aria-label="([^"]*)"', html))
    assert html.count('class="table-view"') == 6
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
    # a part whose interval spans zero is called out by name
    text = re.sub(r"\s+", " ", html)
    assert "the 95% interval for “Unit” (+$45) runs from below zero" in text
    assert "whether it adds to the ask or takes from it" in text


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
| 2026-10-05 | `+bednoise` | a residual scale by bedroom group (σ by group) | | +347.0 ± 30.1 | gain | | d (1) | #300 | `a` | `b` |
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
    assert by["+bednoise"]["note"] == "a residual scale by bedroom group"
    assert by["nb-prevprice-v1"]["clear_gain"] and not parks["clear_gain"]


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
    # Open questions: the location idea waiting for the next neighbourhood,
    # and the idea set aside.
    assert (
        "1 idea about where a building sits\nhas made no clear difference so far:</p>"
        in html
    )
    assert "<li>parks within reach</li>" in html
    assert "1 idea raised the score and was\nstill set aside" in html
    assert "still set aside:</p>\n<ul>" in html and "<li>" in html


MILESTONES = [
    {"kind": "pr", "at": "2026-09-18T10:00:00+00:00", "title": "Something else"},
    {
        "kind": "selection",
        "at": "2026-09-18T22:00:00+00:00",
        "title": "Select a PyMC fit",
        "model": "chelsea-bayesian-x",
        "family": "pymc_bayesian",
    },
    {
        "kind": "selection",
        "at": "2026-09-29T17:00:00+00:00",
        "title": "Select the Gibbs fit (#45)",
        "model": "m5-nocurves-unitdesc-v1-rows-ab2a7df-gibbs-2060",
        "family": "frontier_summary",
    },
    {
        "kind": "selection",
        "at": "2026-10-01T02:00:00+00:00",
        "title": "Selection (autoselect): serve 2slopes (#89)",
        "model": "m7-nocurves-2slopes-unitfacing-v5-rows-8502559-gibbs",
        "family": "frontier_summary",
    },
    {
        "kind": "selection",
        "at": "2026-10-07T06:00:00+00:00",
        "title": "Serve nb3-prevprice-v2 by the latest-split rule (#392)",
        "model": "m7-nocurves-floorslope-nb3-prevprice-v2-rows-163c6de-a100",
        "family": "frontier_summary",
    },
    {
        "kind": "selection",
        "at": "2026-10-07T14:00:00+00:00",
        "title": "Unserve prevprice (#403)",
        "model": "m7-nocurves-floorslope-nb3-coded-v2-rows-9371a18-a100",
        "family": "frontier_summary",
    },
]


def test_design_history_eras_terms_and_spells():
    switches = story.design_history(MILESTONES)
    assert [s["era"] for s in switches] == ["bayes", "frontier", "auto", "auto", "auto"]
    assert switches[2]["words"] == "Serve 2slopes" and switches[2]["pr"] == "89"
    assert switches[1]["terms"] == ["nocurves"]
    assert switches[3]["feature_set"] == "nb3-prevprice-v2"
    lives = {life["term"]: life for life in story.term_lives(switches)}
    assert lives["2slopes"]["served"] == [2] and not lives["2slopes"]["now"]
    assert lives["floorslope"]["now"] and lives["nocurves"]["served"] == [1, 2, 3, 4]
    (spell,) = story.served_spells(switches, "prevprice")
    assert spell["hours"] == 8.0
    assert [e["count"] for e in story.eras(switches)] == [1, 1, 3]


@pytest.mark.parametrize(
    "name, parts",
    [
        ("unitdesc-v1", ("unit", "unitdesc", "v1")),
        ("unitdescpluto-v3", ("unit", "unitdescpluto", "v3")),
        ("unitfacing-v5", ("unit", "unitfacing", "v5")),
        ("nb-facing-v1", ("nb", "facing", "v1")),
        ("nb3-coded-v2", ("nb3", "coded", "v2")),
        ("nb5-coded-v2", ("nb5", "coded", "v2")),
        ("nb3-prevprice-v2", ("nb3", "prevprice", "v2")),
        ("", ("", "", "")),
    ],
)
def test_set_parts(name, parts):
    assert story._set_parts(name) == parts


def test_change_words_shrink_and_unknown_set():
    before = {"terms": ["nocurves"], "feature_set": "nb5-coded-v2", "rows": "a"}
    after = {"terms": ["nocurves"], "feature_set": "nb3-newthing-v1", "rows": "a"}
    assert story.change_words(before, after) == (
        "Left out Flatiron and Gramercy Park. Features now include newthing"
    )


def test_design_history_says_what_changed():
    changes = [s["change"] for s in story.design_history(MILESTONES)]
    assert changes[0] == "Select a PyMC fit"
    assert changes[1] == (
        "The first searched design: a straight line per feature, no curves. "
        "Features: words from the ads"
    )
    assert changes[2] == (
        "Added each building's own price for two more features. "
        "Features now include which way each apartment faces"
    )
    assert changes[3] == (
        "Added each building's own price for height. Dropped each building's own "
        "price for two more features. Took in Greenwich Village. "
        "Features now include how the unit's previous listing was repriced"
    )
    again = MILESTONES + [
        {**MILESTONES[-2], "at": "2026-10-08T01:00:00+00:00"},
        {**MILESTONES[-2], "at": "2026-10-08T02:00:00+00:00"},
        {
            **MILESTONES[-2],
            "at": "2026-10-08T03:00:00+00:00",
            "model": MILESTONES[-2]["model"].replace("163c6de", "5789d79"),
        },
    ]
    assert [s["change"] for s in story.design_history(again)][-3:] == [
        "Features back to how the unit's previous listing was repriced",
        "The same design, refitted",
        "The same design, refitted on the current data rules",
    ]


def test_design_chapter_reads_the_milestones(site_root, research_file):
    data = json.loads(research_file.read_text())
    data["milestones"] = MILESTONES
    research_file.write_text(json.dumps(data))
    html = _page(create_app(site_root, research_data=research_file).test_client())
    assert 'id="history-figure"' in html
    assert "It has been replaced\n4 times since Sep 18" in html
    assert html.count('class="switch era-') == 5
    assert "8 hours later they were withdrawn" in html
    assert "style=" not in html


def test_design_history_skips_malformed_milestones():
    odd = [
        {"kind": "selection", "at": "not a date", "title": "x"},
        {"kind": "selection", "at": "2026-10-01", "title": "no zone"},
        {"kind": "selection", "at": None},
        "junk",
        {"kind": "selection", "at": "2026-10-01T02:00:00+00:00", "title": None},
    ]
    switches = story.design_history(odd)
    assert len(switches) == 1 and switches[0]["terms"] is None
    assert story.design_history(None) == []
    assert story.history_svg(switches, story.term_lives(switches))


CLEANING = {
    "run": "served-run",
    "start": {
        "rows": 1000,
        "units": 400,
        "buildings": 50,
        "bed_changes": 0.08,
        "big_jumps": 0.09,
    },
    "steps": [
        {
            "rule": "baths-ad-v2",
            "family": "correct",
            "changed": {"full_baths": 3, "half_baths": 2},
            "dropped": 0,
            "rows": 1000,
            "units": 400,
            "buildings": 50,
        },
        {
            "rule": "fields-review-v3",
            "family": "correct",
            "changed": {},
            "dropped": 0,
            "rows": 1000,
            "units": 400,
            "buildings": 50,
        },
        {
            "rule": "quarantine-v6",
            "family": "drop",
            "changed": {},
            "dropped": 20,
            "rows": 980,
            "units": 395,
            "buildings": 48,
        },
        {
            "rule": "unit-labels-v9",
            "family": "join",
            "changed": {},
            "dropped": 0,
            "rows": 980,
            "units": 380,
            "buildings": 48,
        },
        {
            "rule": "unit-splits-v4",
            "family": "split",
            "changed": {},
            "dropped": 0,
            "rows": 980,
            "units": 410,
            "buildings": 48,
            "bed_changes": 0.007,
            "big_jumps": 0.07,
        },
    ],
}


def test_cleaning_sums_each_family():
    c = story.cleaning(CLEANING, "served-run")
    assert c["current"] and c["corrected"] == 5 and c["dropped"] == 20
    assert c["dropped_buildings"] == 2 and c["joined"] == 15 and c["split"] == 30
    words = [s["words"] for s in c["steps"]]
    assert words[0] == "3 full baths, 2 half baths"
    assert words[1].startswith("no change")
    assert [round(k["after"], 1) for k in c["checks"]] == [0.7, 7.0]
    assert not story.cleaning(CLEANING, "another-run")["current"]
    assert story.cleaning(None) is None
    assert story.cleaning({"start": {}, "steps": []}) is None
    assert story.cleaning_svg(None) == ""
    for broken in (
        {"dropped": None},
        {"changed": {"bedrooms": "x"}},
        {"changed": [1]},
        {"units": "1"},
    ):
        doc = json.loads(json.dumps(CLEANING))
        doc["steps"][2].update(broken)
        assert story.cleaning(doc) is None, broken


def test_cleaning_chapter_reads_the_steps(site_root, research_file, tmp_path):
    path = tmp_path / "cleaning.json"
    path.write_text(json.dumps(CLEANING))
    app = create_app(site_root, research_data=research_file, cleaning_steps=path)
    html = _page(app.test_client())
    assert 'id="cleaning"' in html
    assert "the 1,000 rows pass through\n5 data rules" in html
    assert "so 15 unit names were joined" in html
    assert "8.0% of the time; after the rules,\n0.7%." in html
    assert "an earlier served fit" in html  # the test site serves another run
    assert "Even after the cleaning, 7.0% of a unit" in html
    path.write_text("not json")
    html = _page(app.test_client())
    assert 'id="cleaning"' not in html


def test_accuracy_reads_the_held_out_asks():
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE listings(method TEXT, ask REAL, estimate REAL, pit REAL, "
        "unit_fit_rows INTEGER)"
    )
    assert story.accuracy(db) is None
    rows = [("psis", 9000.0, 1000.0, 0.5, 3)]  # in the fit: not counted
    rows += [("heldout", 1100.0, 1000.0, 0.5, 2)] * 3  # seen, 10% off
    rows += [("heldout", 1000.0, 1000.0, 0.95, 0)] * 2  # new, exact
    db.executemany("INSERT INTO listings VALUES (?, ?, ?, ?, ?)", rows)
    a = story.accuracy(db, small=2)
    assert a["n"] == 5 and round(a["median"], 6) == 10.0
    assert a["typical"] == 1100  # the median ask
    assert a["seen"] == {"n": 3, "median": a["seen"]["median"]}
    assert round(a["seen"]["median"], 6) == 10.0 and a["new"]["median"] == 0.0
    assert a["likely"] == 60.0
    assert story.accuracy(db)["new"] is None  # too few new apartments to report


def test_rent_jumps_by_the_years_between_listings():
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        "CREATE TABLE buildings(id TEXT, address TEXT);"
        "INSERT INTO buildings VALUES ('b1', '1 Main Street');"
        "CREATE TABLE listings(id INTEGER, unit_id TEXT, unit_label TEXT, building_id TEXT,"
        " ask REAL, price_at TEXT, period TEXT, price_basis TEXT);"
    )
    assert story.rent_jumps(db) is None
    rows = [
        (1, "u1", "4B", "2020-01-01", 1000.0, "ask"),
        (2, "u1", "4B", "2020-06-01", 1500.0, "ask"),  # +50% within a year
        (3, "u1", "4B", "2024-06-01", 1600.0, "ask"),  # no jump, 4 years on
        (4, "u1", "4B", "2025-01", 900.0, "rent"),  # another basis: no pair
        (5, "u2", None, "2019-01-01", 2000.0, "ask"),
        (6, "u2", None, "2023-01-01", 3000.0, "ask"),  # +50% after 4 years
        (7, "u2", None, "2025-01", 3000.0, "ask"),  # a bare month still pairs
    ]
    db.executemany(
        "INSERT INTO listings VALUES (?, ?, ?, 'b1', ?, ?, ?, ?)",
        [(i, u, label, ask, at, at[:7], basis) for i, u, label, at, ask, basis in rows],
    )
    j = story.rent_jumps(db)
    assert (j["pairs"], j["jumps"], j["late"]) == (4, 2, 50.0)
    assert [(g["words"], g["pairs"], g["jumps"]) for g in j["gaps"]] == [
        ("within a year", 1, 1),  # an empty gap group is left out
        ("two or more years apart", 3, 1),
    ]
    e = j["example"]  # the first of two equal jumps, by unit
    assert (e["unit_id"], e["before"], e["after"], e["address"]) == (
        "u1",
        1000.0,
        1500.0,
        "1 Main Street",
    )
    assert round(e["change"]) == 50 and e["from"] == "2020-01-01"


def test_unit_examples_pick_a_joined_and_a_split_unit():
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        "CREATE TABLE buildings(id TEXT, address TEXT);"
        "INSERT INTO buildings VALUES ('b1', '1 Main Street'), ('b2', '2 Side Street');"
        "CREATE TABLE listings(id INTEGER, unit_id TEXT, unit_label TEXT, building_id TEXT,"
        " bedrooms REAL, ask REAL, price_at TEXT, period TEXT);"
    )
    assert story.unit_examples(db) == {}
    rows = [
        (1, "j1", "3C", "b1", 1, 3000.0, "2020-01-01"),
        (2, "j1", "UNIT-3C", "b1", 1, 3100.0, "2021-01-01"),
        (3, "j1", "3C", "b1", 1, 3200.0, "2022-01-01"),
        (4, "j2", "4", "b1", 2, 4000.0, "2020-01-01"),
        (5, "j2", "4FL", "b1", 2, 4100.0, "2021-01-01"),  # 2 names, fewer ads
        (6, "s1", "2", "b2", 1, 3995.0, "2017-03-27"),
        (7, "s1~1", "2", "b2", 2, 6750.0, "2019-06"),  # a bare month
        (8, "s1~2", "2", "b2", 4, 10500.0, "2025-10-10"),
        (9, "s2", "5", "b2", 1, 3000.0, "2018-01-01"),
        (10, "s2~1", "5", "b2", 1, 3000.0, "2020-01-01"),  # same bedrooms: no example
        (11, "s3", "6", "b2", 3, 5000.0, "2018-01-01"),
        (12, "s3~1", "6", "b2", 1, 6000.0, "2019-01-01"),  # fewer bedrooms: unclear
        (13, "s3~2", "6", "b2", 4, 7000.0, "2020-01-01"),
    ]
    db.executemany(
        "INSERT INTO listings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(i, u, lab, b, bd, ask, at, at[:7]) for i, u, lab, b, bd, ask, at in rows],
    )
    ex = story.unit_examples(db)
    assert ex["joined"] == {
        "unit_id": "j1",
        "address": "1 Main Street",
        "labels": ["3C", "UNIT-3C"],
        "listings": 3,
    }
    s = ex["split"]
    assert (s["address"], s["label"], s["count"]) == ("2 Side Street", "2", "three")
    assert [(p["unit_id"], p["words"], p["at"]) for p in s["pieces"]] == [
        ("s1", "a one-bedroom", "2017-03-27"),
        ("s1~1", "a two-bedroom", "2019-06-01"),
        ("s1~2", "a four-bedroom", "2025-10-10"),
    ]
    assert (
        story.bed_phrase(0) == "a studio" and story.bed_phrase(None) == "an apartment"
    )
    assert story.bed_phrase(8) == "an 8-bedroom" and story.bed_phrase(-1) == "a studio"


GROUP_ITEMS = {
    "run": "m-test-run",
    "rows": 1000,
    "rows_with_text": 900,
    "near_m": 400.0,
    "attributes": [
        {"item": "walk_in_closet", "rows": 90, "share": 0.1, "raw_pct": 31.9},
        {"item": "stainless", "rows": 360, "share": 0.4, "raw_pct": 6.8},
    ],
    "places": [
        {
            "item": "nycha",
            "words": "NYCHA housing",
            "rows": 1000,
            "median_m": 910,
            "near_share": 0.134,
            "raw_pct_per_doubling": 1.2,
        }
    ],
}


def test_group_items_need_the_served_run():
    trials = story.theories(story.parse_ledger(LEDGER))
    g = story.group_items(GROUP_ITEMS, trials, "m-test-run")
    assert [i["name"] for i in g["attributes"]["items"]] == [
        "Stainless steel",
        "Walk-in closet",
    ]
    assert g["places"]["items"][0]["pct_share"] == 13.4
    assert g["attributes"]["test"] is None  # not in this ledger
    assert story.group_items(GROUP_ITEMS, trials, "m-other-run") is None
    svg = str(story.group_items_svg(g["attributes"]["items"], "whose ad states it"))
    assert "Share of listings whose ad states it: Stainless steel 40.0%" in svg


def test_group_items_chapter(site_root, research_file, tmp_path):
    ledger = tmp_path / "feature-tests.md"
    ledger.write_text(
        LEDGER.replace(
            "| 2026-10-03 | `nb-prevprice-v1`",
            "| 2026-10-06 | `nb3-attrs-v1` | ad states one of 15 attributes | listing"
            " | -7.6 ± 21.9 | no clear gain | | d (1) | #390 | `i` | `j` |\n"
            "| 2026-10-03 | `nb-prevprice-v1`",
        )
    )
    path = tmp_path / "group-items.json"
    path.write_text(json.dumps(GROUP_ITEMS))
    app = create_app(
        site_root, research_data=research_file, feature_tests=ledger, group_items=path
    )
    html = _page(app.test_client())
    assert 'id="inside-groups"' in html
    assert "“Ad states one of 15 attributes” (-7.6 ± 21.9" in html
    assert "the walk to nearby places." in html
    assert "<strong>raw</strong> difference" in html
    assert "<td>Walk-in closet</td>" in html and "+31.9%" in html
    assert "910 m" in html
    path.write_text(json.dumps({**GROUP_ITEMS, "run": "m-other-run"}))
    assert 'id="inside-groups"' not in _page(app.test_client())


def test_group_items_step_aside_once_served():
    trials = story.theories(story.parse_ledger(LEDGER))
    served = {"text:corner_unit", "log m to NYCHA housing"}
    assert story.group_items(GROUP_ITEMS, trials, "m-test-run", served) is None
    assert story.group_items(GROUP_ITEMS, trials, "m-test-run", {"text:x"})


def test_label_lines_wrap_at_spaces():
    assert story.label_lines("short") == ["short"]
    long = "the same repricing idea, retested once Greenwich Village joined"
    assert story.label_lines(long) == [
        "the same repricing idea, retested once",
        "Greenwich Village joined",
    ]
    lines = story.label_lines("word " * 30)
    assert len(lines) == 2 and lines[1].endswith("…") and len(lines[1]) <= 46
