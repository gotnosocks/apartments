import datetime as dt
import json
import math
import sqlite3
from pathlib import Path

import pytest

from apartments.site import ad_dates, captures, estimate

BUILDING = "b-grove"


def kit(sigma=1e-6, unit_scale=1e-6, draws=4, features=()):
    """A kit whose terms are all zero: every apartment asks the market rent
    of 3000."""
    return estimate.Kit.from_record(
        {
            "period": "2026-09-01",
            "features": [n for n, _ in features],
            "groups": [g for _, g in features],
            "slopes": ["log_sqft_vs_bedroom_median"],
            "market": [math.log(3000)] * draws,
            "season": {"daily": True, "coef": [[0.0] * 4] * draws},
            "beta": [[0.0] * len(features)] * draws,
            "bedroom_time": [[0.0] * 4] * draws,
            "sigma": [[sigma] * 4] * draws,
            "nu": [1e6] * draws,
            "unit_scale": [unit_scale] * draws,
            "unit_nu": [5.0] * draws,
            "t_units": True,
        },
        {"1": math.log(700)},
    )


URL = "https://streeteasy.com/building/grove/4b"
SEEN = dt.datetime(2026, 10, 6, 15, tzinfo=dt.UTC)


def ad(n, **kw):
    """An ad on the market, in the columns of the pipeline's ads and rows files."""
    a = {
        "listing_id": str(1000 + n),
        "unit_id": "u-4b",
        "building": BUILDING,
        "page": URL,
        "response_id": 7,
        "fetched": SEEN,
        "status": "ACTIVE",
        "page_price": 4000.0,
        "bedrooms": 1.0,
        "bathrooms": 1.0,
    }
    return {**a, **kw}


def candidate(n, **kw):
    """An ad as `captures.current_ads` gives it."""
    c = {
        "listing_id": str(1000 + n),
        "unit_id": "u-4b",
        "building_id": BUILDING,
        "unit_url": URL,
        "response_id": 7,
        "collected_at": SEEN.isoformat(),
        "ask": 4000.0,
        "bedrooms": 1.0,
        "bathrooms": 1.0,
        "square_feet": None,
    }
    return {**c, **kw}


def fitted(**kw):
    r = {
        "audit_id": "obs:1",
        "unit_id": "u-4b",
        "building_id": BUILDING,
        "listing_id": "900",
        "period": "2026-08-01",
        "price_at": "2026-08-03T00:00:00+00:00",
        "collected_at": None,
        "is_current": 0,
        "in_fit": 1,
        "bedrooms": 1,
        "square_feet": None,
        "inputs": json.dumps({}),
    }
    return {**r, **kw}


def test_label_floor_reads_the_unit_number_within_the_buildings_height():
    assert captures.label_floor("https://x/building/a/23C", 30) == 23
    assert captures.label_floor("https://x/building/a/apt-4b", 6) == 4
    assert captures.label_floor("https://x/building/a/307", 6) == 3
    assert captures.label_floor("https://x/building/a/23C", 10) is None
    assert captures.label_floor("https://x/building/a/PH", 10) is None
    assert captures.label_floor("https://x/building/a/2A", None) is None


def test_no_catalog_gives_no_pipeline_files(pipeline):
    assert captures.pipeline_files(pipeline.root) is None


def test_the_newest_build_in_the_catalog_gives_the_files(pipeline):
    pipeline.write([ad(1)])
    files = pipeline.write([ad(1), ad(2, unit_id="u-5")])
    assert captures.pipeline_files(pipeline.root) == files
    assert files["ads"].endswith(f"/ads-{files['ads_sha256'][:16]}.parquet")


def test_a_file_unlike_the_catalog_stops_the_build(pipeline):
    files = pipeline.write([ad(1)])
    Path(files["rows"]).write_bytes(b"another file")
    with pytest.raises(ValueError, match="differs from the pipeline's catalog"):
        captures.pipeline_files(pipeline.root)


def test_the_catalog_skips_a_line_still_being_written(pipeline):
    files = pipeline.write([ad(1)])
    with (pipeline.root / "catalog.ndjson").open("a") as f:
        f.write('{"built": "2026-10-07')
    assert captures.pipeline_files(pipeline.root) == files


def test_the_catalog_skips_a_build_from_a_checkout_with_changes(pipeline):
    files = pipeline.write([ad(1)])
    pipeline.write([ad(1), ad(2, unit_id="u-5")])
    catalog = pipeline.root / "catalog.ndjson"
    first, second = catalog.read_text().splitlines()
    entry = json.loads(second)
    entry["code"]["clean"] = False
    catalog.write_text(first + "\n" + json.dumps(entry) + "\n")
    assert captures.pipeline_files(pipeline.root) == files
    catalog.write_text(json.dumps(entry) + "\n")
    assert captures.pipeline_files(pipeline.root) is None


def test_a_build_without_an_ads_file_stops_the_build(pipeline):
    pipeline.write([ad(1)])
    catalog = pipeline.root / "catalog.ndjson"
    entry = json.loads(catalog.read_text().splitlines()[-1])
    del entry["ads_file"]
    with catalog.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    with pytest.raises(ValueError, match="has no ads_file"):
        captures.pipeline_files(pipeline.root)


def test_the_datasets_current_row_rules_apply(pipeline):
    ads = [
        ad(1, unit_id="u-1"),
        ad(2, unit_id="u-2", status="RENTED"),
        ad(3, unit_id="u-3", page_price=None),
        ad(4, unit_id="u-4"),
        ad(6, unit_id="u-6", bedrooms=1.5),
        ad(7, unit_id="u-7", page_price=600.0),
        ad(9, unit_id="u-9", listing_id="777"),
        ad(10, unit_id="u-10"),
    ]
    # The pipeline gives ad 1004 no fit-ready row.
    files = pipeline.write(ads, [a for a in ads if a["unit_id"] != "u-4"])
    got, skipped = captures.current_ads(files, {"777"}, {"u-10": SEEN})
    assert [c["listing_id"] for c in got] == ["1001"]
    assert skipped == {
        "1003": "layout or ask outside the dataset's range",
        "1004": "the ad has no fit-ready row",
        "1006": "layout or ask outside the dataset's range",
        "1007": "layout or ask outside the dataset's range",
        "777": "the dataset dropped the listing",
        "1010": "the dataset prices the unit as current",
    }


def test_an_ad_takes_its_values_from_its_row_and_its_ask_from_its_page(pipeline):
    a = ad(
        1,
        page_price=3300.0,
        asking_rent=3500.0,
        square_feet=640.0,
        full_baths=1,
        half_baths=1,
        physical_floor=4.0,
        elevator=True,
        view_exposures='{"city": true}',
    )
    files = pipeline.write([a], [{**a, "bedrooms": 2.0}])
    ((c,), skipped) = captures.current_ads(files, set(), {})
    assert skipped == {} and c["ask"] == 3300 and c["bedrooms"] == 2
    assert c["square_feet"] == 640 and (c["full_baths"], c["half_baths"]) == (1, 1)
    assert c["physical_floor"] == 4 and c["elevator"] is True
    assert c["view_exposures"] == {"city": True} and c["window_exposures"] is None
    assert c["collected_at"] == "2026-10-06T15:00:00+00:00"
    assert (c["building_id"], c["unit_url"], c["response_id"]) == (BUILDING, URL, 7)


def test_the_ad_fetched_last_wins_per_unit(pipeline):
    """The files hold the older ad first, so the order comes from the reader."""
    files = pipeline.write(
        [ad(1, response_id=6, fetched=SEEN - dt.timedelta(days=1)), ad(2)]
    )
    got, skipped = captures.current_ads(files, set(), {})
    assert [c["listing_id"] for c in got] == ["1002"] and skipped == {}


def test_a_unit_with_an_ad_the_dataset_dropped_has_none(pipeline):
    """The unit's other ads agree with the dropped one, so they repeat its values."""
    files = pipeline.write(
        [ad(2), ad(1, response_id=6, fetched=SEEN - dt.timedelta(days=1))]
    )
    for dropped, other in (("1002", "1001"), ("1001", "1002")):
        got, skipped = captures.current_ads(files, {dropped}, {})
        assert got == []
        assert skipped == {
            dropped: "the dataset dropped the listing",
            other: "the dataset dropped another ad of the unit",
        }


def test_a_unit_takes_its_newest_ad_with_a_row(pipeline):
    """The files hold the ads from oldest to newest, so the order comes from the reader."""
    ads = [
        ad(1, response_id=5, fetched=SEEN - dt.timedelta(days=2)),
        ad(2, response_id=6, fetched=SEEN - dt.timedelta(days=1)),
        ad(3),
    ]
    files = pipeline.write(ads, ads[:2])
    got, skipped = captures.current_ads(files, set(), {})
    assert [c["listing_id"] for c in got] == ["1002"]
    assert skipped == {"1003": "the ad has no fit-ready row"}


def test_a_unit_whose_ads_on_the_market_conflict_has_none(pipeline):
    files = pipeline.write([ad(1), ad(2, page_price=3900.0), ad(3, unit_id="u-5")])
    got, skipped = captures.current_ads(files, set(), {})
    assert [c["listing_id"] for c in got] == ["1003"]
    assert skipped == {
        "1001": "the unit's ads on the market conflict",
        "1002": "the unit's ads on the market conflict",
    }


def test_an_ad_without_a_row_conflicts_too(pipeline):
    """The ads file's values decide the conflict, and an ad without a fit-ready row counts."""
    ads = [ad(1), ad(2, bedrooms=2.0), ad(3, unit_id="u-5")]
    files = pipeline.write(ads, [ads[0], ads[2]])
    got, skipped = captures.current_ads(files, set(), {})
    assert [c["listing_id"] for c in got] == ["1003"]
    assert skipped == {
        "1001": "the unit's ads on the market conflict",
        "1002": "the unit's ads on the market conflict",
    }


def test_ads_without_a_unit_stay_out(pipeline):
    ads = [
        ad(1, unit_id=None),
        ad(2, unit_id=None, page_price=3900.0),
        ad(3, unit_id="u-5"),
    ]
    got, skipped = captures.current_ads(pipeline.write(ads), set(), {})
    assert [c["listing_id"] for c in got] == ["1003"] and skipped == {}


def test_an_ad_ages_out_nine_days_after_it_was_fetched(pipeline):
    files = pipeline.write([ad(1)])

    def current(at):
        return [c["listing_id"] for c in captures.current_ads(files, set(), {}, at)[0]]

    assert current(SEEN + dt.timedelta(days=9)) == ["1001"]
    assert current(SEEN + dt.timedelta(days=9, seconds=1)) == []
    assert current(SEEN - dt.timedelta(seconds=1)) == []  # fetched after the build


def test_a_listing_the_dataset_dropped_stays_out(pipeline):
    files = pipeline.write([ad(1, listing_id="900")])
    dropped = fitted(audit_id="obs:dropped", listing_id="900")
    out, status = captures.rows(
        kit(),
        [kit_building()],
        [fitted(listing_id="800")],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        files,
        [],
        {"obs:1": fitted(listing_id="800"), "obs:dropped": dropped},
    )
    assert out == [] and status["priced"] == 0


def test_a_newer_ad_wins_over_the_datasets_current_row(pipeline):
    files = pipeline.write([ad(1, page_price=3300.0)])
    buildings = [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}]

    def priced(seen):
        row = fitted(is_current=1, collected_at=seen, price_at=seen)
        out, _ = captures.rows(
            kit(), [kit_building()], [row], buildings, files, [], {"obs:1": row}
        )
        return len(out)

    assert priced("2026-10-06T16:00:00+00:00") == 0  # the dataset saw it later
    assert priced("2026-10-06T15:00:00+00:00") == 0  # the same sighting
    assert priced("2026-10-05T00:00:00+00:00") == 1  # the ad is newer
    assert priced("2026-09-20T00:00:00+00:00") == 1  # seen over a week ago


def kit_building(level=0.0):
    return {
        "building": BUILDING,
        "level": [level] * 4,
        "bedroom_slope": [0.0] * 4,
        "fslope": [[0.0]] * 4,
    }


def test_rows_price_an_ad_with_the_kit(pipeline):
    files = pipeline.write([ad(1, page_price=3300.0)])
    out, status = captures.rows(
        kit(sigma=0.05, unit_scale=0.05),
        [kit_building()],
        [fitted(), fitted(audit_id="obs:2", in_fit=0)],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        files,
        [],
    )
    assert status["priced"] == 1 and status["pipeline"] == files
    (row,) = out
    assert row["audit_id"] == "api:7:1001" and row["listing_id"] == "1001"
    assert row["ask"] == 3300 and row["price_basis"] == "current_capture_gross_ask"
    assert row["method"] == "kit" and row["in_fit"] == 0 and row["fitted"] is None
    assert row["neighbourhood"] == "Greenwich Village"
    assert row["is_current"] == 1 and row["collected_at"].startswith("2026-10-06")
    assert row["unit_fit_rows"] == 1
    assert row["floor"] is None  # the ad states none; the page reads the label
    assert 2800 < row["estimate"] < 3300  # the market rent of 3000
    total = sum(p["usd"] for p in json.loads(row["contributions"]))
    assert abs(total - row["estimate"]) < 1
    assert "market" in {p["term"] for p in json.loads(row["contributions"])}


def test_a_kit_row_takes_its_dates_on_the_market(pipeline):
    """The build passes the kit's rows and the same files to `ad_dates.collect`."""
    files = pipeline.write(
        [ad(1, on_day=dt.date(2026, 9, 30), days_on_market=6)],
        [ad(1)],
    )
    out, _ = captures.rows(
        kit(),
        [kit_building()],
        [fitted()],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        files,
        [],
    )
    (dated,) = ad_dates.collect(files, out)
    assert (dated["audit_id"], dated["on_market_at"]) == ("api:7:1001", "2026-09-30")
    assert dated["days_on_market"] == 6


def test_a_building_outside_the_fit_is_skipped(pipeline):
    files = pipeline.write([ad(1, building="b-new")])
    out, status = captures.rows(
        kit(),
        [kit_building()],
        [fitted()],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        files,
        [],
    )
    assert out == [] and status["skipped"] == {"1001": "building not in the served fit"}


def test_no_kit_or_pipeline_build_prices_nothing(pipeline):
    rows, status = captures.price(None, [], [], pipeline.write([ad(1)]), [])
    assert rows == [] and status["priced"] == 0
    rows, status = captures.price(pipeline.root, [], [], None, [])
    assert rows == [] and status == {
        "priced": 0,
        "reason": "no pipeline build to read current ads from",
    }


def as_kit_row(site_root):
    """A current fixture listing turned into one the kit priced."""
    db = sqlite3.connect((site_root / "current" / "site.sqlite").resolve())
    audit_id, unit_url = db.execute(
        "SELECT audit_id, unit_url FROM listings WHERE is_current = 1 LIMIT 1"
    ).fetchone()
    db.execute(
        "UPDATE listings SET method = 'kit', in_fit = 0, fitted = NULL, "
        "collected_at = '2026-10-06T15:00:00+00:00' WHERE audit_id = ?",
        (audit_id,),
    )
    db.commit()
    db.close()
    return audit_id


def test_listing_page_says_the_kit_priced_it(site_root, client):
    audit_id = as_kit_row(site_root)
    page = client.get(f"/listings/{audit_id}").get_data(as_text=True)
    assert "Priced with the kit, not in the fit" in page
    assert "priced with the kit, not in the fit (captured 2026-10-06)" in page
    assert "In-sample fit" not in page


UNIT_TERMS = (
    ("first_listing_of_unit", "relisting"),
    ("log_months_since_last_listing", "relisting"),
    ("looks onto an avenue", "facing"),
    ("log_sqft_vs_bedroom_median", "size"),
)


def test_encode_takes_facing_size_and_gap_from_the_units_earlier_listing():
    k = kit(features=UNIT_TERMS)
    prev = fitted(
        price_at="2026-07-07T15:00:00+00:00",
        inputs=json.dumps(
            {"looks onto an avenue": 1.0, "log_sqft_vs_bedroom_median": 0.1}
        ),
    )
    x = captures.encode(k, candidate(1), {}, prev, centre=1.0)
    assert x["looks onto an avenue"] == 1.0
    assert x["log_sqft_vs_bedroom_median"] == 0.1
    assert "first_listing_of_unit" not in x
    assert (
        abs(x["log_months_since_last_listing"] - (math.log1p(91 / 30.4) - 1.0)) < 1e-9
    )


def test_encode_takes_no_size_from_a_listing_with_other_bedrooms():
    prev = fitted(bedrooms=2, inputs=json.dumps({"log_sqft_vs_bedroom_median": 0.1}))
    x = captures.encode(kit(features=UNIT_TERMS), candidate(1), {}, prev, centre=1.0)
    assert x.get("log_sqft_vs_bedroom_median", 0.0) != 0.1


def test_encode_without_a_centre_keeps_the_gap_at_its_average():
    x = captures.encode(
        kit(features=UNIT_TERMS), candidate(1), {}, fitted(), centre=None
    )
    assert "first_listing_of_unit" not in x
    assert x["log_months_since_last_listing"] == 0.0


def test_relisting_centre_is_recovered_from_the_rows():
    rows = [
        fitted(audit_id="a", price_at="2026-01-01T00:00:00+00:00"),
        fitted(
            audit_id="b",
            price_at="2026-03-02T00:00:00+00:00",
            inputs=json.dumps(
                {"log_months_since_last_listing": math.log1p(60 / 30.4) - 3.0}
            ),
        ),
    ]
    assert abs(captures.relisting_centre(rows) - 3.0) < 1e-9


def test_a_unit_the_fit_has_seen_is_priced_at_its_own_level(pipeline):
    args = (
        kit(sigma=0.05, unit_scale=0.05),
        [kit_building()],
        [fitted()],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        pipeline.write([ad(1, page_price=3300.0)]),
        [],
    )
    level = math.log(0.8)
    (row,), status = captures.rows(*args, units={"u-4b": [level] * 4})
    assert status["unit_levels"] == 1
    assert abs(row["estimate"] - 2400) < 1  # 3000 at the unit's own -20%
    parts = json.loads(row["contributions"])
    (unit,) = [p for p in parts if p["term"] == "unit"]
    assert unit["from_fit"] and unit["usd"] < -500
    assert abs(sum(p["usd"] for p in parts) - row["estimate"]) < 1
    # A unit the fit has not seen keeps the prior.
    (row,), status = captures.rows(*args, units={"u-other": [level] * 4})
    assert status["unit_levels"] == 0 and 2800 < row["estimate"] < 3300
    assert "from_fit" not in json.dumps(row["contributions"])


def test_encode_takes_the_description_from_the_same_ad_seen_earlier():
    features = (
        *UNIT_TERMS,
        ("description_missing", "description"),
        ("text:dishwasher", "description"),
        ("outdoor:balcony", "outdoor space"),
        ("rooms beyond bedrooms=unknown", "rooms beyond bedrooms"),
        ("rooms beyond bedrooms=3", "rooms beyond bedrooms"),
    )
    k = kit(features=features)
    text = {
        "text:dishwasher": 1.0,
        "outdoor:balcony": 1.0,
        "rooms beyond bedrooms=3": 1.0,
    }
    same = fitted(listing_id="1001", inputs=json.dumps(text))
    x = captures.encode(k, candidate(1), {}, same, centre=None)
    assert x["text:dishwasher"] == x["outdoor:balcony"] == 1.0
    assert x["rooms beyond bedrooms=3"] == 1.0
    assert "description_missing" not in x
    assert "rooms beyond bedrooms=unknown" not in x
    # Another ad of the unit, or the same ad without its description, gives none.
    for prev in (
        fitted(listing_id="900", inputs=json.dumps(text)),
        fitted(listing_id="1001", inputs=json.dumps({"description_missing": 1.0})),
    ):
        x = captures.encode(k, candidate(1), {}, prev, centre=None)
        assert x["description_missing"] == 1.0 and "text:dishwasher" not in x
        assert x["rooms beyond bedrooms=unknown"] == 1.0


def test_unit_levels_load_from_the_kit_when_it_has_them(tmp_path):
    import duckdb

    from apartments.site import estimate_build

    assert estimate_build.load_units(tmp_path) == {}
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT 'u-4b' AS unit, [0.1, -0.2]::FLOAT[] AS level) "
        f"TO '{tmp_path / 'units.parquet'}' (FORMAT parquet)"
    )
    con.close()
    digest = estimate_build._sha256(tmp_path / "units.parquet")
    (tmp_path / "complete.json").write_text(
        json.dumps({"files": {"units.parquet": digest}})
    )
    got = estimate_build.load_units(tmp_path)
    assert list(got) == ["u-4b"] and [round(v, 6) for v in got["u-4b"]] == [0.1, -0.2]
    (tmp_path / "complete.json").write_text(json.dumps({"files": {}}))
    try:
        estimate_build.load_units(tmp_path)
    except estimate.KitError:
        pass
    else:
        raise AssertionError("an unhashed units.parquet must not load")


def test_listing_page_says_when_the_unit_level_is_the_fits(site_root, client):
    audit_id = as_kit_row(site_root)
    db = sqlite3.connect((site_root / "current" / "site.sqlite").resolve())
    (parts,) = db.execute(
        "SELECT contributions FROM listings WHERE audit_id = ?", (audit_id,)
    ).fetchone()
    parts = [
        {**p, "from_fit": True} if p["term"] == "unit" else p for p in json.loads(parts)
    ]
    if not any(p["term"] == "unit" for p in parts):
        parts.append(
            {"term": "unit", "usd": -5, "lower": -9, "upper": -1, "from_fit": True}
        )
    db.execute(
        "UPDATE listings SET contributions = ? WHERE audit_id = ?",
        (json.dumps(parts), audit_id),
    )
    db.commit()
    db.close()
    page = client.get(f"/listings/{audit_id}").get_data(as_text=True)
    assert "level is the one the fit learned from its" in page
    assert "drawn from the prior" not in page


def test_a_west_coast_ad_is_priced_on_its_labels_wing(pipeline):
    wing, letters = "the-west-coast-west-wing", "the-west-coast"
    url = "https://streeteasy.com/building/the-west-coast/"
    files = pipeline.write(
        [
            ad(1, building=letters, unit_id="u-620", page=url + "620"),
            ad(2, building=letters, unit_id="u-9l", page=url + "9l"),
        ]
    )
    out, status = captures.rows(
        kit(),
        [{**kit_building(), "building": b} for b in (wing, letters)],
        [
            fitted(audit_id="obs:1", building_id=wing),
            fitted(audit_id="obs:2", building_id=letters),
        ],
        [
            {"id": b, "neighbourhood": "West Village", "floors": 10}
            for b in (wing, letters)
        ],
        files,
        [],
    )
    assert status["priced"] == 2 and not status["skipped"]
    assert {r["unit_label"]: r["building_id"] for r in out} == {
        "620": wing,
        "9L": letters,
    }
