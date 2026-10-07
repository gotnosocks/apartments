import json
import math
import sqlite3

from apartments.site import captures, estimate

BUILDING = "b-grove"


def kit(sigma=1e-6, unit_scale=1e-6, draws=4):
    """A kit of no features: every apartment asks the market rent of 3000."""
    return estimate.Kit.from_record(
        {
            "period": "2026-09-01",
            "features": [],
            "groups": [],
            "slopes": ["log_sqft_vs_bedroom_median"],
            "market": [math.log(3000)] * draws,
            "season": {"daily": True, "coef": [[0.0] * 4] * draws},
            "beta": [[]] * draws,
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


def test_only_active_listings_of_captures_the_dataset_never_read(tmp_path):
    write_capture(
        tmp_path,
        "20261004",
        [candidate(1), candidate(2, source_listing_id=2002)],
    )
    write_capture(
        tmp_path,
        "20261006",
        [
            candidate(3),
            candidate(4, listing_status="RENTED"),
            candidate(5, rent=None),
            candidate(6, source_listing_id=777),
        ],
    )
    # The dataset read the Oct 4 capture (one of its rows is a site row), so
    # its other listing was left out by the dataset's rules.
    got = captures.captures(tmp_path, {"capture:refresh:abc:1", "777"})
    assert [(d, c["capture_id"]) for d, c in got] == [("20261006", "refresh:abc:3")]


def test_newest_capture_wins_per_listing(tmp_path):
    write_capture(tmp_path, "20261006", [candidate(1, rent=4000)])
    write_capture(
        tmp_path, "20261008", [candidate(2, source_listing_id=1001, rent=3900)]
    )
    got = captures.captures(tmp_path, set())
    assert [(d, c["rent"]) for d, c in got] == [("20261008", 3900)]


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
