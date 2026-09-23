from copy import deepcopy
import hashlib

import pytest

from docs.analysis.scripts import review_floor_access_conflicts as m
from apartments import reviewed_cohort_quarantine as q


def case():
    row = {
        "audit_id": "case",
        "unit_id": "unit",
        "source_listing_id": "3193768",
        "building": "340-west-17-street-new_york",
        "asking_rent": 2379.0,
        "known_at": "2026-09-18T02:42:51Z",
        "capture_ids": [11, 12],
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
    }
    text = "**$2,595 monthly rent | Net monthly cost with 1-month free 2,379**. 344 West 17th Street"
    captures = []
    for cid in row["capture_ids"]:
        capture = {
            **{k: row[k] for k in ("audit_id", "unit_id", "source_listing_id")},
            "capture_id": cid,
            "description": text,
            "description_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "raw_listing_sha256": "a" * 64,
            "body_sha256": "b" * 64,
            "known_at": row["known_at"],
            "source_collected_at": "2026-09-11T00:00:00Z",
        }
        original = {
            "pricing": {"price": 2379, "netEffectiveRent": None},
            "listingAddress": "340 West 17th Street #2A",
            "raw_listing_sha256": capture["raw_listing_sha256"],
            "events": {
                "initial_event_matches_analytical_target": True,
                "initial_active_events": [{"price": 2379, "event_date": "2020-08-27"}],
            },
        }
        captures.append({"capture": capture, "original": original})
    return row, captures


def test_exact_review_retains_both_captures_prices_and_address_conflict_without_mutation():
    row, captures = case()
    before = deepcopy((row, captures))
    decision = m.price_recommendation(row, captures)
    assert decision["recommendation_only"] is True
    assert decision["action"] == "quarantine_unresolved_gross_price_basis"
    assert len(decision["evidence"]) == 2
    q.validate_decision(row, decision, m.REVIEWED_AT)
    assert (row, captures) == before
    assert "replacement_price" not in decision
    assert decision["evidence"][0]["spans"][1]["literal"] == "344 West 17th Street"


@pytest.mark.parametrize(
    "fault",
    [
        "ad",
        "target",
        "building",
        "missing_capture",
        "raw_hash",
        "captured_price",
        "event",
        "address",
        "quote",
        "clock",
    ],
)
def test_closed_review_cannot_extend_to_other_identity_or_changed_evidence(fault):
    row, captures = case()
    if fault == "ad":
        row["source_listing_id"] = "other"
    elif fault == "target":
        row["asking_rent"] = 2595
    elif fault == "building":
        row["building"] = "344-west-17-street-new_york"
    elif fault == "missing_capture":
        captures.pop()
    elif fault == "raw_hash":
        captures[0]["original"]["raw_listing_sha256"] = "c" * 64
    elif fault == "captured_price":
        captures[0]["original"]["pricing"]["price"] = 2595
    elif fault == "event":
        captures[0]["original"]["events"]["initial_event_matches_analytical_target"] = (
            False
        )
    elif fault == "address":
        captures[0]["original"]["listingAddress"] = "344 West 17th Street #3A"
    elif fault == "quote":
        captures[0]["capture"]["description"] = captures[0]["capture"][
            "description"
        ].replace("2,379", "2,380")
    elif fault == "clock":
        captures[0]["capture"]["known_at"] = "2027-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        m.price_recommendation(row, captures)
