import json

import numpy as np
import pandas as pd
from rentfrontier import latest_ask


def record(changes, price, status="ACTIVE", on="2025-01-01", off=None):
    return json.dumps(
        {
            "status": status,
            "onMarketAt": on,
            "offMarketAt": off,
            "pricing": {
                "price": price,
                "priceChanges": [{"changedAt": d, "price": p} for d, p in changes],
            },
        }
    )


def test_a_live_listing_keeps_all_its_changes():
    r = latest_ask.record_latest(
        record([("2025-01-01", 3000), ("2025-02-01", 2800)], 2800)
    )
    assert r["changes"] == [("2025-01-01", 3000.0), ("2025-02-01", 2800.0)]
    assert r["page_price"] is None and r["n_placeholder"] == 0


def test_a_placeholder_on_the_off_market_day_is_skipped_and_a_final_raise_counts():
    r = latest_ask.record_latest(
        record(
            [("2025-01-01", 3000), ("2025-02-01", 2800), ("2025-03-01", 10000)],
            10000,
            status="RENTED",
            off="2025-03-01",
        )
    )
    assert r["changes"][-1] == ("2025-02-01", 2800.0) and r["n_placeholder"] == 1
    r = latest_ask.record_latest(
        record(
            [("2025-01-01", 3000), ("2025-03-01", 3100)],
            3100,
            status="RENTED",
            off="2025-03-01",
        )
    )
    assert r["changes"][-1] == ("2025-03-01", 3100.0)
    r = latest_ask.record_latest(
        record(
            [("2025-01-01", 6500), ("2025-03-01", 10000)],
            10000,
            status="RENTED",
            off="2025-03-01",
        )
    )
    assert r["changes"] == [("2025-01-01", 6500.0)]


def test_a_same_day_fix_on_the_first_day_counts():
    r = latest_ask.record_latest(
        record(
            [("2025-01-01T10:00", 30000), ("2025-01-01T11:00", 3000)],
            3000,
            status="RENTED",
            on="2025-01-01",
            off="2025-01-01",
        )
    )
    assert r["changes"][-1] == ("2025-01-01", 3000.0)


def frame_of(asks, listings, days, bedrooms=2.0):
    n = len(asks)
    return pd.DataFrame(
        {
            "audit_id": [f"r{i}" for i in range(n)],
            "source_listing_id": listings,
            "building": ["b"] * n,
            "bedrooms": [bedrooms] * n,
            "price_at": pd.to_datetime(days, utc=True),
            "asking_rent": asks,
            "log_rent": np.log(asks),
        }
    )


def table_of(rows, captured="2026-01-01"):
    at = pd.Timestamp(captured, tz="UTC").timestamp()
    return pd.DataFrame(
        [
            {"listing_id": k, "collected_at": at, "changes": c, "page_price": p}
            for k, (c, p) in rows.items()
        ]
    ).set_index("listing_id")


def test_two_rows_of_one_listing_each_keep_their_own_dates():
    frame = frame_of(
        [3000.0, 3500.0, 3100.0],
        ["1", "1", "2"],
        ["2024-01-01", "2025-01-01", "2024-06-01"],
    )
    table = table_of(
        {
            "1": (
                [
                    ("2024-01-01", 3000.0),
                    ("2024-02-01", 2900.0),
                    ("2025-01-01", 3500.0),
                ],
                None,
            ),
            "2": ([("2024-06-01", 3100.0)], None),
        }
    )
    out = latest_ask.choose(frame, table).set_index("audit_id")
    assert out.latest_ask.tolist() == [2900.0, 3500.0, 3100.0]


def test_a_row_newer_than_the_capture_keeps_its_ask():
    frame = frame_of([4800.0, 5000.0], ["1", "2"], ["2026-02-01", "2025-06-01"])
    table = table_of(
        {"1": ([("2025-09-01", 5100.0)], 5100.5), "2": ([("2025-06-01", 5000.0)], None)}
    )
    out = latest_ask.choose(frame, table).set_index("audit_id")
    assert out.latest_ask["r0"] == 4800.0
    assert out.how["r0"] == "own ask, captured before the row"


def test_a_page_price_is_the_current_price_or_a_digit_off():
    frame = frame_of(
        [1000.0, 9500.0, 10500.0, 3000.0],
        ["1", "2", "3", "4"],
        ["2025-01-01"] * 4,
    )
    table = table_of(
        {
            "1": ([("2025-01-01", 1000.0)], 10000.0),
            "2": ([("2025-01-01", 9500.0)], None),
            "3": ([("2025-01-01", 10500.0)], None),
            "4": ([("2025-01-01", 3000.0)], 2950.0),
        }
    )
    out = latest_ask.choose(frame, table).set_index("audit_id")
    assert out.latest_ask["r0"] == 10000.0 and out.how["r0"] == "page price, digit"
    assert out.latest_ask["r1"] == 9500.0 and out.how["r1"] == "latest"
    assert out.latest_ask["r3"] == 2950.0 and out.how["r3"] == "page price"


def test_a_wide_change_keeps_the_ask_nearer_the_building():
    frame = frame_of(
        [3000.0, 3100.0, 2900.0], ["1", "2", "3"], ["2025-01-01"] * 3, bedrooms=1.0
    )
    table = table_of(
        {"1": ([("2025-01-01", 3000.0), ("2025-02-01", 1_500_000.0)], None)}
    )
    out = latest_ask.choose(frame, table).set_index("audit_id")
    assert out.latest_ask["r0"] == 3000.0 and out.how["r0"] == "first, nearer building"
    # Listings no crawl captured keep their own ask.
    assert out.how["r1"] == "uncaptured" and out.latest_ask["r1"] == 3100.0


def test_a_sale_with_a_rentals_id_is_skipped(monkeypatch, tmp_path):
    """StreetEasy numbers sales and rentals separately, so a later sale capture
    can carry a rental's id. Both builders keep the rental's own record."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from rentfrontier import listing_extras

    folder = tmp_path / "listing_observations"
    folder.mkdir()
    pq.write_table(
        pa.table(
            {
                "listing_id": [7, 7],
                "listing_type": ["rental", "sale"],
                "collected_at": [1.0, 2.0],
                "raw_listing_json": [
                    record([("2025-01-01", 3000)], 3000),
                    record([("2026-01-01", 899000)], 899000),
                ],
            }
        ),
        folder / "part.parquet",
    )
    monkeypatch.setattr(latest_ask, "CRAWLS", {"x": str(tmp_path)})
    monkeypatch.setattr(listing_extras, "CRAWLS", {"x": str(tmp_path)})
    assert latest_ask.listings().loc["7"].changes == [("2025-01-01", 3000.0)]
    extras = listing_extras.build().set_index("listing_id")
    assert json.loads(extras.loc["7"].price_changes) == [["2025-01-01", 3000]]
