import hashlib
from copy import deepcopy

import pytest

from apartments.interior_evidence import screen
from apartments.interior_projection import project


def capture(text, identity=1, **kwargs):
    return {
        "capture_id": identity,
        "description": text,
        "findings": screen(text),
        "description_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "audit_id": "row1",
        "source_listing_id": "ad1",
        **kwargs,
    }


def test_advertised_room_height_is_not_typical_home_height():
    result = project(
        [
            capture(
                "☀ This duplex has 18’ skylit livingroom ceilings. A floor-through home."
            )
        ]
    )
    assert result["features"] == {
        "advertised_ceiling_feet": 18.0,
        "advertised_levels": 2,
        "floor_through_mention": 1,
        "skylight_mention": 1,
    }
    height = next(
        e for e in result["evidence"] if e["feature"] == "advertised_ceiling_feet"
    )
    assert "room_specific_scope" in height["finding"]["flags"]
    assert height["accepted"] and height["capture_id"] == 1


def test_unknown_not_absence_and_no_latest_capture_backfill():
    assert set(project([])["features"].values()) == {None}
    result = project([capture("A pleasant home.")])
    assert set(result["features"].values()) == {None}
    a = capture("10 foot ceilings.", 1)
    b = capture("12 foot ceilings.", 2)
    result = project([a, b])
    assert result == project([b, a])
    assert result["features"]["advertised_ceiling_feet"] is None
    assert (
        "conflicting_accepted_values"
        in result["decisions"]["advertised_ceiling_feet"]["reasons"]
    )


def test_agreeing_captures_and_unmentioned_capture_do_not_mean_absence():
    result = project(
        [
            capture("A single-level home. 10 foot ceilings.", 1),
            capture("10-foot ceilings.", 2),
            capture("A pleasant home.", 3),
        ]
    )
    assert result["features"]["advertised_ceiling_feet"] == 10
    assert result["features"]["advertised_levels"] == 1
    assert result["decisions"]["advertised_ceiling_feet"]["accepted_capture_ids"] == [
        1,
        2,
    ]


@pytest.mark.parametrize(
    "text",
    [
        '10" ceilings.',
        "10 to 12 foot ceilings.",
        "10′ 6″ ceilings.",
        "Around 10 foot ceilings.",
        "10 foot plus ceilings.",
        "10 foot ceilings +.",
        "Between 10 and 12 foot ceilings.",
        "20 x 12 foot ceilings.",
        "12 foot x 20 foot ceilings.",
        "Over 12 foot ceilings.",
        "Approximately 12 foot ceilings.",
        "12 foot ceilings or more.",
        "9.5 FT floor to ceiling windows.",
    ],
)
def test_height_ambiguity_unknown(text):
    assert project([capture(text)])["features"]["advertised_ceiling_feet"] is None


@pytest.mark.parametrize(
    "text",
    [
        "No skylights.",
        "Could convert to a duplex.",
        "Select apartments feature a duplex.",
        "A multi-level home.",
        "The gallery has a skylight.",
        "Commercial space. A duplex with 12 foot ceilings.",
        "Building Amenities:\nSkylight\n12 foot ceilings",
        "A duplex. Currently undergoing renovation.",
        "Skylight. Photos show pre-renovation condition.",
        "A duplex. All new renovations will be complete for a 5/1 lease start.",
        "A two-level roof garden.",
        "This boutique building has a total of 6 floor-through apartments.",
        "All wood floor through.",
    ],
)
def test_scope_polarity_plans_and_indeterminate_levels(text):
    result = project([capture(text)])
    assert set(result["features"].values()) == {None}
    assert any(not e["accepted"] for e in result["evidence"])


def test_ambiguous_candidate_blocks_other_accepted_candidate_same_feature():
    result = project(
        [capture("This duplex is spacious. Other duplex apartments available.")]
    )
    assert result["features"]["advertised_levels"] is None
    assert result["decisions"]["advertised_levels"]["accepted_candidate_count"] == 1
    result = project([capture("A duplex.", 1), capture("Could become a triplex.", 2)])
    assert result["features"]["advertised_levels"] is None


def test_flags_not_silently_ignored_and_completed_renovation_not_global_plan():
    result = project([capture("Newly renovated. A duplex with 12 foot ceilings.")])
    assert result["features"]["advertised_levels"] == 2
    assert result["features"]["advertised_ceiling_feet"] == 12
    assert (
        project([capture("Newly renovated duplex with 12 foot ceilings.")])["features"][
            "advertised_levels"
        ]
        is None
    )


@pytest.mark.parametrize("mutation", ["offset", "text", "omit", "hash", "flag"])
def test_tampered_or_incomplete_evidence_rejected(mutation):
    row = capture("A duplex with 12 foot ceilings.")
    if mutation == "offset":
        row["findings"][0]["start"] += 1
    elif mutation == "text":
        row["findings"][0]["match"] = "triplex"
    elif mutation == "omit":
        row["findings"].pop()
    elif mutation == "hash":
        row["description_sha256"] = "f" * 64
    else:
        row["findings"][0]["flags"].append("invented")
    with pytest.raises(ValueError):
        project([row])


def test_duplicate_capture_or_cross_advertisement_rejected():
    a = capture("A duplex.")
    with pytest.raises(ValueError, match="Duplicate"):
        project([a, deepcopy(a)])
    with pytest.raises(ValueError, match="Duplicate"):
        project([a, capture("A duplex.", "1")])
    with pytest.raises(ValueError, match="one analytical row"):
        project([a, capture("A duplex.", 2, source_listing_id="ad2")])


def test_projection_does_not_mutate_input():
    rows = [capture("The living room has 12 foot ceilings.")]
    before = deepcopy(rows)
    project(rows)
    assert rows == before


@pytest.mark.parametrize(
    "text",
    [
        "Two level Children’s playroom for kids of all ages.",
        "Two-level play room for children.",
        "The recreation room has 12 foot ceilings.",
        "A skylight above the recreational area.",
        "The pool has a skylight.",
        "Two-level rec room.",
    ],
)
def test_shared_play_recreation_and_pool_scope(text):
    result = project([capture(text)])
    assert set(result["features"].values()) == {None}
    assert result["evidence"]
    assert all(
        "local_nonunit_scope_ambiguity" in e["rejection_reasons"]
        for e in result["evidence"]
    )


@pytest.mark.parametrize(
    "text",
    [
        "10.5 &#39; CEILINGS FOUR CLOSETS 28 FT LONG LIVING ROOM",
        "11'?2? ceiling height and thirteen 7'?9? double-paned quiet windows",
        "11'5 ft ceilings",
        "11' 5 ft ceilings",
        "Ceiling height 11'?5?",
    ],
)
def test_bad_reverse_link_and_malformed_compound_height(text):
    result = project([capture(text)])
    assert result["evidence"]
    assert result["features"]["advertised_ceiling_feet"] is None


@pytest.mark.parametrize(
    "text",
    [
        "Ceiling height: 11 feet.",
        "Ceilings are 11 feet.",
        "Ceiling heights of 11 feet.",
    ],
)
def test_explicit_reverse_height_grammar_preserved(text):
    assert project([capture(text)])["features"]["advertised_ceiling_feet"] == 11


@pytest.mark.parametrize(
    "text",
    [
        "This home is elevated one level up from ground level.",
        "Among the units is an exceptional simplex on a single level.",
        "Among the units is an exceptional simplex. It occupies a single level.",
    ],
)
def test_elevation_and_buildingwide_one_level_not_unit_layout(text):
    result = project([capture(text)])
    assert result["evidence"]
    assert result["features"]["advertised_levels"] is None


def test_clean_one_level_layout_preserved():
    assert (
        project([capture("The unit boasts an efficient one-level layout.")])[
            "features"
        ]["advertised_levels"]
        == 1
    )
