import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0ending, drift_building_phase
from rentfrontier.b0data import sha256

BASE = pd.Timestamp("2024-01-01", tz="UTC")
# The opening of listings 14 and 16, five hours into day 40.
T = BASE + pd.Timedelta(days=40, hours=5)


def at(days=0.0, seconds=0.0):
    """A time `days` and `seconds` after BASE, as StreetEasy writes it, in New York time."""
    t = BASE + pd.Timedelta(days=days, seconds=seconds)
    return t.tz_convert("America/New_York").isoformat()


def iso(t):
    return t.tz_convert("America/New_York").isoformat()


# (listing, building, unit_id, price_at in days after BASE)
ROWS = [
    ("1", "a", "1", 0),
    ("2", "a", "1", 60),
    ("3", "a", "2", 0),
    ("4", "a", "2", 30),
    ("5", "a", "3", 0),
    ("6", "a", "3", 40),
    ("7", "a", "4", 0),
    ("8", "a", "4", 30),
    ("9", "a", "5", 0),
    ("10", "a", "5", 45),
    ("11", "a", "6", 0),
    ("12", "a", "6", 40),
    ("13", "a", "7", 0),
    ("14", "a", "7", 41),
    ("15", "a", "8", 0),
    ("16", "a", "8", 41),
    ("17", "a", "9", 0),
    ("18", "a", "9", 15),
    ("19", "a", "10", 0),
    ("20", "a", "10", 30),
    ("21", "a", "11", 0),
    ("22", "a", "11", 30),
    ("25", "a", None, 0),
    ("26", "a", None, 30),
    ("27", "a", "13", 0),
    ("28", "a", "13", 30),
    ("29", "a", "14", 0),
    ("30", "a", "14", 30),
    # Same price_at: as text "100" sorts before "99", so 100 is the earlier ad.
    ("99", "b", "1", 0),
    ("100", "b", "1", 0),
]


def changes(*pairs):
    return [{"changedAt": t, "status": s} for s, t in pairs]


# (listing, collected_at, last_collected_at, statusChanges), one record each. Listings 4,
# 29 and 99 have none.
RECORDS = [
    ("1", 1.0, 1.0, changes(("ACTIVE", at(-3)), ("RENTED", at(20)))),
    ("2", 1.0, 1.0, changes(("ACTIVE", at(58)))),
    (
        "3",
        1.0,
        1.0,
        changes(("ACTIVE", at(0)), ("IN_CONTRACT", at(10)), ("RENTED", at(15))),
    ),
    # A record with neither time is no listing's latest.
    ("5", None, None, changes(("ACTIVE", at(0)), ("RENTED", at(1)))),
    (
        "5",
        1.0,
        1.0,
        changes(
            ("ACTIVE", at(0)),
            ("TEMPORARILY_OFF_MARKET", at(10)),
            ("NO_LONGER_AVAILABLE", at(20)),
        ),
    ),
    ("6", 1.0, 1.0, changes(("ACTIVE", at(39)))),
    (
        "7",
        1.0,
        1.0,
        changes(
            ("DRAFT", at(-1)),
            ("ACTIVE", at(0)),
            ("DELISTED", at(5)),
            ("ACTIVE", at(8)),
            ("NO_LONGER_AVAILABLE", at(12)),
        ),
    ),
    ("8", 1.0, 1.0, changes(("ACTIVE", at(29)))),
    (
        "9",
        1.0,
        1.0,
        changes(
            ("ACTIVE", at(0)),
            ("DELISTED", at(10)),
            ("ACTIVE", at(50)),
            ("RENTED", at(70)),
        ),
    ),
    ("10", 1.0, 1.0, changes(("ACTIVE", at(40)))),
    ("11", 1.0, 1.0, changes(("ACTIVE", at(0)), ("RENTED", at(60)))),
    ("12", 1.0, 1.0, changes(("ACTIVE", at(30)))),
    ("13", 1.0, 1.0, changes(("ACTIVE", at(0)), ("DELISTED", iso(T)))),
    ("14", 1.0, 1.0, changes(("ACTIVE", iso(T)))),
    (
        "15",
        1.0,
        1.0,
        changes(("ACTIVE", at(0)), ("DELISTED", iso(T - pd.Timedelta(seconds=1)))),
    ),
    ("16", 1.0, 1.0, changes(("ACTIVE", iso(T)))),
    ("17", 1.0, 1.0, changes(("ACTIVE", at(0)), ("NO_LONGER_AVAILABLE", at(20)))),
    ("18", 1.0, 1.0, changes(("ACTIVE", at(25)))),
    ("19", 1.0, 1.0, changes(("NO_LONGER_AVAILABLE", at(5)))),
    ("20", 1.0, 1.0, changes(("ACTIVE", at(30)))),
    # Listing 21's later record, by last_collected_at, has the ending.
    ("21", 3.0, 3.0, changes(("ACTIVE", at(0)))),
    ("21", 2.0, 5.0, changes(("ACTIVE", at(0)), ("DELISTED", at(10)))),
    ("22", 1.0, 1.0, changes(("ACTIVE", at(30)))),
    ("25", 1.0, 1.0, changes(("ACTIVE", at(0)), ("RENTED", at(5)))),
    ("26", 1.0, 1.0, changes(("ACTIVE", at(30)))),
    ("27", 1.0, 1.0, changes(("ACTIVE", at(0)), ("RENTED", "not a time"))),
    ("28", 1.0, 1.0, changes(("ACTIVE", at(30)))),
    ("30", 1.0, 1.0, changes(("ACTIVE", at(30)))),
    ("100", 1.0, 1.0, changes(("ACTIVE", at(-10)), ("RENTED", at(-5)))),
    ("999", 1.0, 1.0, changes(("ACTIVE", at(0)), ("RENTED", at(5)))),
]

WANT = {
    "1": "none",  # the unit's first ad
    "2": "rented",
    "3": "none",
    "4": "rented",  # IN_CONTRACT, the first ending after ACTIVE; 4 opens at its price_at
    "5": "none",
    "6": "temp_off_market",  # the first ending after ACTIVE, not the last change
    "7": "none",
    "8": "no_longer_available",  # the ending after the last ACTIVE
    "9": "none",
    "10": "delisted",  # 9 came back on the market after 10 opened
    "11": "none",
    "12": "undated",  # 11 was still on the market when 12 opened
    "13": "none",
    "14": "undated",  # 13 ended at the moment 14 opened
    "15": "none",
    "16": "delisted",  # 15 ended a second before 16 opened
    "17": "none",
    "18": "undated",  # 18 opens at its price_at, before 17 ended
    "19": "none",
    "20": "undated",  # 19 has no ACTIVE change
    "21": "none",
    "22": "delisted",  # from 21's later record
    "25": "none",  # no unit_id
    "26": "none",  # no unit_id
    "27": "none",
    "28": "undated",  # 27's ending has no readable time
    "29": "none",
    "30": "undated",  # 29 has no record
    "100": "none",
    "99": "rented",
}


def frame():
    return pd.DataFrame(
        {
            "listing_id": [r[0] for r in ROWS],
            "audit_id": [r[0] for r in ROWS],
            "building": [r[1] for r in ROWS],
            "unit_id": [r[2] for r in ROWS],
            "price_at": [BASE + pd.Timedelta(days=r[3]) for r in ROWS],
            "latest_ask": [3000.0 + i for i in range(len(ROWS))],
        }
    )


@pytest.fixture
def src(tmp_path):
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": [int(r[0]) for r in RECORDS],
                "collected_at": [r[1] for r in RECORDS],
                "last_collected_at": [r[2] for r in RECORDS],
                "raw_listing_json": [
                    json.dumps({"statusChanges": r[3]}) for r in RECORDS
                ],
            }
        ),
        path,
        row_group_size=4,
    )
    d = tmp_path / "src"
    d.mkdir()
    frame().to_parquet(d / "rows.parquet")
    frame().iloc[:0].to_parquet(d / "set_aside.parquet")
    manifest = {
        "rows_sha256": "abc",
        "build": {"records": {"path": str(path), "sha256": sha256(path)}},
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


def test_previous_row_is_the_ad_before_in_l1s_phase_order():
    f = frame()
    prev = b0ending.previous_row(f)
    lid = f.listing_id.to_numpy()
    named = {lid[i]: (lid[p] if p >= 0 else None) for i, p in enumerate(prev)}
    assert named["2"] == "1" and named["1"] is None
    assert named["99"] == "100" and named["100"] is None
    assert named["25"] is None and named["26"] is None
    at = f.price_at.dt.tz_convert(None).to_numpy()
    months = np.full(len(f), np.nan)
    has = prev >= 0
    months[has] = (
        (at[has] - at[prev[has]])
        / np.timedelta64(1, "D")
        / drift_building_phase.MONTH_DAYS
    )
    np.testing.assert_allclose(
        months, drift_building_phase.months_since_previous(f), equal_nan=True
    )


def test_ending_reads_the_previous_ads_changes_before_the_row_opened(src, tmp_path):
    out = tmp_path / "out"
    manifest = b0ending.ending(src, out)
    rows = pd.read_parquet(out / "rows.parquet")
    pd.testing.assert_frame_equal(
        rows.drop(columns="prev_ending"), pd.read_parquet(src / "rows.parquet")
    )
    assert list(rows.prev_ending.cat.categories) == list(b0ending.CATEGORIES)
    assert dict(zip(rows.listing_id, rows.prev_ending.astype(str))) == WANT
    assert (out / "set_aside.parquet").exists()
    entry = manifest["ending"]
    assert entry["source"] == str(src) and entry["source_rows_sha256"] == "abc"
    assert entry["records"] == str(tmp_path / "records.parquet")
    assert entry["listings_read"] == 27
    assert entry["rows_with_previous"] == 14
    assert entry["previous_without_status_changes"] == 1
    assert entry["rows"] == {
        "none": 16,
        "rented": 3,
        "no_longer_available": 1,
        "delisted": 3,
        "temp_off_market": 1,
        "undated": 6,
    }
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    with pytest.raises(FileExistsError):
        b0ending.ending(src, out)


def test_ending_refuses_records_that_do_not_match_the_manifest(src, tmp_path):
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["records"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        b0ending.ending(src, tmp_path / "out")
    assert not (tmp_path / "out").exists()
