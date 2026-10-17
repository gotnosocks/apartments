import importlib.util
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ads_check = load(
    "ads_check", Path(__file__).parents[2] / "ops" / "pipeline" / "ads_check.py"
)


def event(date, status, index=0):
    return {
        "event_index": index,
        "event_listing_id": "7",
        "event_category": "rental",
        "event_date": date,
        "status": status,
    }


def test_last_break_is_the_ads_latest_return():
    events = [
        event("2026-08-10", "ACTIVE"),
        event("2026-08-14", "RENTED"),
        event("2026-08-17", "ACTIVE"),
        event("2026-08-25", "TEMPORARILY_OFF_MARKET"),
        event("2026-09-08", "ACTIVE"),
    ]
    assert ads_check.last_break(events, "2026-08-10", "2026-10-05") == (
        "TEMPORARILY_OFF_MARKET",
        "2026-08-25",
        "2026-09-08",
    )
    assert ads_check.last_break(events[:1], "2026-08-10", "2026-10-05") == (None,) * 3
    # Events outside the days from `since` to `as_of` take no part.
    assert ads_check.last_break(events, "2026-08-15", "2026-09-07") is None
    # Rented and back on the same day: the history lists the newer event first.
    same_day = [
        event("2026-10-05", "ACTIVE", 0),
        event("2026-10-05", "RENTED", 1),
        event("2026-08-10", "ACTIVE", 2),
    ]
    assert ads_check.last_break(same_day, "2026-08-10", "2026-10-05") == (
        "RENTED",
        "2026-10-05",
        "2026-10-05",
    )
    # Off the market by the ad's own last event: no date at all.
    assert ads_check.last_break(events[:2], "2026-08-10", "2026-10-05") is None
