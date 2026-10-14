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


def test_a_live_listing_takes_its_last_change():
    r = latest_ask.record_latest(
        record([("2025-01-01", 3000), ("2025-02-01", 2800)], 2800)
    )
    assert r["live_ask"] == 2800 and r["page_price"] is None and r["n_off_day"] == 0


def test_a_placeholder_typed_on_the_off_market_day_is_skipped():
    r = latest_ask.record_latest(
        record(
            [("2025-01-01", 3000), ("2025-02-01", 2800), ("2025-03-01", 10000)],
            10000,
            status="RENTED",
            off="2025-03-01",
        )
    )
    assert r["live_ask"] == 2800 and r["n_off_day"] == 1


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
    assert r["live_ask"] == 3000


def test_a_page_price_off_by_a_digit_goes_to_the_nearer_of_the_two():
    frame = pd.DataFrame(
        {
            "audit_id": ["x", "p1", "p2"],
            "source_listing_id": ["1", "2", "3"],
            "building": ["b"] * 3,
            "bedrooms": [2.0] * 3,
            "asking_rent": [1000.0, 9500.0, 10500.0],
            "log_rent": np.log([1000.0, 9500.0, 10500.0]),
        }
    )
    table = pd.DataFrame(
        {"live_ask": [1000.0, 9500.0, 10500.0], "page_price": [10000.0, None, None]},
        index=["1", "2", "3"],
    )
    out = latest_ask.choose(frame, table).set_index("audit_id")
    assert out.latest_ask["x"] == 10000.0 and out.how["x"] == "page price, digit"
    assert out.latest_ask["p1"] == 9500.0 and out.how["p1"] == "latest"


def test_a_wide_change_keeps_the_ask_nearer_the_building():
    frame = pd.DataFrame(
        {
            "audit_id": ["x", "p1", "p2"],
            "source_listing_id": ["1", "2", "3"],
            "building": ["b"] * 3,
            "bedrooms": [1.0] * 3,
            "asking_rent": [3000.0, 3100.0, 2900.0],
            "log_rent": np.log([3000.0, 3100.0, 2900.0]),
        }
    )
    table = pd.DataFrame({"live_ask": [1_500_000.0], "page_price": [None]}, index=["1"])
    out = latest_ask.choose(frame, table).set_index("audit_id")
    assert out.latest_ask["x"] == 3000.0 and out.how["x"] == "first, nearer building"
    # Listings no crawl captured keep their own ask.
    assert out.how["p1"] == "uncaptured" and out.latest_ask["p1"] == 3100.0
