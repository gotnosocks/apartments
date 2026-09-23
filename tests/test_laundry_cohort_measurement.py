from copy import deepcopy
import hashlib
import json

import pytest

from models.laundry_cohort_measurement import measure_capture


def capture():
    raw = json.dumps(
        {
            "id": 123,
            "description": "$L1",
            "propertyDetails": {"amenities": {"list": ["LAUNDRY"]}},
        }
    )
    text = "Laundry on every floor."
    row = {
        "source_listing_id": "123",
        "building": "b",
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
        "laundry_type": "in_building",
    }
    evidence = {
        "audit_id": "a",
        "capture_id": 42,
        "source_listing_id": "123",
        "unit_id": "u",
        "body_sha256": "body",
        "raw_listing_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "description_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "description": text,
        "source_collected_at": "2025-01-01T00:00:00Z",
        "known_at": "2025-01-01T00:00:00Z",
        "description_interpreted_at": "2026-09-19T00:00:00Z",
        "source_path": "/description",
    }
    return row, evidence, raw


def test_recovered_description_is_used_without_mutating_capture_or_source_clocks():
    row, evidence, raw = capture()
    saved = deepcopy((row, evidence, raw))
    result = measure_capture(row, evidence, raw)
    assert result["measurement"]["most_convenient_reported_option"] == "on_floor"
    assert result["laundry_type"] == "in_building"
    assert result["known_at"] == evidence["known_at"]
    assert (row, evidence, raw) == saved


def test_mismatched_raw_bytes_and_advertisement_identity_are_refused():
    row, evidence, raw = capture()
    with pytest.raises(ValueError, match="hash"):
        measure_capture(row, evidence, raw + " ")
    row["source_listing_id"] = "124"
    with pytest.raises(ValueError, match="identity"):
        measure_capture(row, evidence, raw)
