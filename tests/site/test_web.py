"""The app as a whole: its sections, headers, health check and the URLs it serves."""

import gzip
import itertools
import json
import re
from pathlib import Path

import pytest

from apartments.site import charts
from apartments.site.web import create_app

from .conftest import write_estimates
from .test_deals import publish
from .test_workbench import write_diagnostics

GROVE = "the-grove-250-west-19th-street-new_york"
TEMPLATES = Path(charts.__file__).parent / "templates"

ABSENT = [
    "/best",
    "/best.csv",
    "/buildings",
    f"/buildings/{GROVE}",
    "/buildings.json?q=grove",
    "/units/u1",
    "/quarantined",
    "/estimate",
    "/estimates/map",
    "/estimates/map.json",
    "/research",
    "/research/model",
    "/research/story",
    "/research/board",
    "/research/frontier",
    "/research/glossary",
    "/research/designs",
    "/research/history",
    "/research/validation",
    "/research/elegance",
    "/research/data",
    "/research/plan",
]


def published_root(tmp_path: Path, *, diagnostics: bool = True) -> Path:
    """A site root holding the published folders and no sqlite build."""
    root = tmp_path / "published"
    root.mkdir()
    publish(root)
    write_estimates(root)
    if diagnostics:
        write_diagnostics(root)
    return root


@pytest.fixture
def published(tmp_path):
    app = create_app(published_root(tmp_path))
    app.config["TESTING"] = True
    return app.test_client()


def current_section(html: str) -> list[str]:
    nav = html.split('class="sections">', 1)[1].split("</nav>", 1)[0]
    return re.findall(r'aria-current="true">([^<]+)</a>', nav)


def test_the_home_page_is_the_deals_page(published):
    home = published.get("/")
    assert home.status_code == 200
    page = home.get_data(as_text=True)
    assert "<h1>Deals</h1>" in page
    deals = published.get("/deals").get_data(as_text=True)
    assert re.findall(r'href="/listings/(\d+)"', page) == re.findall(
        r'href="/listings/(\d+)"', deals
    )
    # The brand and the Deals section link both point at `/`.
    assert 'class="brand" href="/">NYC Rents</a>' in page
    assert '<a href="/" aria-current="true">Deals</a>' in deals
    assert "· NYC Rents</title>" in page


@pytest.mark.parametrize("path", ABSENT)
def test_other_urls_are_plain_404s(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert b"Not found" in response.data


def test_not_found(client):
    assert client.get("/listings/zzz").status_code == 404
    response = client.get("/no-such-page")
    assert response.status_code == 404 and b"Back to Deals" in response.data


@pytest.mark.parametrize(
    ("path", "section"),
    [
        ("/", "Deals"),
        ("/deals", "Deals"),
        ("/estimates", "Estimates"),
        ("/listings", "Estimates"),
        ("/listings/1004", "Deals"),
        ("/listings/1001", "Estimates"),
        ("/about", "Estimates"),
        ("/workbench", "Workbench"),
        ("/workbench/signals", "Workbench"),
        ("/workbench/triage", "Workbench"),
        ("/workbench/buildings", "Workbench"),
        ("/tags", "Tags"),
    ],
)
def test_each_page_marks_its_section_current(published, path, section):
    response = published.get(path)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert current_section(page) == [section]
    nav = page.split('class="sections">', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r">([^<]+)</a>", nav) == [
        "Deals",
        "Estimates",
        "Workbench",
        "Review",
        "Tags",
    ]


def test_the_estimates_subnav_has_its_four_links(published):
    page = published.get("/about").get_data(as_text=True)
    subnav = page.split('aria-label="Estimates">', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r'href="([^"]+)"', subnav) == [
        "/estimates",
        "/listings",
        "/new-jersey",
        "/about",
    ]
    assert '<a href="/about" aria-current="page">How it works</a>' in subnav
    assert 'class="subnav"' not in published.get("/").get_data(as_text=True)
    assert 'class="subnav"' not in published.get("/tags").get_data(as_text=True)


def test_the_published_folders_are_enough_to_serve(tmp_path):
    root = published_root(tmp_path)
    assert not (root / "current").exists()
    client = create_app(root).test_client()
    for path in (
        "/",
        "/deals",
        "/estimates",
        "/listings",
        "/listings.csv",
        "/listings/1004",
        "/workbench",
        "/workbench/signals",
        "/workbench/triage",
        "/workbench/buildings",
        "/tags",
        "/tags.csv",
        "/about",
        "/healthz",
    ):
        assert client.get(path).status_code == 200, path
    # The Hoboken and Jersey City page reads the sqlite build alone, so it is empty.
    observed = client.get("/new-jersey")
    assert observed.status_code == 200
    assert "/listings/" not in observed.get_data(as_text=True)


def test_about_reads_the_diagnostics_meta(tmp_path):
    root = published_root(tmp_path)
    path = root / "diagnostics" / "meta.json"
    meta = json.loads(path.read_text())
    meta["model_terms"] = ["bedrooms", "building level", "unit level"]
    meta["coverage"] = {"50": 0.512, "80": 0.81, "95": 0.947}
    meta["counts"] = {
        "ads": {"all": 6400, "latest": 5200, "market": 1200},
        "buildings": 310,
        "history": 41000,
    }
    path.write_text(json.dumps(meta))
    response = create_app(root).test_client().get("/about")
    assert response.status_code == 200
    page = " ".join(response.get_data(as_text=True).split())
    assert "<h1>How it works</h1>" in page
    assert "The 3 terms of the model" in page and "<li>unit level</li>" in page
    assert "Nov 9, 2026" in page
    assert "6,400 held-out ads in 310 buildings" in page
    assert "worst R-hat 1.004" in page and "worst R-hat 1.006" in page
    assert "81.0% for the 80% range" in page
    assert "No diagnostics are published yet" not in page
    main = page.split("<main", 1)[1].split("</main>", 1)[0]
    renter, statistician = main.split('<details class="card statistician"', 1)
    assert len(re.sub(r"<[^>]+>", " ", "<main" + renter).split()) < 700
    # The renter's sections come first, in plain words.
    for heading in (
        "Reading a gap",
        "The cautious saving",
        "The range bar",
        "The Evidence chip",
        "Cautions and flags",
    ):
        assert f"<h2>{heading}</h2>" in renter
    assert "Bayesian" not in renter and "R-hat" not in renter
    assert "$300/mo" in renter and "unit history, 3 ads" in renter
    assert "Read the ad on StreetEasy" in renter
    assert "Compare the ask with the building&#39;s other asks" in renter.replace(
        "'", "&#39;"
    )
    for label in ("suspect gap", "off market", "price/ft²", "building side"):
        assert f'<span class="chip warn-chip">{label}</span>' in renter
    assert "at building&#39;s asks</span>" in renter
    # The statistical description sits in a closed block.
    assert "<summary>For the statistician</summary>" in statistician
    assert "Bayesian" in statistician and "worst R-hat 1.004" in statistician
    assert "The 3 terms of the model" in statistician


def test_about_renders_without_diagnostics(tmp_path):
    root = published_root(tmp_path, diagnostics=False)
    response = create_app(root).test_client().get("/about")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "No diagnostics are published yet" in page
    assert 'id="held-out"' in page and "R-hat" not in page
    # A root with nothing published still explains the model.
    empty = create_app(tmp_path / "empty").test_client().get("/about")
    assert empty.status_code == 200
    assert "Model outputs, not appraisals" in empty.get_data(as_text=True)


def test_templates_link_only_to_views_the_app_has():
    views = set(create_app(TEMPLATES.parent / "no-root").view_functions)
    pattern = re.compile(r"""(?:url_for|page_url|sort_url)\(\s*['"]([A-Za-z_.]+)['"]""")
    linked = {
        (template.name, name)
        for template in sorted(TEMPLATES.glob("*.html"))
        for name in pattern.findall(template.read_text())
    }
    assert linked
    assert sorted(pair for pair in linked if pair[1] not in views) == []


def test_the_footer_names_the_model_when_a_meta_is_published(published, tmp_path):
    foot = published.get("/tags").get_data(as_text=True).split("<footer", 1)[1]
    assert "<code>drift-building</code>" in foot and "Nov 9, 2026" in foot
    assert "Model outputs, not appraisals: they describe asking rents." in foot
    bare = create_app(tmp_path / "empty").test_client().get("/tags")
    assert bare.status_code == 200
    foot = bare.get_data(as_text=True).split("<footer", 1)[1]
    assert "<code>" not in foot and "Model outputs, not appraisals" in foot


def test_security_and_cache_headers(published):
    response = published.get("/")
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-cache"
    etag = response.headers["ETag"]
    assert published.get("/", headers={"If-None-Match": etag}).status_code == 304
    static = published.get("/static/site.css?v=1")
    assert "max-age=31536000" in static.headers["Cache-Control"]
    static.close()


def test_untrusted_host_is_refused(client):
    assert client.get("/listings", headers={"Host": "evil.example"}).status_code == 400
    trusted = client.get("/listings", headers={"Host": "thelio.example.ts.net:8600"})
    assert trusted.status_code == 200


def test_gzip_when_accepted(client):
    response = client.get("/listings", headers={"Accept-Encoding": "gzip"})
    assert response.headers["Content-Encoding"] == "gzip"
    assert b"NYC Rents" in gzip.decompress(response.data)


def test_healthz_counts_the_published_tables(published):
    response = published.get("/healthz")
    body = response.get_json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert body["model"] == "drift-building" and body["scoring_day"] == "2026-11-09"
    assert body["deals"] > 0 and body["estimates"] > 0
    assert response.headers["Cache-Control"] == "no-store"


def test_nothing_published_is_503(tmp_path):
    client = create_app(tmp_path / "empty").test_client()
    response = client.get("/")
    assert response.status_code == 503 and b"No deals table" in response.data
    assert client.get("/estimates").status_code == 503
    health = client.get("/healthz")
    assert health.status_code == 503 and health.get_json()["status"] == "error"


def test_a_new_publish_is_served_without_restart(tmp_path):
    root = published_root(tmp_path)
    client = create_app(root).test_client()
    first = client.get("/healthz").get_json()["deals"]
    publish(root, rows=json.loads((root / "deals" / "deals.json").read_text())[:1])
    assert first > 1 and client.get("/healthz").get_json()["deals"] == 1


def test_robots(client):
    assert client.get("/robots.txt").get_data(as_text=True).endswith("Disallow: /\n")


def test_nice_ticks_cover_the_range():
    ticks = charts.nice_ticks(2830.0, 5310.0)
    assert ticks[0] <= 2830 and ticks[-1] >= 5310
    steps = {round(b - a, 6) for a, b in itertools.pairwise(ticks)}
    assert len(steps) == 1 and steps.pop() in (500.0, 1000.0)


def test_money_and_percent_formatting():
    assert charts.usd(-885.4, signed=True) == "−$885"
    assert charts.usd(1200) == "$1,200"
    assert charts.pct(-19.1, digits=1) == "−19.1%"
    assert charts.pct(0.0) == "0%"


def test_values_that_round_to_zero_carry_no_sign():
    assert charts.pct(-0.3) == "0%"
    assert charts.pct(-0.04, digits=1) == "0.0%"
    assert charts.pct(-0.6) == "−1%"
    assert charts.usd(-0.4, signed=True) == "$0"
    assert charts.usd(-27, signed=True) == "−$27"


def test_a_market_ad_sits_under_deals_and_a_past_ad_under_estimates(published):
    market = " ".join(published.get("/listings/1004").get_data(as_text=True).split())
    crumbs = market.split('class="crumbs"', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r">([^<]+)</a>", crumbs) == ["Deals"]
    assert 'aria-current="page">250 West 19th Street' in crumbs
    assert 'class="subnav"' not in market

    past = " ".join(published.get("/listings/1001").get_data(as_text=True).split())
    crumbs = past.split('class="crumbs"', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r">([^<]+)</a>", crumbs) == ["Estimates", "Past ads"]
    assert 'class="subnav"' in past


def test_embedded_chart_data_escapes_angle_brackets():
    text = charts.embed_json({"label": "</script><b>", "n": 1})
    assert "<" not in text
    assert json.loads(text) == {"label": "</script><b>", "n": 1}


@pytest.mark.parametrize(
    "path", ["/", "/estimates", "/listings", "/listings/1004", "/about", "/tags"]
)
def test_pages_spell_neighborhoods_the_american_way(published, path):
    page = published.get(path).get_data(as_text=True)
    assert "eighbour" not in re.sub(r'(href|name|value|id|for|class)="[^"]*"', "", page)


def phone_rules() -> str:
    css = (Path(charts.__file__).parent / "static" / "site.css").read_text()
    blocks = re.findall(r"@media \(max-width: 640px\) \{(.*?)\n\}", css, flags=re.S)
    return "\n".join(blocks)


@pytest.mark.parametrize(
    "selector",
    [
        ".top nav a",
        ".subnav a",
        ".results-links a",
        ".pager a",
        "details.tag-compact > summary.tag-summary",
        ".tag-clear",
        ".tag-form select",
        ".tag-form button",
    ],
)
def test_phone_tap_targets_are_forty_pixels_tall(selector):
    rules = [
        body
        for names, body in re.findall(r"([^{}]+)\{([^{}]*)\}", phone_rules())
        if selector in [n.strip() for n in names.split(",")]
    ]
    assert any("min-height: 40px" in body for body in rules), selector


def test_phone_rules_stack_the_tags_table_and_size_chart_text():
    rules = phone_rules()
    assert re.search(r"table\.tags-table tr \{[^}]*display: grid", rules)
    assert re.search(r"\.history-chart svg \{[^}]*width: 640px", rules)
    assert re.search(r"\.history-chart \{[^}]*overflow-x: auto", rules)
