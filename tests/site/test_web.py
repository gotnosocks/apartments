import csv
import gzip
import io
import itertools

import pytest

from apartments.site import charts
from apartments.site.web import create_app

GROVE = "the-grove-250-west-19th-street-new_york"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/listings",
        "/listings?status=current",
        "/listings/a1",
        "/listings/a3",
        "/units/u1",
        "/units/u2",
        "/buildings",
        f"/buildings/{GROVE}",
        "/model",
    ],
)
def test_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"Chelsea rents" in response.data


def listed(client, query=""):
    """audit ids of the listing links on a /listings page, in order."""
    html = client.get("/listings" + query).get_data(as_text=True)
    return [part.split('"')[0] for part in html.split('href="/listings/')[1:]]


def test_listing_filters(client):
    assert listed(client) == ["a3", "a4", "a2", "a1", "a6", "a5"]  # newest first
    assert listed(client, "?status=current") == ["a3"]
    assert listed(client, "?status=past&beds=0") == ["a6", "a5"]
    assert listed(client, "?beds=2&beds=4") == ["a4"]
    assert listed(client, "?price=below") == ["a2"]
    assert listed(client, "?price=above") == ["a4"]
    assert listed(client, "?min_ask=3000&max_ask=%243%2C500") == ["a3", "a1"]
    assert listed(client, "?from=2019&to=2021") == ["a2", "a1"]
    assert listed(client, "?q=grove") == ["a3", "a4", "a2", "a1"]
    assert listed(client, "?q=23rd") == ["a6", "a5"]
    assert listed(client, "?q=11-c") == ["a3"]  # exact unit label
    assert listed(client, "?sort=ask") == ["a5", "a6", "a2", "a1", "a3", "a4"]
    assert listed(client, "?sort=diff_pct&order=desc")[0] == "a4"


def test_invalid_parameters_fall_back_to_defaults(client):
    default = listed(client)
    for query in (
        "?page=abc&per=7",
        "?sort=ask;DROP TABLE listings&order=sideways",
        "?beds=9&status=nope&price=cheap",
        "?min_ask=-5&max_ask=nan&from=12&to=abcd",
        "?q=%25%25%25_",
    ):
        response = client.get("/listings" + query)
        assert response.status_code == 200
        if "q=" not in query:
            assert listed(client, query) == default
    assert listed(client, "?q=%25") == []  # a literal %, not a wildcard


def test_pagination(client):
    html = client.get("/listings?per=25&page=99").get_data(as_text=True)
    assert "Page" not in html  # one page only; out-of-range pages clamp


def test_csv_export_follows_the_filters(client):
    response = client.get("/listings.csv?q=grove&sort=ask")
    assert response.status_code == 200 and response.mimetype == "text/csv"
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert [r["audit_id"] for r in rows] == ["a2", "a1", "a3", "a4"]
    assert rows[0]["price_band"] == "below" and float(rows[0]["ask"]) == 2600.0


def test_listing_page_explains_the_estimate(client):
    html = client.get("/listings/a3").get_data(as_text=True)
    assert "Less reliable estimate" in html
    assert (
        "the unit&#39;s 2 other listings" in html or "unit's 2 other listings" in html
    )
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html  # data is escaped
    assert "<script>alert(1)</script>" not in html
    assert "renovated" in html and "penthouse" in html
    assert "At their reference level, adding nothing: Bedrooms" in html
    single = client.get("/listings/a4").get_data(as_text=True)
    assert "only listing" in single and "Above typical" in single
    held = client.get("/listings/a2").get_data(as_text=True)
    assert "held out of the model fit" in held


def test_building_page(client):
    html = client.get(f"/buildings/{GROVE}").get_data(as_text=True)
    assert "The Grove" in html and "250 West 19th Street" in html
    assert "+10%" in html and "Built" in html and "1986" in html
    assert 'data-chart="points"' in html
    current = client.get(f"/buildings/{GROVE}?status=current").get_data(as_text=True)
    assert current.count('href="/listings/') == 1


def test_buildings_index_search_and_sort(client):
    html = client.get("/buildings?q=west+23").get_data(as_text=True)
    assert "134 West 23rd Street" in html and "The Grove" not in html
    html = client.get("/buildings?sort=level&order=desc").get_data(as_text=True)
    assert html.index("The Grove") < html.index("134 West 23rd Street")


def test_not_found(client):
    assert client.get("/listings/zzz").status_code == 404
    assert client.get("/units/zzz").status_code == 404
    assert client.get("/buildings/zzz").status_code == 404
    response = client.get("/no-such-page")
    assert response.status_code == 404 and b"Not found" in response.data


def test_security_and_cache_headers(client):
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-cache"
    etag = response.headers["ETag"]
    assert client.get("/", headers={"If-None-Match": etag}).status_code == 304
    static = client.get("/static/site.css?v=1")
    assert "max-age=31536000" in static.headers["Cache-Control"]
    static.close()


def test_untrusted_host_is_refused(client):
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert (
        client.get("/", headers={"Host": "thelio.example.ts.net:8600"}).status_code
        == 200
    )


def test_gzip_when_accepted(client):
    response = client.get("/listings", headers={"Accept-Encoding": "gzip"})
    assert response.headers["Content-Encoding"] == "gzip"
    assert b"Chelsea rents" in gzip.decompress(response.data)


def test_healthz(client):
    response = client.get("/healthz")
    body = response.get_json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert body["listings"] == 6 and body["run"] == "m-test-run"
    assert response.headers["Cache-Control"] == "no-store"


def test_no_published_build_is_503(tmp_path):
    app = create_app(tmp_path / "empty")
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 503 and b"Not available yet" in response.data
    assert client.get("/healthz").status_code == 503


def test_a_new_publish_is_served_without_restart(client, site_root, bundle):
    from apartments.site import build

    first = client.get("/healthz").get_json()["build"]
    build.build(bundle, site_root)
    assert client.get("/healthz").get_json()["build"] != first


def test_robots(client):
    assert client.get("/robots.txt").get_data(as_text=True).endswith("Disallow: /\n")


def test_nice_ticks_cover_the_range():
    ticks = charts.nice_ticks(2830.0, 5310.0)
    assert ticks[0] <= 2830 and ticks[-1] >= 5310
    steps = {round(b - a, 6) for a, b in itertools.pairwise(ticks)}
    assert len(steps) == 1 and steps.pop() in (500.0, 1000.0)


def test_chart_data_block_cannot_close_its_script():
    figure = charts.residual_scatter(
        [{"period": "2020-01-01", "residual_pct": 0.1, "title": "</script><b>x"}],
        label="t",
    )
    assert "</script><b>" not in str(figure).split('class="chart-data">')[1][:-20]


def test_money_and_percent_formatting():
    assert charts.usd(-885.4, signed=True) == "−$885"
    assert charts.usd(1200) == "$1,200"
    assert charts.pct(-19.1, digits=1) == "−19.1%"
    assert charts.pct(0.0) == "0%"
