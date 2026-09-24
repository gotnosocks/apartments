import pytest

from apartments.interior_evidence import CONTEXT_RADIUS, screen


def by_feature(text, feature):
    return [item for item in screen(text) if item["feature"] == feature]


def test_unicode_literal_offsets_and_room_specific_ceiling():
    text = "☀ A duplex with 18’ skylit livingroom ceilings and exposed brick."
    evidence = screen(text)
    (height,) = by_feature(text, "ceiling_height")
    assert height["value_feet"] == 18
    assert "room_specific_scope" in height["flags"]
    assert by_feature(text, "levels")[0]["levels"] == 2
    assert by_feature(text, "skylight")
    for item in evidence:
        assert text[item["start"] : item["end"]] == item["match"]
        assert text[item["context_start"] : item["context_end"]] == item["context"]


@pytest.mark.parametrize(
    "text",
    ["10-12 foot ceilings", "10′–12′ ceilings", "ceilings range from 10 to 12 feet"],
)
def test_range_not_collapsed(text):
    (item,) = by_feature(text, "ceiling_height")
    assert item["feet_values"] == [10, 12]
    assert "value_feet" not in item
    assert "measurement_range" in item["flags"]


@pytest.mark.parametrize(
    "text", ['10" ceilings', "10 inch ceilings", "10 inches ceilings", "10″ ceilings"]
)
def test_inches_never_repaired_to_feet(text):
    (item,) = by_feature(text, "ceiling_height")
    assert item["measurement_unit"] == "inches"
    assert "inch_units_not_feet" in item["flags"]
    assert "value_feet" not in item and "feet_values" not in item


def test_mixed_feet_inches_not_partial_scalar():
    (item,) = by_feature("10′ 6″ ceilings.", "ceiling_height")
    assert item["measurement_text"] == "10′ 6″"
    assert "mixed_units_review_required" in item["flags"]
    assert "value_feet" not in item


def test_unit_and_lobby_candidates_retained_with_scope_advice():
    text = "The lobby has 20 ft ceilings. This apartment has 10 foot ceilings."
    lobby, unit = by_feature(text, "ceiling_height")
    assert "building_or_shared_scope" in lobby["flags"]
    assert "building_or_shared_scope" not in unit["flags"]
    assert all("differing_height_candidates" in item["flags"] for item in (lobby, unit))
    assert [item["value_feet"] for item in (lobby, unit)] == [20, 10]


def test_section_scope_persists_across_bullets_and_resets():
    text = "Building Amenities:\n20 foot ceilings\nSkylight\nUnit Features:\n10 foot ceilings"
    items = screen(text)
    assert "shared_section_scope" in items[0]["flags"]
    assert "shared_section_scope" in items[1]["flags"]
    assert "shared_section_scope" not in items[2]["flags"]


def test_hypothetical_negated_and_planned_are_not_resolved():
    text = "Could convert to a duplex. No skylights. Planned renovation will add a skylight."
    items = screen(text)
    assert "hypothetical_language" in items[0]["flags"]
    assert "negation_language" in items[1]["flags"]
    assert "planned_language" in items[2]["flags"]
    assert all("value" not in item for item in items)


@pytest.mark.parametrize(
    "phrase",
    ["floor through", "floor-through", "floor thru", "floor-thru", "floor–through"],
)
def test_floor_through_does_not_infer_exposures(phrase):
    (item,) = screen("A " + phrase + " apartment.")
    assert item["feature"] == "floor_through"
    assert "levels" not in item and "value" not in item


def test_multiple_levels_and_other_units_scope():
    items = by_feature(
        "Single-level home. Two-level unit. A triplex. Multi-level layout. Other duplex apartments available.",
        "levels",
    )
    assert [item.get("levels") for item in items] == [1, 2, 3, None, 2]
    assert "other_or_multiple_units_scope" in items[-1]["flags"]


def test_missing_description_or_unmentioned_feature_is_unknown():
    for description in (
        None,
        "",
        {},
        "$3a",
        "A spacious apartment with high ceilings.",
    ):
        assert screen(description) == []


def test_measurements_require_local_ceiling_and_explicit_units():
    assert screen("10 ceilings. A 20 foot terrace. Spacious ceilings.") == []
    (item,) = by_feature("Ceiling height: approximately 10.5 feet.", "ceiling_height")
    assert item["value_feet"] == 10.5
    assert "approximate_or_bound_language" in item["flags"]


def test_context_is_bounded_even_without_sentence_boundaries():
    text = "word " * 10000 + "12 feet ceilings" + " word" * 10000
    (item,) = screen(text)
    assert len(item["context"]) <= 2 * CONTEXT_RADIUS + len(item["match"])


@pytest.mark.parametrize(
    "phrase", ["12-foot ceilings", "12-ft. ceilings", "12′-high ceilings"]
)
def test_hyphenated_explicit_measurements(phrase):
    (item,) = by_feature(phrase, "ceiling_height")
    assert item["value_feet"] == 12


def test_recovered_description_examples():
    assert by_feature("11 ft. high ceilings", "ceiling_height")[0]["value_feet"] == 11
    (item,) = by_feature("18 ft ceiling height in living room", "ceiling_height")
    assert item["value_feet"] == 18 and "room_specific_scope" in item["flags"]
    assert by_feature("10.5ft ceilings", "ceiling_height")[0]["value_feet"] == 10.5
    assert "value_feet" not in by_feature('9.7" ceilings', "ceiling_height")[0]
    assert "value_feet" not in by_feature('10’4" ceiling heights', "ceiling_height")[0]
    assert by_feature("11'-11'. Floor-to-ceiling windows", "ceiling_height") == []
    assert by_feature("terrace 11' x 14'; High-Ceilings", "ceiling_height") == []
    (item,) = by_feature("two duplex penthouses in the 11-story building", "levels")
    assert "other_or_multiple_units_scope" in item["flags"]
