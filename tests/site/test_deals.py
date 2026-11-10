"""The Deals page: ads on the market ordered by how low the ask is for the apartment."""

import hashlib
import json

from apartments.site import deals

ROWS = [
    {
        "listing_id": "11",
        "url": "https://streeteasy.com/rental/11",
        "building": "b-1",
        "address": "10 West 9th Street",
        "unit": "#4B",
        "neighbourhood": "west-village",
        "bedrooms": 1.0,
        "status": "ACTIVE",
        "ask": 3000.0,
        "months_free": 1.0,
        "days_on_market": 3.0,
        "model_median": 3600.0,
        "model_lo80": 3300.0,
        "model_hi80": 3900.0,
        "below_share": 0.012,
        "unit_ads": 4,
    },
    {
        "listing_id": "12",
        "url": "https://streeteasy.com/rental/12",
        "building": "b-2",
        "unit": "",
        "neighbourhood": "Harlem",
        "bedrooms": 4.0,
        "status": "TEMPORARILY_OFF_MARKET",
        "ask": 5000.0,
        "months_free": None,
        "days_on_market": 40.0,
        "model_median": 6500.0,
        "model_lo80": 4500.0,
        "model_hi80": 8600.0,
        "below_share": 0.2,
        "unit_ads": 0,
    },
    {
        "listing_id": "13",
        "url": "https://streeteasy.com/rental/13",
        "building": "b-3",
        "unit": "#2",
        "neighbourhood": "chelsea",
        "bedrooms": 0.0,
        "status": "ACTIVE",
        "ask": 4000.0,
        "days_on_market": None,
        "model_median": 3000.0,
        "model_lo80": 2800.0,
        "model_hi80": 3300.0,
        "below_share": 0.99,
        "unit_ads": 2,
    },
    # No score: left out.
    {"listing_id": "14", "ask": 2000.0, "model_median": 2100.0, "below_share": None},
]
# The shape `drift_deals publish` writes, with a backtest that missed the gate: the page
# reads a few of these keys and must not mind the rest.
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


def publish(site_root, rows=ROWS, meta=META, validation=VALIDATION):
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_keeps_scored_rows_and_words_the_backtest(site_root):
    assert deals.load(site_root) is None
    publish(site_root)
    data = deals.load(site_root)
    assert [r["listing_id"] for r in data["rows"]] == ["11", "12", "13"]
    first = data["rows"][0]
    assert round(first["lower_than"], 1) == 98.8
    assert round(first["gap_pct"], 1) == 16.7
    assert first["hood_label"] == "West Village"
    assert data["hoods"] == [
        ("chelsea", "Chelsea"),
        ("Harlem", "Harlem"),
        ("west-village", "West Village"),
    ]
    bands = [v["lower_than"] for v in data["validation"]["by_first_ask_place"]]
    assert bands == ["90% to 100%", "0% to 10%"]


def test_choose_filters_and_orders():
    rows = deals.load_rows(ROWS)
    every = lambda **kw: [  # noqa: E731
        r["listing_id"] for r in deals.choose(rows, cautioned=True, **kw)
    ]
    assert every() == ["11", "12", "13"]
    assert every(sort="discount") == ["12", "11", "13"]
    assert every(sort="new") == ["11", "12", "13"]
    assert every(beds=3) == ["12"] and every(beds=0) == ["13"]
    assert every(max_rent=4000) == ["11", "13"]
    assert every(hood="chelsea") == ["13"]
    assert every(known=True) == ["11", "13"]
    # Ad 12 is off the market for now: a caution, so the list leaves it out unless asked.
    ids = lambda **kw: [r["listing_id"] for r in deals.choose(rows, **kw)]  # noqa: E731
    assert ids() == ["11", "13"] and ids(beds=3) == []
    assert deals.choice({"beds": "7", "max": "x", "sort": "nope", "known": "1"}) == {
        "beds": None,
        "max_rent": None,
        "hood": None,
        "known": True,
        "cautioned": False,
        "sort": "score",
    }
    assert (
        deals.choice({"all": "1"})["cautioned"]
        and not deals.choice({"all": "0"})["cautioned"]
    )


def test_cautions_are_worded_from_the_tables_codes():
    words = lambda **row: deals.caution_words(row)  # noqa: E731
    assert (
        words() == [] and words(cautions=None) == [] and words(cautions="income") == []
    )
    assert words(cautions=["income", "beds", "income", "new-code", 7]) == [
        deals.CAUTIONS["income"],
        deals.CAUTIONS["beds"],
    ]
    # A table from before the cautions, and one with them, say an ad is off the market once.
    off = deals.CAUTIONS["off_market"]
    assert words(status="TEMPORARILY_OFF_MARKET") == [off]
    assert words(status="TEMPORARILY_OFF_MARKET", cautions=["off_market"]) == [off]


def test_page_shows_the_table_the_backtest_and_the_model(client, site_root):
    assert client.get("/deals").status_code == 503
    publish(site_root)
    response = client.get("/deals")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        "10 West 9th Street · #4B" in html
        and "https://streeteasy.com/rental/11" in html
    )
    assert "$3,000" in html and "$3,300 to $3,900" in html
    assert "98.8%" in html and "1 month free" in html
    # The ad off the market is left out, and the page says so and links to the full list.
    assert "<strong>2</strong> of 3 ads on the market" in html and "Nov 9, 2026" in html
    assert "1 more is left out for a caution" in html and "rental/12" not in html
    assert 'href="/deals?all=1"' in html and "Check first" not in html
    assert "90% to 100%" in html and "9,000 ads" in html and "Nov 10, 2025" in html
    assert "drift-building" in html and "189,647" in html and "81%" in html
    assert html.index("rental/11") < html.index("rental/13")
    assert 'aria-current="page">Deals</a>' in html
    filtered = client.get("/deals?beds=0&sort=discount").get_data(as_text=True)
    assert "rental/13" in filtered and "rental/11" not in filtered
    assert "<strong>1</strong> of 3 ads on the market" in filtered
    assert "left out for a caution" not in filtered
    full = client.get("/deals?all=1&sort=score").get_data(as_text=True)
    assert "<strong>3</strong> of 3 ads on the market" in full
    assert full.index("rental/11") < full.index("rental/12") < full.index("rental/13")
    assert "Check first: temporarily off the market." in full
    assert "left out for a caution" not in full
    # The link to the full list keeps the other filters.
    kept = client.get("/deals?beds=3&sort=new").get_data(as_text=True)
    assert "<strong>0</strong> of 3" in kept and "1 more is left out" in kept
    assert 'href="/deals?beds=3&amp;sort=new&amp;all=1"' in kept


def test_page_stands_without_meta_or_backtest(client, site_root):
    publish(site_root, meta=None, validation=None)
    html = client.get("/deals").get_data(as_text=True)
    assert "rental/11" in html and "Does a low ask mean anything" not in html


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
        "unit_ads": None,
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
    assert "over 99.9%" in html and "100.0%" not in html
    assert "b-9" in html


def test_bad_query_strings_and_a_replaced_file(client, site_root):
    publish(site_root)
    response = client.get("/deals?beds=x&max=-5&sort=zzz&hood=nope&known=7")
    assert response.status_code == 200
    assert "No ad on the market matches" in response.get_data(as_text=True)
    assert client.get("/deals?max=1e999&beds=1.5").status_code == 200
    # A newly published table replaces the cached one.
    publish(site_root, rows=ROWS[:1])
    html = client.get("/deals").get_data(as_text=True)
    assert "<strong>1</strong> of 1 ad on the market" in html


def test_a_meta_or_backtest_from_another_publish_is_not_shown(client, site_root):
    publish(site_root)
    folder = site_root / "deals"
    # A new table lands before its meta: the old meta and backtest say nothing about it.
    (folder / "deals.json").write_text(json.dumps(ROWS[:2]))
    data = deals.load(site_root)
    assert len(data["rows"]) == 2 and data["meta"] == {}
    assert data["validation"]["by_first_ask_place"] == []
    html = client.get("/deals").get_data(as_text=True)
    assert "drift-building" not in html and "Does a low ask mean anything" not in html
    # A backtest the meta does not name is left out, and the meta stays.
    publish(site_root)
    (folder / "validation.json").write_text(json.dumps(VALIDATION | {"as_of": "x"}))
    data = deals.load(site_root)
    assert data["meta"]["run"] == "run-x"
    assert data["validation"]["by_first_ask_place"] == []


def test_page_says_when_the_backtest_fit_missed_the_gate(client, site_root):
    missed = "missed the project's convergence test"
    publish(site_root)
    assert missed in client.get("/deals").get_data(as_text=True)
    passed = META | {"gate": META["gate"] | {"backtest": META["gate"]["market"]}}
    for meta in (passed, {k: v for k, v in META.items() if k != "gate"}):
        publish(site_root, meta=meta)
        html = client.get("/deals").get_data(as_text=True)
        assert "Does a low ask mean anything" in html and missed not in html
    # A gate that is not what publish writes says nothing.
    for gate in ("x", [1], {"backtest": "no"}, {"backtest": {"passes": 0}}):
        publish(site_root, meta=META | {"gate": gate})
        assert missed not in client.get("/deals").get_data(as_text=True)
