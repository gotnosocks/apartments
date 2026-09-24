from copy import deepcopy

import pytest

from apartments.building_field_recovery import recover_records
from streeteasy_archive.flight import FlightText


def example():
    original = {"id": "12", "slug": "building", "amenities": "$a", "nyc": "$b"}
    records = {
        "1": {"building": original},
        "a": {"list": ["FIOS_AVAILABLE"]},
        "b": {"buildingClass": "C6", "buildingClassDescription": "$c"},
        "c": FlightText("Walk Up, Cooperative"),
    }
    return original, records


def test_literal_recovery_preserves_missing_and_source():
    original, records = example()
    before = deepcopy((original, records))
    result = recover_records(records, original)
    assert (
        result["fields"]["nyc"]["resolved"]["buildingClassDescription"]
        == "Walk Up, Cooperative"
    )
    assert result["fields"]["amenities"]["resolved"] == {"list": ["FIOS_AVAILABLE"]}
    assert result["fields"]["additionalDetails"] == {
        "present": False,
        "original": None,
        "resolved": None,
    }
    assert result["resolved_record_ids"] == ["a", "b", "c"]
    assert (original, records) == before
    assert "elevator" not in result


@pytest.mark.parametrize(
    "fault", ["wrong_object", "cycle", "missing_reference", "depth"]
)
def test_unbound_or_unresolved_fields_rejected(fault):
    original, records = example()
    if fault == "wrong_object":
        original = {**original, "slug": "other"}
    elif fault == "cycle":
        records["c"] = "$b"
    elif fault == "missing_reference":
        del records["c"]
    else:
        value = "end"
        for _ in range(66):
            value = [value]
        records["a"] = value
    with pytest.raises(ValueError):
        recover_records(records, original)


def test_text_that_looks_like_a_reference_is_literal():
    original, records = example()
    records["c"] = FlightText("$dead")
    assert (
        recover_records(records, original)["fields"]["nyc"]["resolved"][
            "buildingClassDescription"
        ]
        == "$dead"
    )
