import pytest

from apartments.outdoor_evidence import CONTEXT_RADIUS, extract, screen


def areas(text):
    return [item for item in screen(text) if item["feature"] == "outdoor_area"]


def test_structured_private_and_shared_remain_separate_and_literal():
    result = extract(
        {
            "features": {
                "privateOutdoorSpaceTypes": ["BALCONY", "TERRACE"],
                "list": ["PRIVATE_OUTDOOR_SPACE"],
            },
            "amenities": {
                "sharedOutdoorSpaceTypes": ["GARDEN"],
                "list": ["SHARED_OUTDOOR_SPACE"],
            },
        }
    )
    assert not result["warnings"]
    assert [
        x["value"] for x in result["assertions"] if x["attribute"] == "private_type"
    ] == ["BALCONY", "TERRACE"]
    assert [
        x["value"] for x in result["assertions"] if x["attribute"] == "shared_type"
    ] == ["GARDEN"]
    assert result["assertions"][0] == {
        "attribute": "private_type",
        "value": "BALCONY",
        "literal": "BALCONY",
        "source_path": "/features/privateOutdoorSpaceTypes/0",
    }
    assert all(
        x["value"] is True
        for x in result["assertions"]
        if x["attribute"].endswith("_outdoor")
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"features": {}},
        {
            "features": {"privateOutdoorSpaceTypes": []},
            "amenities": {"sharedOutdoorSpaceTypes": []},
        },
        {"features": {"views": ["GARDEN"]}, "lotAreaSize": 1000},
        {"description": "No private outdoor space; garden views."},
    ],
)
def test_unknown_is_not_false_and_description_never_asserts_access(payload):
    assert extract(payload)["assertions"] == []


def test_unknown_codes_and_malformed_fields_remain_reviewable():
    result = extract(
        {
            "features": {"privateOutdoorSpaceTypes": ["LOGGIA", None, 4, ""]},
            "amenities": {"sharedOutdoorSpaceTypes": "GARDEN"},
        }
    )
    assert result["assertions"] == [
        {
            "attribute": "private_type",
            "value": "LOGGIA",
            "source_path": "/features/privateOutdoorSpaceTypes/0",
            "literal": "LOGGIA",
        }
    ]
    assert [x["code"] for x in result["warnings"]] == [
        "unknown_type_code",
        "invalid_type_code",
        "invalid_type_code",
        "invalid_type_code",
        "invalid_array_type",
    ]


def test_nested_payload_and_source_paths():
    result = extract(
        {
            "propertyDetails": {
                "features": {"privateOutdoorSpaceTypes": ["PATIO"]},
                "description": "Private terrace.",
            }
        }
    )
    assert (
        result["assertions"][0]["source_path"]
        == "/propertyDetails/features/privateOutdoorSpaceTypes/0"
    )
    assert (
        result["description_candidates"][0]["source_path"]
        == "/propertyDetails/description"
    )
    assert (
        extract({"propertyDetails": {}, "description": "Shared garden."})[
            "description_candidates"
        ][0]["source_path"]
        == "/description"
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "6,000 SF of total living space and 7,000 SF of private outdoor space",
            [7000],
        ),
        ("private 575sf terrace", [575]),
        ("A 400-square-foot terrace.", [400]),
        ("Garden measures 550 sq. ft.", [550]),
        ("Terrace: approximately 300 square feet.", [300]),
        ("A 100 ft² balcony.", [100]),
        ("3,000 square foot townhouse with a rooftop terrace", []),
        ("A 900 square foot living room with garden views.", []),
        ("Garden views from this 600 sf apartment.", []),
        ("Terrace, and a 1000 sf apartment.", []),
    ],
)
def test_numeric_area_requires_local_outdoor_link(text, expected):
    assert [item.get("value_sqft") for item in areas(text)] == expected


def test_exact_unicode_offsets_and_independent_private_shared_flags():
    text = "☀ Private 575sf terrace; shared 800 SF garden."
    for item in screen(text):
        assert text[item["start"] : item["end"]] == item["match"]
        assert text[item["context_start"] : item["context_end"]] == item["context"]
    private, shared = areas(text)
    assert "explicit_private_language" in private["flags"]
    assert "building_or_shared_scope" not in private["flags"]
    assert "building_or_shared_scope" in shared["flags"]
    assert "explicit_private_language" not in shared["flags"]
    for item in (private, shared):
        assert (
            text[item["measurement_start"] : item["measurement_end"]]
            == item["measurement_text"]
        )
        assert text[item["outdoor_start"] : item["outdoor_end"]] == item["outdoor_text"]


@pytest.mark.parametrize(
    "text,flag",
    [
        ("No private outdoor space.", "negation_language"),
        ("A terrace will be added.", "planned_language"),
        ("Could add a terrace.", "hypothetical_language"),
        ("Garden views.", "view_or_exposure_language"),
        ("A private terrace shared by residents.", "mixed_private_shared_language"),
        ("Private 10 x 20 terrace, 200 SF outdoor space.", "dimensions_language"),
        (
            "Total 800 SF of private outdoor space including two terraces.",
            "area_sum_or_total_language",
        ),
    ],
)
def test_context_warnings_are_advisory_not_resolved_states(text, flag):
    items = screen(text)
    assert items and all(flag in item["flags"] for item in items)
    assert all("value" not in item for item in items)


def test_shared_section_persists_and_unit_section_resets():
    items = screen(
        "Building Amenities:\nGarden\nPatio\nUnit Features:\nPrivate terrace"
    )
    assert "shared_section_scope" in items[0]["flags"]
    assert "shared_section_scope" in items[1]["flags"]
    assert "shared_section_scope" not in items[2]["flags"]


@pytest.mark.parametrize(
    "text", ["200-300 SF terrace", "200 to 300 sq ft garden", "200 SF–300 SF patio"]
)
def test_range_not_collapsed_to_scalar(text):
    item = areas(text)[-1]
    assert item["sqft_values"] == [200, 300]
    assert "value_sqft" not in item
    assert "measurement_range" in item["flags"]


def test_context_bound_and_no_dimension_multiplication():
    text = "word " * 1000 + "10 x 20 terrace" + " word" * 1000
    (item,) = screen(text)
    assert len(item["context"]) <= len(item["match"]) + 2 * CONTEXT_RADIUS
    assert item["feature"] == "outdoor_wording" and "value_sqft" not in item


def test_zero_negative_and_extreme_areas_flagged():
    assert "unusual_outdoor_area" in areas("0 SF patio")[0]["flags"]
    assert "unusual_outdoor_area" in areas("50000 SF garden")[0]["flags"]
    assert "value_sqft" not in areas("-100 SF terrace")[0]
