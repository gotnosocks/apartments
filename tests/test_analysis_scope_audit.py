"""Source screens are cohort-wide review evidence, not residual-based edits."""

from models.analysis_scope_audit import screen


def prices(first=1500, second=15000, elapsed="16:07:48"):
    return {
        "pricing": {
            "priceChanges": [
                {"changedAt": "2025-08-02T16:07:25-04:00", "price": first},
                {"changedAt": f"2025-08-02T{elapsed}-04:00", "price": second},
            ]
        }
    }


def test_rapid_initial_source_changes_require_date_value_size_and_time_match():
    found = screen(prices(), "2025-08-02", 1500)
    assert (
        len(found) == 1
        and found[0]["elapsed_seconds"] == 23
        and found[0]["price_ratio"] == 10
    )
    assert found[0]["first_price"] == 1500 and found[0]["next_price"] == 15000
    assert screen(prices(), "2025-08-01", 1500) == []
    assert screen(prices(), "2025-08-02", 1600) == []
    assert screen(prices(second=1600), "2025-08-02", 1500) == []
    assert screen(prices(elapsed="17:07:48"), "2025-08-02", 1500) == []
    assert screen(prices(first=0), "2025-08-02", 0) == []


def test_order_duplicates_and_finite_values():
    payload = prices()
    events = payload["pricing"]["priceChanges"]
    events[:] = [events[1], events[0], events[0], {"changedAt": "bad", "price": 100}]
    assert screen(payload, "2025-08-02", 1500)[0]["elapsed_seconds"] == 23
    assert screen(prices(first=float("nan")), "2025-08-02", 1500) == []


def test_language_preserves_context_for_review_not_automatic_classification():
    text = "An apartment near retail space, with room for a home office."
    found = screen({"description": text}, "2020-01-01", 3000)
    assert found[0]["reason"] == "commercial_language"
    assert (
        found[0]["context"] == text
    )  # This is a false-positive candidate to reject in review.
    assert not any("exclude" in f or "replacement_price" in f for f in found)
    assert (
        screen(
            {"description": "Apartment with a home office, near shops."},
            "2020-01-01",
            3000,
        )
        == []
    )
    found = screen(
        {"description": "Advertise rent it’s NET EFFECTIVE"}, "2020-01-01", 3000
    )
    assert found[0]["reason"] == "advertised_net_effective"
