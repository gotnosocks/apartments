"""Listing filters for baths, size and elevator, and a summary of the matching asks (playtest round 3a)."""

from apartments.site.web import asks_summary


def test_filters_narrow_and_keep_their_values(client):
    html = client.get(
        "/listings?baths=1&elevator=yes&min_sqft=100&max_sqft=5000"
    ).get_data(as_text=True)
    assert 'value="1" selected' in html and 'value="yes" selected' in html
    assert 'name="min_sqft"' in html and 'value="100"' in html
    assert "listings match" in html or "listing match" in html
    assert "filters leave out listings that don" in html


def test_summary_only_with_filters(client):
    assert "match: median ask" not in client.get("/listings").get_data(as_text=True)
    html = " ".join(client.get("/listings?beds=1").get_data(as_text=True).split())
    assert "match: median ask" in html and "median estimate <strong>$" in html


def test_asks_summary_percentiles():
    class Db:
        def execute(self, sql, params):
            return [(a, None if a == 10 else 2 * a) for a in range(1, 11)]

    class F:
        def where(self):
            return "", []

    s = asks_summary(Db(), F())
    assert (
        s["n"] == 10
        and s["median"] == 5.5
        and s["low"] == 1.9
        and abs(s["high"] - 9.1) < 1e-9
        and s["estimate"] == 10  # the nine listings with an estimate
    )
