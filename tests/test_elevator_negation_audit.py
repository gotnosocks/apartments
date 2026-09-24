from copy import deepcopy
import hashlib
import json

import pytest

from apartments.attribute_evidence import extract_attribute_evidence
from models.elevator_negation_audit import replay, summarize_row


def inputs(structured=False):
    payload = {
        "id": 42,
        "description": "$reference",
        "propertyDetails": {"amenities": {"list": ["ELEVATOR"] if structured else []}},
    }
    raw = json.dumps(payload)
    row = {
        "source_listing_id": "42",
        "building": "b",
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
        "elevator": True,
        "audit_id": "a",
        "unit_id": "u",
    }
    capture = {
        "description": "One flight up in a non-elevator building.",
        "raw_listing_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }
    return row, capture, raw


@pytest.mark.parametrize("structured,expected", [(False, False), (True, None)])
def test_replay_preserves_original_structured_claim_and_recovers_literal_description(
    structured, expected
):
    row, capture, raw = inputs(structured)
    frozen = deepcopy(capture)
    result = replay(row, capture, raw, extract_attribute_evidence)
    assert result["after"]["value"] is expected
    assert bool(result["after"]["conflicts"]) == structured
    assert result["description"] == capture["description"] and capture == frozen
    assert "non-elevator" in next(
        c["literal"]
        for c in result["after"]["claims"]
        if c["source_path"] == "/description"
    )


@pytest.mark.parametrize("damage", ["hash", "advertisement", "unrelated"])
def test_wrong_original_payload_or_unrelated_extraction_changes_are_refused(damage):
    row, capture, raw = inputs()
    old = extract_attribute_evidence
    if damage == "hash":
        raw += " "
    if damage == "advertisement":
        row["source_listing_id"] = "43"
    if damage == "unrelated":

        def old(payload):
            result = extract_attribute_evidence(payload)
            result["attributes"]["bedrooms"] = 5
            return result

    with pytest.raises(ValueError):
        replay(row, capture, raw, old)


def test_unknown_or_differing_attached_captures_prevent_a_known_candidate():
    row, _, _ = inputs()
    no = {"after": {"value": False, "conflicts": []}}
    unknown = {"after": {"value": None, "conflicts": [True, False]}}
    assert summarize_row(row, [no, no])["candidate_elevator"] is False
    result = summarize_row(row, [no, unknown])
    assert result["candidate_elevator"] is None and not result["all_captures_agree"]
    assert result["conflicting_claim_captures"] == 1
