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


def test_estimates_explains_the_market_reference(client):
    html = " ".join(client.get("/estimates").get_data(as_text=True).split())
    assert "not what a typical one-bedroom asks" in html
    assert "Glossary of terms" in html
