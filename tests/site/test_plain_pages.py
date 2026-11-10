"""Renter-facing pages in plain words (playtest round 1)."""

from apartments.site import anatomy


def test_home_describes_the_served_model_in_words(client):
    html = " ".join(client.get("/").get_data(as_text=True).split())
    # the fixture's served design: walk, bedroom slope and floor slope
    assert "Building drift over time" in html or "building drift over time" in html
    assert "how it works" in html and "PSIS-LOO ΔELPD</a>" in html


def test_summary_lists_the_parts_in_order():
    a = anatomy.describe(
        {"name": "x", "building_walk": True, "trend_knot_months": 3, "beta_sd": 0.5}
    )
    assert a.summary == (
        "Market trend, calendar season, building premium, building drift over time, "
        "apartment premium and listing features"
    )


def test_estimates_says_what_the_estimates_are(client):
    html = " ".join(client.get("/estimates").get_data(as_text=True).split())
    assert "It never saw the ask it is compared with." in html
    assert "Each past ad is the newest ad of its apartment" in html


def test_chosen_by_in_words():
    from apartments.site.web import chosen_by

    assert (
        chosen_by("rentfrontier.autoselect, 2026-10-04 (Ben, 2026-09-30: switch)")
        == "the automatic selection rule, 2026-10-04"
    )
    assert chosen_by("rentfrontier.autoselect") == "the automatic selection rule"
    assert chosen_by("Ben, 2026-09-26") == "Ben, 2026-09-26"
    assert chosen_by("Ben, after review") == "Ben, after review"


def test_home_tiles_are_links(client):
    html = " ".join(client.get("/").get_data(as_text=True).split())
    assert '<a class="tile" href="/listings">' in html
    assert '<a class="tile" href="/listings?status=current">' in html
    assert '<a class="tile" href="/buildings">' in html
    assert 'href="/deals">Deals</a>' in html


def test_home_starts_with_tasks_and_folds_the_technical_details(client):
    html = " ".join(client.get("/").get_data(as_text=True).split())
    start = html.index('id="start"')
    assert start < html.index("Research</a></h2>")
    assert "Looking for an apartment" in html and "Checking an ask" in html
    assert "How rents have changed" not in html and "Pricing an apartment" not in html
    # the technical name and score sit behind a fold
    assert html.index("<summary>Technical details</summary>") < html.index(
        "Technical name"
    )
