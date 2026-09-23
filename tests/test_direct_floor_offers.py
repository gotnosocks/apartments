import hashlib
import json
from pathlib import Path

import pytest
from apartments.attribute_evidence import (
    extract_attribute_evidence as extract,
    DIRECT_OFFER_FLOOR_RULE,
)


def test_complete_reviewed_descriptions_recover_independent_floor_claims():
    cases = json.loads(
        (Path(__file__).parent / "fixtures/direct_floor_offers.json").read_text()
    )
    for case in cases:
        text = case["description"]
        assert hashlib.sha256(text.encode()).hexdigest() == case["description_sha256"]
        result = extract({"description": text})
        assert (
            result["attributes"]["advertised_floor"]
            == {"3967693": 2, "776029": 1}[case["source_listing_id"]]
        )
        assert result["attributes"]["physical_floor"] is None
        for claim in result["evidence"]:
            if claim["attribute"] == "advertised_floor":
                assert claim["rule"] == DIRECT_OFFER_FLOOR_RULE
                assert text[claim["start"] : claim["end"]] == claim["literal"]


@pytest.mark.parametrize(
    "text",
    [
        "Photos of this first floor walk-up apartment are for reference.",
        "Photos of\nthis first floor walk-up apartment are shown.",
        "Not this first floor apartment.",
        "This first floor apartment might be available.",
        "Is this first floor apartment available?",
        "Shared amenities: this second floor residence is a lounge.",
        "FLOOR TWO, UNIT ONE\nPhotos show a different apartment.",
        "FLOOR TWO, UNIT ONE is a sample.",
        "The first floor gym is shared.",
        "Unit two, floor unknown.",
    ],
)
def test_reference_shared_hypothetical_and_unit_labels_are_not_floor_claims(text):
    assert extract({"description": text})["attributes"]["advertised_floor"] is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("This third-floor apartment has bright windows.", 3),
        ("This twentieth floor residence is spacious.", 20),
        ("FLOOR TWO, UNIT NINE\n\nA spacious apartment.", 2),
    ],
)
def test_direct_floor_values_and_exact_offsets(text, expected):
    result = extract({"description": text})
    assert result["attributes"]["advertised_floor"] == expected
    assert result["attributes"]["floors_above_ground"] is None


def test_structured_floor_disagreement_preserves_both_claims():
    result = extract(
        {
            "propertyDetails": {"floor": 3},
            "description": "This first floor walk-up apartment is spacious.",
        }
    )
    assert result["attributes"]["advertised_floor"] is None
    assert "advertised_floor" in result["conflicts"]
    assert {
        e["value"] for e in result["evidence"] if e["attribute"] == "advertised_floor"
    } == {1, 3}
