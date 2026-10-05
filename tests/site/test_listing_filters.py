"""Listing filters for baths, size and elevator, and a summary of the matching asks (playtest round 3a)."""

from apartments.site.web import asks_summary


def test_filters_narrow_and_keep_their_values(client):
    html = client.get(
        "/listings?baths=1&elevator=yes&min_sqft=100&max_sqft=5000"
    ).get_data(as_text=True)
    assert 'value="1" selected' in html and 'value="yes" selected' in html
    assert 'name="min_sqft"' in html and 'value="100"' in html
    assert "listings match" in html or "listing match" in html
    assert "a size filter leaves out listings" in html


def test_summary_only_with_filters(client):
    assert "match: median ask" not in client.get("/listings").get_data(as_text=True)
    assert "match: median ask" in " ".join(
        client.get("/listings?beds=1").get_data(as_text=True).split()
    )


def test_asks_summary_percentiles():
    class Db:
        def execute(self, sql, params):
            return [(a,) for a in range(1, 11)]

    class F:
        def where(self):
            return "", []

    s = asks_summary(Db(), F())
    assert s == {"n": 10, "median": 6, "low": 2, "high": 9}
