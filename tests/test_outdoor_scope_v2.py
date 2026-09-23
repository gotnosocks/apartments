import copy

import pytest

from apartments.outdoor_evidence import extract
from apartments.outdoor_scope_v2 import measure, scope_text


def capture(text, private=(), shared=(), key=1):
    details = {
        "features": {"privateOutdoorSpaceTypes": list(private)},
        "amenities": {"sharedOutdoorSpaceTypes": list(shared)},
    }
    return {
        "audit_id": "ad",
        "source_listing_id": "123",
        "unit_id": "unit:1",
        "capture_id": key,
        "body_sha256": "body",
        "raw_listing_sha256": "raw",
        "source_collected_at": "2026-01-02T00:00:00Z",
        "description": text,
        "property_details": details,
        "extraction": extract({"description": text, "propertyDetails": details}),
    }


@pytest.mark.parametrize(
    "text,expected",
    [
        ("A private balcony.", [("BALCONY", "private_explicit")]),
        ("Two privates terraces.", [("TERRACE", "private_explicit")]),
        ("Your own landscaped garden.", [("GARDEN", "private_explicit")]),
        ("A terrace off the living room.", [("TERRACE", "unit_access")]),
        ("French doors open to a landscaped garden.", [("GARDEN", "unit_access")]),
        (
            "The primary bedroom has access to the terrace.",
            [("TERRACE", "unit_access")],
        ),
        ("This apartment features a balcony.", [("BALCONY", "unit_access")]),
        ("The building offers a private roof deck.", [("ROOF_DECK", "shared")]),
        ("Building features:\nPrivate terrace.", [("TERRACE", "unresolved")]),
        (
            "Building features: shared garden. Apartment features: private patio.",
            [("GARDEN", "shared"), ("PATIO", "private_explicit")],
        ),
        (
            "A private terrace and a common roof deck.",
            [("TERRACE", "private_explicit"), ("ROOF_DECK", "shared")],
        ),
        (
            "The building offers a roof deck, but this apartment has a private roof deck.",
            [("ROOF_DECK", "shared"), ("ROOF_DECK", "private_explicit")],
        ),
        ("Views of a private garden.", [("GARDEN", "view")]),
        ("The apartment has windows overlooking the garden.", [("GARDEN", "view")]),
        (
            "Private balcony overlooking the garden.",
            [("BALCONY", "private_explicit"), ("GARDEN", "view")],
        ),
        ("Garden Level: kitchen.", [("GARDEN", "unresolved")]),
        ("Semi-private patio.", [("PATIO", "unresolved")]),
        ("Some units have private terraces.", [("TERRACE", "unresolved")]),
        (
            "Some apartments have patios. This unit has a balcony.",
            [("PATIO", "unresolved"), ("BALCONY", "unit_access")],
        ),
        ("No private balcony.", [("BALCONY", "negative")]),
        ("This unit does not have a balcony.", [("BALCONY", "negative")]),
        ("No access to the garden.", [("GARDEN", "negative")]),
        ("The patio is not included.", [("PATIO", "negative")]),
        ("Private terrace is not private.", [("TERRACE", "unresolved")]),
        ("Private terrace shared with another apartment.", [("TERRACE", "shared")]),
        ("Potential for a private terrace.", [("TERRACE", "planned")]),
        ("This home will have a patio.", [("PATIO", "planned")]),
        ("The terrace is under construction.", [("TERRACE", "planned")]),
        ("A private deck.", [("DECK", "private_explicit")]),
        ("No fee! Private outdoor space.", [("OUTDOOR_SPACE", "private_explicit")]),
        (
            "Private backyard. Shared courtyard.",
            [("YARD", "private_explicit"), ("COURTYARD", "shared")],
        ),
        ("This residence offers a courtyard view.", [("COURTYARD", "view")]),
        ("A south-facing private terrace.", [("TERRACE", "private_explicit")]),
        ("A balcony just off the living room.", [("BALCONY", "unit_access")]),
        ("The living room with a spacious balcony.", [("BALCONY", "unit_access")]),
        ("Amenities include a furnished roofdeck.", [("ROOF_DECK", "shared")]),
        ("Private lounge and roof deck.", [("ROOF_DECK", "unresolved")]),
        (
            "The master bedroom has a window looking out to the garden.",
            [("GARDEN", "view")],
        ),
        ("Private balcony not included.", [("BALCONY", "negative")]),
    ],
)
def test_literal_scope_and_offsets(text, expected):
    claims = scope_text(text)
    assert [(c["type"], c["scope"]) for c in claims] == expected
    for c in claims:
        assert text[c["start"] : c["end"]] == c["match"]
        assert text[c["context_start"] : c["context_end"]] == c["context"]


def test_coexisting_private_shared_and_negative_retained_without_global_veto():
    one = capture("Private terrace. Building amenities: common terrace.", ["TERRACE"])
    two = capture("No terrace.", key=2)
    actual = measure([one, two])
    assert actual["types_by_scope"]["private_explicit"] == ["TERRACE"]
    assert actual["private_and_shared_types"] == ["TERRACE"]
    assert actual["positive_and_negative_types"] == ["TERRACE"]
    assert [c["scope"] for c in actual["claims"]] == [
        "private_explicit",
        "shared",
        "negative",
    ]
    assert actual["claims"][0]["basis"] == "text_and_structured_type"
    assert actual["claims"][2]["basis"] == "text_only"


def test_text_and_structured_scope_are_independent_dimensions():
    one = capture("The building has a garden.", ["GARDEN"])
    original = copy.deepcopy(one)
    actual = measure([one])["claims"][0]
    assert actual["scope"] == "shared"
    assert actual["structured_assertions"][0]["attribute"] == "private_type"
    assert one == original
    # No structured assertion required for direct text claims.
    assert measure([capture("A private terrace.")])["types_by_scope"][
        "private_explicit"
    ] == ["TERRACE"]


def test_integrity_identity_and_no_absence_inference():
    assert measure([])["claims"] == []
    assert measure([capture(None)])["types_by_scope"]["negative"] == []
    source = capture("Private balcony.", ["BALCONY"])
    changed = copy.deepcopy(source)
    changed["description"] = "No balcony."
    with pytest.raises(ValueError, match="extraction mismatch"):
        measure([changed])
    changed = copy.deepcopy(source)
    changed["source_listing_id"] = "different"
    with pytest.raises(ValueError, match="one analytical advertisement"):
        measure([source, changed])
    with pytest.raises(ValueError, match="Duplicate"):
        measure([source, source])


def test_nested_source_and_unicode_boundaries():
    source = capture("irrelevant")
    source["property_details"]["description"] = (
        "Garden views.\u2028Private balcony.<br/>Shared garden."
    )
    source["extraction"] = extract(
        {
            "description": source["description"],
            "propertyDetails": source["property_details"],
        }
    )
    claims = measure([source])["claims"]
    assert all(c["source_path"] == "/propertyDetails/description" for c in claims)
    assert claims[1]["scope"] == "private_explicit"
    assert claims[2]["scope"] == "shared"


def test_view_subject_is_separate_from_garden_ownership():
    apartment = scope_text("The apartment overlooks the building's front garden.")[0]
    assert (apartment["scope"], apartment["subject"]) == ("view", "apartment")
    building = scope_text(
        "Windowed elevator lobbies overlooking a serene courtyard garden."
    )
    assert [(c["scope"], c["subject"]) for c in building] == [
        ("view", "building"),
        ("view", "building"),
    ]


def test_non_amenity_names_do_not_become_planned_or_shared_facilities():
    claims = scope_text(
        "The building is near Hudson Yards. The future London Terrace Towers project."
    )
    assert all(
        c["scope"] == "unresolved" and c["subject"] == "not_an_amenity" for c in claims
    )
