from copy import deepcopy

import pytest

from models.floor_label_conflict_review import adjudicate


def fixture():
    conflict = {
        "audit_id": "a",
        "unit_id": "u",
        "building": "b",
        "candidate_floor": 3,
        "explicit_floor": 4,
    }
    evidence = {
        "audit_id": "a",
        "unit_id": "u",
        "source_listing_id": "123",
        "capture_id": 1,
        "body_sha256": "body",
        "raw_listing_sha256": "raw",
        "description": "The unit is on the 4th floor (3 flights up).",
        "known_at": "2026-09-18T10:00:00+00:00",
    }
    label = {**conflict, **evidence, "literal": "#3A"}
    policy = {
        "reviewer": "test reviewer",
        "interpreted_at": "2026-09-19T00:00:00+00:00",
        "cases": [
            {
                "audit_id": "a",
                "source_listing_id": "123",
                "expected_candidate_floor": 3,
                "expected_explicit_floor": 4,
                "decision": "retain_explicit_floor_claim",
                "interpretation": "supported_local_offset",
                "reason": "The own-unit floor and flight count agree.",
            }
        ],
    }
    return [conflict], [label], {"a": [evidence]}, policy


def test_complete_review_preserves_labels_and_literal_claims_without_patching():
    args = fixture()
    before = deepcopy(args)
    result = adjudicate(*args)
    assert args == before
    row = result[0]
    assert row["proposed_analytical_floor"] == 4
    assert row["label_prefix_validated_as_floor"] is False
    capture = row["captures"][0]
    assert capture["label_evidence"]["literal"] == "#3A"
    for span in capture["review_spans"]:
        assert capture["description"][span["start"] : span["end"]] == span["literal"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_decision",
        "extra_decision",
        "typed_capture",
        "wrong_hash",
        "wrong_floor",
        "late_evidence",
        "missing_support",
        "other_unit_support",
    ],
)
def test_incomplete_or_misbound_manual_reviews_are_rejected(fault):
    conflicts, labels, evidence, policy = fixture()
    if fault == "missing_decision":
        policy["cases"] = []
    if fault == "extra_decision":
        policy["cases"].append({**policy["cases"][0], "audit_id": "extra"})
    if fault == "typed_capture":
        labels[0]["capture_id"] = "1"
    if fault == "wrong_hash":
        labels[0]["body_sha256"] = "another"
    if fault == "wrong_floor":
        policy["cases"][0]["expected_candidate_floor"] = 2
    if fault == "late_evidence":
        evidence["a"][0]["known_at"] = "2026-09-20T00:00:00+00:00"
    if fault in ("missing_support", "other_unit_support"):
        policy["cases"][0]["supporting_advertisements"] = ["456"]
    if fault == "other_unit_support":
        evidence["b"] = [
            {**evidence["a"][0], "unit_id": "different", "source_listing_id": "456"}
        ]
    with pytest.raises(ValueError):
        adjudicate(conflicts, labels, evidence, policy)


def test_media_reference_and_source_conflict_recommend_unknown_floor():
    for decision in (
        "withhold_floor_due_to_scope",
        "withhold_floor_due_to_source_conflict",
    ):
        args = fixture()
        args[-1]["cases"][0]["decision"] = decision
        assert adjudicate(*args)[0]["proposed_analytical_floor"] is None
