"""The Today section: each apartment's price on the publish's day, as
`rentfrontier.drift_today publish` writes it into the site's `today/` folder."""

import hashlib
import json
import re

import duckdb
import pytest

from apartments.site import today
from apartments.site.web import create_app


def row(listing, building, unit, beds, last_ask, median, **kw):
    out = dict(
        apartment=f"{building}|{unit or ''}",
        building=building,
        address=kw.pop("address", "134 West 23rd Street"),
        latitude=40.74,
        longitude=-73.99,
        neighbourhood=kw.pop("neighbourhood", "chelsea"),
        unit_id=f"unit:{listing}" if unit else None,
        unit=unit or "",
        bedrooms=float(beds),
        full_baths=1.0,
        half_baths=0.0,
        listing_id=listing,
        last_day=kw.pop("last_day", "2024-05-01"),
        last_ask=float(last_ask),
        on_market=kw.pop("on_market", False),
        unit_ads=kw.pop("unit_ads", 2),
        median=float(median),
        lo95=0.8 * median,
        lo80=0.88 * median,
        lo50=0.95 * median,
        hi50=1.05 * median,
        hi80=1.12 * median,
        hi95=1.2 * median,
        unit_sd=0.05,
    )
    out.update(kw)
    return out


ROWS = [
    row("2001", "134-west-23-street-new_york", "6B", 1, 3000, 3300),
    row(
        "2002",
        "134-west-23-street-new_york",
        "7A",
        2,
        4200,
        4600,
        last_day="2026-11-05",
        on_market=True,
    ),
    row("2003", "134-west-23-street-new_york", None, 0, 2200, 2400, unit_ads=0),
    row(
        "2004",
        "10-bank-street-new_york",
        "2",
        3,
        8000,
        9100,
        address="10 Bank Street",
        neighbourhood="west-village",
    ),
]

META = {
    "model": "drift-building",
    "run": "drift-market-run",
    "dataset": "b0-market",
    "gate": {"passes": True, "max_rhat": 1.0064, "min_ess": 1426, "chains": 6},
    "scoring_day": "2026-11-09",
    "day": "2026-11-13",
    "last_ad_day": "2026-11-09",
    "grid_start": "2013-12-02",
    "grid_end": "2026-11-09",
    "weeks_past_grid": 0.57,
    "walk": {"drift_per_week": 0.0008, "step_sd_per_week": 0.004, "added_sd": 0.003},
    "draws": {"kept": 96, "burn": 4, "keep": 2},
    "apartments": {"all": 4, "on_market": 1, "unseen": 1},
    "check": {
        "rows": 6774,
        "elpd": {"today": 5100.2, "fit": 5101.0},
        "median_gap": {"median_abs": 0.002, "p95_abs": 0.01, "mean": 0.0},
        "width80_ratio": 1.01,
        "coverage": {"today": {"80": 0.79}, "fit": {"80": 0.795}},
    },
}


def write(root, rows=ROWS, **meta):
    folder = root / "today"
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "rows.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in rows))
    path = folder / "today.parquet"
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * FROM read_json_auto('{source}')) TO '{path}' (FORMAT parquet)"
    )
    con.close()
    source.unlink()
    m = META | meta
    m.setdefault("today_sha256", hashlib.sha256(path.read_bytes()).hexdigest())
    (folder / "meta.json").write_text(json.dumps(m))


@pytest.fixture
def client(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    write(root)
    app = create_app(root)
    app.config["TESTING"] = True
    return app.test_client()


def _links(page: str) -> list[str]:
    return re.findall(r'href="/price-now/(\d+)"', page)


def test_the_page_says_the_day_the_model_and_how_far_it_extrapolates(client):
    page = client.get("/price-now").get_data(as_text=True)
    assert "November 13, 2026" in page or "Nov 13, 2026" in page
    assert "drift-building" in page and "drift-market-run" in page
    assert "The market trend stops before today" in page
    assert "4 days" in page
    # the check against the fit's own predictions
    assert "6,774" in page and "1.01 times" in page
    # nothing is listed until the reader searches
    assert _links(page) == []


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("q=134+west", ["2001", "2002", "2003"]),
        ("q=134+west&unit=6-b", ["2001"]),
        ("q=https://streeteasy.com/building/134-west-23-street-new_york/7a", ["2002"]),
        ("q=streeteasy.com/rental/2004", ["2004"]),
        ("q=2003", ["2003"]),
        ("q=bank&go=list", ["2004"]),
        ("which=market", ["2002"]),
        ("which=known&sort=low", ["2001", "2002", "2004"]),
        ("beds=0&beds=3&sort=high", ["2004", "2003"]),
        ("min=3000&max=5000&sort=low", ["2001", "2002"]),
        ("nb=West+Village&go=list", ["2004"]),
    ],
)
def test_search(client, query, expected):
    response = client.get(f"/price-now?{query}")
    if len(expected) == 1 and "go=list" not in query:
        assert response.status_code == 302
        assert response.headers["Location"].endswith(f"/price-now/{expected[0]}")
        return
    page = response.get_data(as_text=True)
    assert [k for k in dict.fromkeys(_links(page))] == expected


def test_an_apartment_shows_todays_middle_ranges_and_its_last_ask(client):
    page = client.get("/price-now/2001").get_data(as_text=True)
    assert "134 West 23rd Street · 6B" in page
    assert "$3,300" in page and "$2,904 to $3,696" in page
    assert "$3,000" in page and "+10%" in page
    assert "https://streeteasy.com/rental/2001" in page
    assert "learned from 2 ads" in page
    # the building's other apartments
    assert 'href="/price-now/2002"' in page and 'href="/price-now/2003"' in page
    assert 'href="/price-now/2004"' not in page


def test_an_apartment_on_the_market_and_one_the_model_never_saw(client):
    page = client.get("/price-now/2002").get_data(as_text=True)
    assert "on the market now" in page and "whose ask it did not see" in page
    page = client.get("/price-now/2003").get_data(as_text=True)
    assert "priced as a new apartment in its building" in page


def test_unknown_apartment_is_404_and_a_mismatched_table_503(client, tmp_path):
    assert client.get("/price-now/9999").status_code == 404
    root = tmp_path / "other"
    root.mkdir()
    write(root, today_sha256="0" * 64)
    app = create_app(root)
    assert app.test_client().get("/price-now").status_code == 503
    empty = tmp_path / "empty"
    empty.mkdir()
    assert create_app(empty).test_client().get("/price-now").status_code == 503


def test_parse_query():
    assert today.parse_query("12345") == {"listing": "12345"}
    assert today.parse_query("https://streeteasy.com/rental/4471234") == {
        "listing": "4471234"
    }
    assert today.parse_query("streeteasy.com/building/the-eugene/52a?featured=1") == {
        "slug": "the-eugene",
        "unit": "52a",
    }
    assert today.parse_query("10 Bank St") == {"text": "10 Bank St"}
    assert today.unit_key("#6-B") == "6b"
