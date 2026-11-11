import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0closingraise
from rentfrontier.b0data import sha256


def record(changes, statuses, on="2024-01-01", off="2024-02-01"):
    """A raw record with price changes (timestamp, price) and status changes (timestamp,
    status). A price change given as a bare day falls at noon UTC."""
    return json.dumps(
        {
            "status": "RENTED",
            "onMarketAt": f"{on}T00:00:00Z",
            "offMarketAt": f"{off}T00:00:00Z",
            "pricing": {
                "price": changes[-1][1],
                "priceChanges": [
                    {"changedAt": t if "T" in t else f"{t}T12:00:00Z", "price": p}
                    for t, p in changes
                ],
            },
            "statusChanges": [{"changedAt": t, "status": s} for t, s in statuses],
        }
    )


LISTED = ("2024-01-01T00:00:00Z", "ACTIVE")
RECORDS = {
    # A raise typed 30 s before RENTED.
    "1": record(
        [("2024-01-01", 3000), ("2024-01-20", 2900), ("2024-02-01T15:00:00Z", 3400)],
        [LISTED, ("2024-02-01T15:00:30Z", "RENTED")],
    ),
    # A raise typed 2 hours before RENTED.
    "2": record(
        [("2024-01-01", 3000), ("2024-01-20", 2900), ("2024-02-01T13:00:00Z", 3400)],
        [LISTED, ("2024-02-01T15:00:00Z", "RENTED")],
    ),
    # A cut typed in the same action as RENTED.
    "3": record(
        [("2024-01-01", 3000), ("2024-01-20", 2900), ("2024-02-01T15:00:00Z", 2600)],
        [LISTED, ("2024-02-01T15:00:00Z", "RENTED")],
    ),
    # A raise typed 3 hours after DELISTED, with timestamps in New York time.
    "4": record(
        [
            ("2024-01-01", 3000),
            ("2024-01-28", 2900),
            ("2024-02-01T16:00:00.000-05:00", 3400),
        ],
        [LISTED, ("2024-02-01T13:00:00.000-05:00", "DELISTED")],
    ),
    # Priced net of free months, so its ask matches no change.
    "5": record(
        [("2024-01-01", 3000), ("2024-02-01T15:00:00Z", 3300)],
        [LISTED, ("2024-02-01T15:00:10Z", "RENTED")],
    ),
    # A raise on the off-market day, with the status event dated the next day.
    "6": record(
        [("2024-01-01", 3000), ("2024-01-20", 2900), ("2024-02-01T15:00:00Z", 3400)],
        [LISTED, ("2024-02-02T09:00:00Z", "RENTED")],
    ),
    # A cut typed in the morning of the off-market day, and a raise typed 10 s before RENTED.
    "8": record(
        [
            ("2024-01-01", 3000),
            ("2024-01-20", 2900),
            ("2024-02-01T14:00:00Z", 2700),
            ("2024-02-01T19:59:50Z", 3400),
        ],
        [LISTED, ("2024-02-01T20:00:00Z", "RENTED")],
    ),
    # A raise typed in the morning of the off-market day, and a cut typed 10 s before RENTED.
    "9": record(
        [
            ("2024-01-01", 3000),
            ("2024-01-20", 2900),
            ("2024-02-01T14:00:00Z", 3600),
            ("2024-02-01T19:59:50Z", 3400),
        ],
        [LISTED, ("2024-02-01T20:00:00Z", "RENTED")],
    ),
}


@pytest.fixture
def src(tmp_path):
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": list(RECORDS),
                "listing_type": ["rental"] * len(RECORDS),
                "last_collected_at": [1] * len(RECORDS),
                "raw_listing_json": list(RECORDS.values()),
            }
        ),
        path,
    )
    rows = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
            "latest_ask": [3400.0, 3400.0, 2600.0, 3400.0, 2750.0, 3400.0, 1500.0]
            + [3400.0, 3400.0],
            "latest_ask_how": ["latest"] * 9,
            "price_at": pd.to_datetime(["2024-01-25"] * 9, utc=True),
            "latest_day": [pd.Timestamp("2024-02-01").date()] * 9,
            "latest_day_how": ["change"] * 9,
        }
    )
    d = tmp_path / "src"
    d.mkdir()
    rows.to_parquet(d / "rows.parquet")
    rows.iloc[:0].to_parquet(d / "set_aside.parquet")
    manifest = {
        "rows_sha256": "abc",
        "build": {"records": {"path": str(path), "sha256": sha256(path)}},
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


def timed(raw):
    kept = b0closingraise.record_latest(raw, b0closingraise.STALE_DAYS)["changes"]
    return b0closingraise.standing(raw, kept)


def test_standing_times_the_last_late_price_against_the_first_off_market_status():
    assert [timed(RECORDS[i])[0] for i in "1234"] == [30, 7200, 0, -10800]
    # A price typed more than 300 s before the status event stood on the open ad.
    assert timed(RECORDS["2"])[1:] == (3400, "2024-02-01")
    assert timed(RECORDS["8"]) == (10, 2700, "2024-02-01")
    assert all(x is None or np.isnan(x) for x in timed(RECORDS["1"])[1:])
    assert all(x is None or np.isnan(x) for x in timed(RECORDS["6"]))
    # A price typed 300 s before the status event counts as typed while the ad closed, and
    # one typed 301 s before it stood. An ACTIVE event on the off-market day is passed
    # over, and a timestamp with no offset is read as UTC.
    for seconds, stood in ((300, False), (301, True)):
        at = pd.Timestamp("2024-02-01T16:00:00Z") - pd.Timedelta(seconds=seconds)
        raw = record(
            [("2024-01-01", 3000), (at.strftime("%Y-%m-%dT%H:%M:%SZ"), 3400)],
            [
                LISTED,
                ("2024-02-01T08:00:00Z", "ACTIVE"),
                ("2024-02-01T16:00:00", "RENTED"),
            ],
        )
        wait, price, _ = timed(raw)
        assert wait == seconds
        assert (price == 3400) is stood
    # A record with no off-market day, and one with no change from that day on.
    bare = json.dumps({"pricing": {"priceChanges": []}})
    assert np.isnan(b0closingraise.standing(bare, [])[0])
    early = record([("2024-01-01", 3000)], [("2024-02-01T16:00:00Z", "RENTED")])
    assert np.isnan(timed(early)[0])


def test_closing_raise_reprices_only_raises_typed_as_the_ad_closed(src, tmp_path):
    before = (src / "rows.parquet").read_bytes()
    out = tmp_path / "out"
    manifest = b0closingraise.closing_raise(src, out)
    rows = pd.read_parquet(out / "rows.parquet")
    # Row 8 takes the cut of the off-market day's morning. Row 9 keeps its closing cut.
    assert rows.latest_ask.tolist() == [
        2900.0,
        3400.0,
        2600.0,
        2900.0,
        2750.0,
        3400.0,
        1500.0,
        2700.0,
        3400.0,
    ]
    changed = [True, False, False, True, False, False, False, True, False]
    assert rows.latest_ask_how.tolist() == [
        b0closingraise.HOW if c else "latest" for c in changed
    ]
    # The kept change of 2024-01-20 falls before the row's day of 2024-01-25, and those of
    # 2024-01-28 and 2024-02-01 after it.
    assert [str(d) for d in rows.latest_day[changed]] == [
        "2024-01-25",
        "2024-01-28",
        "2024-02-01",
    ]
    assert rows.latest_day_how[changed].tolist() == [
        "row, change before",
        "change",
        "change",
    ]
    assert rows.latest_day_how[~np.array(changed)].tolist() == ["change"] * 6
    entry = manifest["closing_raise"]
    assert entry["source"] == str(src)
    assert entry["source_rows_sha256"] == "abc"
    assert entry["listings_read"] == 8
    assert entry["closing_would_change"] == 7
    assert entry["changed"] == 3
    assert entry["changed_to_off_day_price"] == 1
    assert entry["dated_by_row"] == 1
    assert entry["median_log_change"] == round(float(np.log(3400 / 2900)), 4)
    assert entry["kept_off_day_price"] == {
        "stood": 1,
        "closing_cut": 2,
        "no_wait": 1,
    }
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert json.loads((out / "manifest.json").read_text()) == manifest
    assert (src / "rows.parquet").read_bytes() == before
    assert (out / "set_aside.parquet").read_bytes() == (
        src / "set_aside.parquet"
    ).read_bytes()
    with pytest.raises(FileExistsError):
        b0closingraise.closing_raise(src, out)


def test_closing_raise_refuses_a_changed_records_file(src, tmp_path):
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["records"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        b0closingraise.closing_raise(src, tmp_path / "out")
