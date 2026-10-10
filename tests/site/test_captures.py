import datetime as dt
import json
import math
import sqlite3

from apartments.site import captures, estimate

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


def candidate(n, **kw):
    c = {
        "capture_id": f"refresh:abc:{n}",
        "building_id": BUILDING,
        "unit_id": "u-4b",
        "canonical_unit_url": "https://streeteasy.com/building/grove/4b",
        "source_listing_id": 1000 + n,
        "listing_status": "ACTIVE",
        "price_basis": "gross_advertised_rent",
        "rent": 4000,
        "bedrooms": 1,
        "bathrooms": 1,
        "square_feet": None,
        "physical_floor": None,
        "advertised_floor": None,
        "collected_at": "2026-10-06T15:00:00+00:00",
    }
    return {**c, **kw}


def write_capture(archives, name, rows):
    path = archives / name / "details" / "snapshot"
    path.mkdir(parents=True)
    (path / "candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


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


def test_only_captures_the_dataset_never_read(tmp_path):
    write_capture(tmp_path, "20261004", [candidate(1), candidate(2, unit_id="u-5")])
    write_capture(tmp_path, "20261006", [candidate(3, unit_id="u-6")])
    # The dataset read the Oct 4 capture (one of its rows is a dataset row),
    # so its other listing was left out by the dataset's rules.
    got = captures.captures(tmp_path, {"capture:refresh:abc:1"}, set(), {})
    assert [(d, c["capture_id"]) for d, c in got] == [("20261006", "refresh:abc:3")]


def test_the_datasets_current_row_rules_apply(tmp_path):
    write_capture(
        tmp_path,
        "20261006",
        [
            candidate(1, unit_id="u-1"),
            candidate(2, unit_id="u-2", listing_status="RENTED"),
            candidate(3, unit_id="u-3", rent=None),
            candidate(4, unit_id="u-4", furnished=True),
            candidate(5, unit_id="u-5", concession=True),
            candidate(6, unit_id="u-6", bedrooms=1.5),
            candidate(7, unit_id="u-7", rent=600),
            candidate(8, unit_id="u-8", price_basis="net_effective_rent"),
            candidate(9, unit_id="u-9", source_listing_id=777),
            candidate(10, unit_id="u-10"),
            candidate(11, unit_id="u-11", square_feet=90),
        ],
    )
    got = captures.captures(
        tmp_path, set(), {"777"}, {"u-10": dt.datetime(2026, 10, 6, 15, tzinfo=dt.UTC)}
    )
    assert [c["capture_id"] for _, c in got] == ["refresh:abc:1", "refresh:abc:11"]
    assert got[1][1]["square_feet"] is None  # outside 150-6000 sq ft


def test_newest_capture_wins_per_unit(tmp_path):
    write_capture(tmp_path, "20261006", [candidate(1, rent=4000)])
    write_capture(
        tmp_path, "20261008", [candidate(2, source_listing_id=1001, rent=3900)]
    )
    got = captures.captures(tmp_path, set(), set(), {})
    assert [(d, c["rent"]) for d, c in got] == [("20261008", 3900)]


def test_a_capture_ages_out_a_week_after_it_was_seen(tmp_path):
    write_capture(tmp_path, "20261006", [candidate(1)])
    seen = dt.datetime(2026, 10, 6, 15, tzinfo=dt.UTC)
    assert captures.captures(tmp_path, set(), set(), {}, seen + dt.timedelta(days=7))
    assert not captures.captures(
        tmp_path, set(), set(), {}, seen + dt.timedelta(days=7, seconds=1)
    )


def test_a_listing_the_dataset_dropped_stays_out(tmp_path):
    write_capture(tmp_path, "20261006", [candidate(1, source_listing_id=900)])
    dropped = fitted(audit_id="obs:dropped", listing_id="900")
    out, status = captures.rows(
        kit(),
        [kit_building()],
        [fitted(listing_id="800")],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        tmp_path,
        [],
        {"obs:1": fitted(listing_id="800"), "obs:dropped": dropped},
    )
    assert out == [] and status["priced"] == 0


def test_a_newer_capture_wins_over_the_datasets_current_row(tmp_path):
    write_capture(tmp_path, "20261006", [candidate(1, rent=3300)])
    buildings = [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}]

    def priced(seen):
        row = fitted(is_current=1, collected_at=seen, price_at=seen)
        out, _ = captures.rows(
            kit(), [kit_building()], [row], buildings, tmp_path, [], {"obs:1": row}
        )
        return len(out)

    assert priced("2026-10-06T16:00:00+00:00") == 0  # the dataset saw it later
    assert priced("2026-10-06T15:00:00+00:00") == 0  # the same sighting
    assert priced("2026-10-05T00:00:00+00:00") == 1  # the capture is newer
    assert priced("2026-09-20T00:00:00+00:00") == 1  # seen over a week ago


def kit_building(level=0.0):
    return {
        "building": BUILDING,
        "level": [level] * 4,
        "bedroom_slope": [0.0] * 4,
        "fslope": [[0.0]] * 4,
    }


def test_rows_price_a_capture_with_the_kit(tmp_path):
    write_capture(tmp_path, "20261006", [candidate(1, rent=3300)])
    out, status = captures.rows(
        kit(sigma=0.05, unit_scale=0.05),
        [kit_building()],
        [fitted(), fitted(audit_id="obs:2", in_fit=0)],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        tmp_path,
        [],
    )
    assert status["priced"] == 1 and status["by_capture"] == {"20261006": 1}
    (row,) = out
    assert row["audit_id"] == "capture:refresh:abc:1"
    assert row["method"] == "kit" and row["in_fit"] == 0 and row["fitted"] is None
    assert row["neighbourhood"] == "Greenwich Village"
    assert row["is_current"] == 1 and row["collected_at"].startswith("2026-10-06")
    assert row["unit_fit_rows"] == 1
    assert row["floor"] is None  # the ad states none; the page reads the label
    assert 2800 < row["estimate"] < 3300  # the market rent of 3000
    total = sum(p["usd"] for p in json.loads(row["contributions"]))
    assert abs(total - row["estimate"]) < 1
    assert "market" in {p["term"] for p in json.loads(row["contributions"])}


def test_a_building_outside_the_fit_is_skipped(tmp_path):
    write_capture(tmp_path, "20261006", [candidate(1, building_id="b-new")])
    out, status = captures.rows(
        kit(),
        [kit_building()],
        [fitted()],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        tmp_path,
        [],
    )
    assert out == [] and status["skipped"] == {
        "refresh:abc:1": "building not in the served fit"
    }


def test_no_kit_prices_nothing(tmp_path):
    rows, status = captures.price(None, [], [], tmp_path, [])
    assert rows == [] and status["priced"] == 0


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


def test_a_unit_the_fit_has_seen_is_priced_at_its_own_level(tmp_path):
    write_capture(tmp_path, "20261006", [candidate(1, rent=3300)])
    args = (
        kit(sigma=0.05, unit_scale=0.05),
        [kit_building()],
        [fitted()],
        [{"id": BUILDING, "neighbourhood": "Greenwich Village", "floors": 6}],
        tmp_path,
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
