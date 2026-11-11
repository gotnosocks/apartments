"""The rebuilt Deals page: cautious saving order, basis population, filters and diagnostics."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import duckdb

from apartments.site import deals

ROWS = [
    # 11: unit history (4 ads), 1 month free ($3,250 gross, $3,000 net, no net cut),
    # cautious saving = (3300 - 3000) / 3300 = 9.09% ($300/mo).
    {
        "listing_id": "11",
        "url": "https://streeteasy.com/rental/11",
        "building": "b-1",
        "address": "10 West 9th Street",
        "unit": "4B",
        "neighbourhood": "west-village",
        "bedrooms": 1.0,
        "full_baths": 1.0,
        "half_baths": 0.0,
        "square_feet": 720.0,
        "status": "ACTIVE",
        "ask": 3000.0,
        "first_ask": 3250.0,
        "page_price": 3250.0,
        "months_free": 1.0,
        "days_on_market": 3.0,
        "model_median": 3600.0,
        "model_lo95": 3100.0,
        "model_lo80": 3300.0,
        "model_lo50": 3450.0,
        "model_hi50": 3750.0,
        "model_hi80": 3900.0,
        "model_hi95": 4150.0,
        "below_share": 0.012,
        "unit_ads": 4,
    },
    # 12: off market (caution), no unit history.
    {
        "listing_id": "12",
        "url": "https://streeteasy.com/rental/12",
        "building": "b-2",
        "unit": "",
        "neighbourhood": "Harlem",
        "bedrooms": 4.0,
        "full_baths": 2.0,
        "half_baths": 0.0,
        "square_feet": 1400.0,
        "status": "TEMPORARILY_OFF_MARKET",
        "ask": 5000.0,
        "months_free": None,
        "days_on_market": 40.0,
        "model_median": 6500.0,
        "model_lo80": 5600.0,
        "model_hi80": 8600.0,
        "below_share": 0.08,
        "unit_ads": 0,
    },
    # 13: unit history (2 ads), price cut from $4,400 to $4,000, above middle.
    {
        "listing_id": "13",
        "url": "https://streeteasy.com/rental/13",
        "building": "b-3",
        "address": "200 Eighth Avenue",
        "unit": "2F",
        "neighbourhood": "chelsea",
        "bedrooms": 0.0,
        "full_baths": 1.0,
        "half_baths": 0.0,
        "square_feet": 480.0,
        "status": "ACTIVE",
        "ask": 4000.0,
        "first_ask": 4400.0,
        "days_on_market": None,
        "model_median": 3000.0,
        "model_lo80": 2800.0,
        "model_hi80": 3300.0,
        "below_share": 0.99,
        "unit_ads": 2,
    },
    # 15: building basis in diagnostics (unit_ads 0, building_ads 8), tight range:
    # cautious saving = (3500 - 2900) / 3500 = 17.14% ($600/mo), gap 23.7% <= 35%.
    {
        "listing_id": "15",
        "url": "https://streeteasy.com/rental/15",
        "building": "b-5",
        "address": "88 Wythe Avenue",
        "unit": "6A",
        "neighbourhood": "Williamsburg",
        "bedrooms": 2.0,
        "full_baths": 1.0,
        "half_baths": 1.0,
        "square_feet": 950.0,
        "status": "ACTIVE",
        "ask": 2900.0,
        "first_ask": 3300.0,
        "days_on_market": 9.0,
        "model_median": 3800.0,
        "model_lo80": 3500.0,
        "model_hi80": 4150.0,
        "below_share": 0.02,
        "unit_ads": 0,
    },
    # 16: suspect gap (unit_ads 0, building_ads 9, ask $7,250 vs middle $26,848 -> 73% under).
    {
        "listing_id": "16",
        "url": "https://streeteasy.com/rental/16",
        "building": "b-6",
        "address": "1259 Jefferson Avenue",
        "unit": "1A",
        "neighbourhood": "Bushwick",
        "bedrooms": 3.0,
        "full_baths": 2.0,
        "half_baths": 0.0,
        "square_feet": 1600.0,
        "status": "ACTIVE",
        "ask": 7250.0,
        "days_on_market": 13.0,
        "model_median": 26848.0,
        "model_lo80": 22724.0,
        "model_hi80": 31993.0,
        "below_share": 0.0006,
        "unit_ads": 0,
    },
    # 17: area-only basis (unit_ads 0, building_ads 1), wide range:
    # gap_pct 25% > row 11's 16.7%, yet model_lo80 is $2,700 so cautious saving is 0!
    {
        "listing_id": "17",
        "url": "https://streeteasy.com/rental/17",
        "building": "b-7",
        "address": "55 Bedford Street",
        "unit": "3R",
        "neighbourhood": "west-village",
        "bedrooms": 1.0,
        "full_baths": 1.0,
        "half_baths": 0.0,
        "square_feet": 600.0,
        "status": "ACTIVE",
        "ask": 2700.0,
        "days_on_market": 1.0,
        "model_median": 3600.0,
        "model_lo80": 2700.0,
        "model_hi80": 4800.0,
        "below_share": 0.10,
        "unit_ads": 0,
    },
    # 14: missing score, dropped on load.
    {"listing_id": "14", "ask": 2000.0, "model_median": 2100.0, "below_share": None},
]

META = {
    "model": "drift-building",
    "run": "run-x",
    "gate": {
        "market": {"passes": True, "max_rhat": 1.004, "min_ess": 1034.0, "chains": 4},
        "heldout": {"passes": True, "max_rhat": 1.005, "min_ess": 1207.0, "chains": 4},
        "backtest": {"passes": False, "max_rhat": 1.07, "min_ess": 18.0, "chains": 4},
    },
    "scoring_day": "2026-11-09",
    "ads": 6774,
    "published": "2026-11-10T12:00:00Z",
    "heldout": {
        "rows": 189647,
        "elpd": 230884.75,
        "median_abs_error": 0.041,
        "rmse": 0.0825,
        "bias": -0.005,
        "coverage": {"50": 0.52, "80": 0.81, "90": 0.9, "95": 0.95},
        "run": "run-h",
        "split": "latest",
    },
    "backtest_run": "run-k",
}

VALIDATION = {
    "as_of": "2025-11-10",
    "ads_with_first_ask": 9000,
    "by_first_ask_place": [
        {
            "place": "0.0 to 0.1",
            "ads": 700,
            "median_days_on_market": 12.0,
            "share_within_14_days": 0.55,
            "share_cut": 0.08,
            "share_raised": 0.11,
        },
        {
            "place": "0.9 to 1.0",
            "ads": 1100,
            "median_days_on_market": 48.0,
            "share_within_14_days": 0.12,
            "share_cut": 0.51,
            "share_raised": 0.01,
        },
    ],
}

DIAG_ADS = [
    {
        "listing_id": "11",
        "unit_id": "u-11",
        "unit": "4B",
        "unit_ads": 4,
        "building_ads": 12,
        "basis": "unit",
        "floor": 4.0,
        "flags": [],
    },
    {
        "listing_id": "12",
        "unit_id": "u-12",
        "unit": "5C",
        "unit_ads": 0,
        "building_ads": 6,
        "basis": "building",
        "floor": 5.0,
        "flags": [],
    },
    {
        "listing_id": "13",
        "unit_id": "u-13",
        "unit": "2F",
        "unit_ads": 2,
        "building_ads": 7,
        "basis": "unit",
        "floor": 2.0,
        "flags": ["ask_jump"],
    },
    {
        "listing_id": "15",
        "unit_id": "u-15",
        "unit": "6A",
        "unit_ads": 0,
        "building_ads": 8,
        "basis": "building",
        "floor": 6.0,
        "flags": ["ppsf"],
    },
    {
        "listing_id": "16",
        "unit_id": "u-16",
        "unit": "1A",
        "unit_ads": 0,
        "building_ads": 9,
        "basis": "building",
        "floor": 1.0,
        "flags": ["extreme"],
    },
    {
        "listing_id": "17",
        "unit_id": "u-17",
        "unit": "3R",
        "unit_ads": 0,
        "building_ads": 1,
        "basis": "area",
        "floor": 3.0,
        "flags": [],
    },
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(site_root: Path, rows=ROWS, meta=META, validation=VALIDATION) -> None:
    folder = site_root / "deals"
    folder.mkdir(exist_ok=True)
    (folder / "deals.json").write_text(json.dumps(rows))
    stamps = {"deals_sha256": sha(folder / "deals.json")}
    (folder / "validation.json").unlink(missing_ok=True)
    if validation is not None:
        (folder / "validation.json").write_text(json.dumps(validation))
        stamps["validation_sha256"] = sha(folder / "validation.json")
    (folder / "meta.json").unlink(missing_ok=True)
    if meta is not None:
        (folder / "meta.json").write_text(json.dumps(meta | stamps))


def publish_diagnostics(
    site_root: Path,
    ads: list[dict] = DIAG_ADS,
    bad_sha: bool = False,
) -> None:
    folder = site_root / "diagnostics"
    folder.mkdir(exist_ok=True)
    ads_path = folder / "ads.parquet"
    hist_path = folder / "history.parquet"
    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TABLE a (listing_id VARCHAR, unit_id VARCHAR, unit VARCHAR, "
            "unit_ads BIGINT, building_ads BIGINT, basis VARCHAR, floor DOUBLE, "
            "flags VARCHAR[])"
        )
        for r in ads:
            con.execute(
                "INSERT INTO a VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    r["listing_id"],
                    r["unit_id"],
                    r["unit"],
                    r["unit_ads"],
                    r["building_ads"],
                    r["basis"],
                    r["floor"],
                    r["flags"],
                ],
            )
        con.execute(f"COPY a TO '{ads_path}' (FORMAT parquet)")
        con.execute(
            "CREATE TABLE h (listing_id VARCHAR, building VARCHAR, unit_id VARCHAR, "
            "unit VARCHAR, day DATE, ask DOUBLE, bedrooms DOUBLE, full_baths DOUBLE, "
            "heldout BOOLEAN)"
        )
        con.execute(f"COPY h TO '{hist_path}' (FORMAT parquet)")
    finally:
        con.close()
    meta = {
        "model": "drift-building",
        "sha256": {
            "ads.parquet": "0" * 64 if bad_sha else sha(ads_path),
            "history.parquet": sha(hist_path),
        },
    }
    (folder / "meta.json").write_text(json.dumps(meta))


def listed_ids(html: str) -> list[str]:
    return re.findall(r'href="/listings/([^"]+)"', html)


def test_load_computes_cautious_saving_cuts_and_borough_groups(site_root):
    assert deals.load(site_root) is None
    publish(site_root)
    data = deals.load(site_root)
    assert data is not None and not data["has_diagnostics"]
    assert [r["listing_id"] for r in data["rows"]] == [
        "11",
        "12",
        "13",
        "15",
        "16",
        "17",
    ]

    by_id = {r["listing_id"]: r for r in data["rows"]}
    # Row 11: 1 month free ($3,250 gross, $3,000 net), first ask $3,250 -> no net cut.
    assert round(by_id["11"]["cautious_saving"], 4) == round(300.0 / 3300.0, 4)
    assert by_id["11"]["cautious_usd"] == 300.0
    assert by_id["11"]["cut_usd"] is None
    assert by_id["11"]["basis_badge"] == "unit history, 4 ads"

    # Row 13: real $400 price cut from $4,400 to $4,000.
    assert by_id["13"]["cut_usd"] == 400.0

    # Row 16: no unit history and >35% under middle -> suspect.
    assert by_id["16"]["suspect"] is True
    assert by_id["11"]["suspect"] is False

    assert set(data["hood_groups"]) == {"Manhattan", "Brooklyn", "Other"}
    bands = [v["lower_than"] for v in data["validation"]["by_first_ask_place"]]
    assert bands == ["90% to 100%", "0% to 10%"]


def test_default_population_and_orders_without_and_with_diagnostics(site_root):
    publish(site_root)
    without_diag = deals.load(site_root)["rows"]
    # Without diagnostics, only unit_ads > 0 (11, 13) qualify for default basis.
    assert [r["listing_id"] for r in deals.choose(without_diag)] == ["11", "13"]
    # Including area-only adds 15 and 17 (while 16 stays suspect and 12 stays cautioned).
    assert [r["listing_id"] for r in deals.choose(without_diag, area=True)] == [
        "15",
        "11",
        "17",
        "13",
    ]
    # Notice cautious order puts 11 ($300/mo under lo80) ahead of 17 ($0 under lo80),
    # whereas discount order puts 17 (25% under middle) ahead of 11 (17% under middle).
    assert [
        r["listing_id"] for r in deals.choose(without_diag, area=True, sort="discount")
    ] == ["17", "15", "11", "13"]

    # With diagnostics, building-basis ad 15 (8 building ads) enters default population,
    # while suspect building-basis ad 16 (73% under) and area-only ad 17 stay hidden.
    publish_diagnostics(site_root)
    with_diag = deals.load(site_root)["rows"]
    assert [r["listing_id"] for r in deals.choose(with_diag)] == ["15", "11", "13"]
    assert [r["listing_id"] for r in deals.choose(with_diag, suspect=True)] == [
        "16",
        "15",
        "11",
        "13",
    ]
    assert [
        r["listing_id"]
        for r in deals.choose(with_diag, area=True, suspect=True, cautioned=True)
    ] == ["16", "15", "12", "11", "17", "13"]
    assert [
        r["listing_id"] for r in deals.choose(with_diag, area=True, sort="score")
    ] == ["11", "15", "17", "13"]
    assert [
        r["listing_id"] for r in deals.choose(with_diag, area=True, sort="new")
    ] == ["17", "11", "15", "13"]


def test_url_filters_for_hoods_beds_rent_sqft_floor_and_toggles(client, site_root):
    publish(site_root)
    publish_diagnostics(site_root)

    # Default page shows 15, 11, 13 in cautious saving order.
    html = client.get("/deals").get_data(as_text=True)
    assert listed_ids(html) == ["15", "11", "13"]
    assert "88 Wythe Avenue · 6A" in html and "building, 8 ads" in html
    assert "unit history, 4 ads" in html
    assert "$600/mo" in html and "$300/mo" in html
    assert "$3,250 on ad, 1 mo free" in html
    assert "−$400" in html and "price/ft²" in html and "ask jump" in html
    assert html.count('class="deal-strip"') == 3
    # Backtest is inside a collapsed <details> block at the bottom.
    assert '<details class="card deals-backtest" id="backtest">' in html
    assert "90% to 100%" in html and "9,000 ads" in html
    # Column headers carry explanatory title tooltips.
    assert '<th scope="col" class="num" title="Dollars per month below' in html

    # Multi-neighborhood and borough filters in URL.
    two_hoods = client.get("/deals?hood=Chelsea&hood=West+Village").get_data(
        as_text=True
    )
    assert listed_ids(two_hoods) == ["11", "13"]
    brooklyn = client.get("/deals?hood=Brooklyn").get_data(as_text=True)
    assert listed_ids(brooklyn) == ["15"]

    # Multiple bedroom counts, max rent, min square feet and floor at least.
    assert listed_ids(client.get("/deals?beds=0&beds=2").get_data(as_text=True)) == [
        "15",
        "13",
    ]
    assert listed_ids(client.get("/deals?max=3000").get_data(as_text=True)) == [
        "15",
        "11",
    ]
    assert listed_ids(client.get("/deals?min_sqft=800").get_data(as_text=True)) == [
        "15"
    ]
    assert listed_ids(client.get("/deals?floor=5").get_data(as_text=True)) == ["15"]

    # Hidden-count links keep active filters in the URL.
    filtered = client.get("/deals?beds=3&sort=new").get_data(as_text=True)
    assert "<strong>0</strong> of 6" in filtered
    assert 'href="/deals?beds=3&amp;suspect=1&amp;sort=new"' in filtered


def test_page_renders_without_diagnostics_and_refuses_bad_diagnostics_sha(
    client, site_root
):
    assert client.get("/deals").status_code == 503
    publish(site_root)
    resp = client.get("/deals")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert listed_ids(html) == ["11", "13"]
    assert "https://streeteasy.com/rental/11" in html
    assert "1 area-only" in html or "2 area-only" in html

    # Corrupted diagnostics sha refuses with 503 rather than mixing files.
    publish_diagnostics(site_root, bad_sha=True)
    bad = client.get("/deals")
    assert bad.status_code == 503
    assert "do not match" in bad.get_data(as_text=True)


def test_cautions_are_worded_and_match_frontier_codes():
    words = lambda **row: deals.caution_words(row)  # noqa: E731
    assert words() == [] and words(cautions=None) == [] and words(cautions=[]) == []
    assert words(cautions={"income": 1}) == [] and words(cautions=[7, None, ""]) == []
    assert words(cautions="income") == [deals.CAUTIONS["income"]]
    assert words(cautions=["income", "beds", "income", "new-code", 7]) == [
        deals.CAUTIONS["income"],
        deals.CAUTIONS["beds"],
        "a caution this page has no words for (new-code)",
    ]
    off = deals.CAUTIONS["off_market"]
    assert words(status="TEMPORARILY_OFF_MARKET") == [off]
    assert words(status="TEMPORARILY_OFF_MARKET", cautions=["off_market"]) == [off]

    source = Path(__file__).parents[2] / "frontier/src/rentfrontier/cautions.py"
    spec = importlib.util.spec_from_file_location("frontier_cautions", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(deals.CAUTIONS) == set(module.CODES)
    assert deals.OFF_MARKET == module.OFF_MARKET


def test_rows_with_missing_names_and_foreign_links(client, site_root):
    bare = {
        "listing_id": "21",
        "url": "javascript:alert(1)",
        "building": "b-9",
        "address": None,
        "unit": None,
        "neighbourhood": "nan",
        "bedrooms": None,
        "ask": 2500.0,
        "months_free": None,
        "days_on_market": None,
        "model_median": 3000.0,
        "model_lo80": None,
        "model_hi80": None,
        "below_share": 0.0,
        "unit_ads": 1,
    }
    odd = bare | {
        "listing_id": "x<y",
        "url": "https://example.com/rental/22",
        "address": "<script>alert(2)</script>",
        "neighbourhood": "<b>soho</b>",
        "below_share": 0.3,
    }
    rows = deals.load_rows([bare, odd])
    assert [r["url"] for r in rows] == ["https://streeteasy.com/rental/21", None]
    assert rows[0]["neighbourhood"] is None and rows[0]["lower_words"] == "over 99.9%"
    publish(site_root, rows=[bare, odd])
    assert deals.load(site_root)["hoods"] == [("<b>soho</b>", "<B>Soho</B>")]
    html = client.get("/deals").get_data(as_text=True)
    assert "Nan" not in html and "javascript:" not in html and "example.com" not in html
    assert "<script>alert(2)" not in html and "&lt;script&gt;alert(2)" in html
    assert "<b>soho</b>" not in html and "<B>Soho</B>" not in html
    assert "b-9" in html


def test_bad_query_strings_replaced_files_and_backtest_gate(client, site_root):
    publish(site_root)
    response = client.get(
        "/deals?beds=x&max=-5&min_sqft=-1&floor=0&sort=zzz&hood=nope&area=7"
    )
    assert response.status_code == 200
    assert "No ad on the market matches" in response.get_data(as_text=True)
    assert client.get("/deals?max=1e999&beds=1.5").status_code == 200

    # Backtest convergence warning shows only when backtest gate failed.
    missed = "missed the convergence test"
    assert missed in client.get("/deals").get_data(as_text=True)
    passed = META | {"gate": META["gate"] | {"backtest": META["gate"]["market"]}}
    publish(site_root, meta=passed)
    html = client.get("/deals").get_data(as_text=True)
    assert 'id="backtest"' in html and missed not in html

    # Unmatched meta/validation hashes drop out when deals.json is replaced alone.
    folder = site_root / "deals"
    (folder / "deals.json").write_text(json.dumps(ROWS[:1]))
    data = deals.load(site_root)
    assert len(data["rows"]) == 1 and data["meta"] == {}
    assert data["validation"]["by_first_ask_place"] == []
    bare_html = client.get("/deals").get_data(as_text=True)
    assert 'id="backtest"' not in bare_html and "drift-building" not in bare_html
