import json

import pytest

from apartments.review_ledger import ReviewConflict, ReviewLedger, ReviewLedgerError


def test_atomic_batch_replay_retraction_and_raw_immutability(tmp_path):
    path = tmp_path / "review.jsonl"
    ledger = ReviewLedger(path, "apt-dataset")
    raw = {
        "bedrooms": 1,
        "amenities": {"nested": {"bath": "half"}},
        "archive_listing": {"id": 42},
    }
    before = json.loads(json.dumps(raw))
    rev = ledger.revision()
    edit = ledger.correct(
        [9, 3],
        [
            {"op": "replace", "path": "/bedrooms", "value": 2},
            {"op": "replace", "path": "/amenities/nested/bath", "value": "full"},
        ],
        "reviewer",
        "verified against listing",
        rev,
    )
    assert edit["snapshot_ids"] == [3, 9]
    assert len(ledger.events()) == 1
    corrected, evidence = ledger.apply(raw, 3)
    assert corrected["bedrooms"] == 2
    assert corrected["amenities"]["nested"]["bath"] == "full"
    assert evidence[0]["id"] == edit["id"]
    assert raw == before
    ledger.retract(
        edit["id"], "reviewer", "source correction was mistaken", ledger.revision()
    )
    assert ledger.apply(raw, 3) == (raw, [])


def test_stale_revision_and_invalid_scope_rejected(tmp_path):
    ledger = ReviewLedger(tmp_path / "review.jsonl", "dataset")
    rev = ledger.revision()
    ledger.record_review(1, "identity", "confirmed", "matches unit", "a")
    with pytest.raises(ReviewConflict):
        ledger.correct(
            [1], [{"op": "replace", "path": "/bedrooms", "value": 1}], "a", "fix", rev
        )
    with pytest.raises(ReviewLedgerError):
        ledger.correct(
            [1],
            [{"op": "replace", "path": "/archive_listing/id", "value": 2}],
            "a",
            "fix",
            ledger.revision(),
        )


def test_correct_request_id_is_idempotent(tmp_path):
    ledger = ReviewLedger(tmp_path / "review.jsonl", "dataset")
    rev = ledger.revision()
    args = (
        [7],
        [{"op": "replace", "path": "/bedrooms", "value": 1}],
        "a",
        "checked",
        rev,
    )
    first = ledger.correct(*args, request_id="preview-1")
    retry = ledger.correct(*args, request_id="preview-1")
    assert first["id"] == retry["id"]
    assert len(ledger.events()) == 1
    with pytest.raises(ReviewConflict):
        ledger.correct([8], args[1], "a", "checked", rev, request_id="preview-1")


def test_nested_add_applies_and_integrity_detects_corruption_and_truncation(tmp_path):
    path = tmp_path / "review.jsonl"
    ledger = ReviewLedger(path, "d")
    ledger.correct(
        [1],
        [{"op": "replace", "path": "/amenities/nested/extra", "value": True}],
        "a",
        "observed",
        ledger.revision(),
    )
    with pytest.raises(ReviewLedgerError, match="cannot apply"):
        ledger.apply({"amenities": {"nested": {}}}, 1)
    events = ledger.events()
    assert (
        ledger.apply({"amenities": {"nested": {"extra": False}}}, 1, events=events)[0][
            "amenities"
        ]["nested"]["extra"]
        is True
    )
    assert [e["id"] for e in ledger.active_corrections()] == [events[0]["id"]]
    path.write_text(path.read_text().replace("observed", "tampered"))
    with pytest.raises(ReviewLedgerError, match="hash chain"):
        ledger.events()
    path.write_text(path.read_text().rstrip("\n"))
    with pytest.raises(ReviewLedgerError, match="Incomplete"):
        ledger.events()


def test_open_attribute_schema_and_protected_metadata(tmp_path):
    ledger = ReviewLedger(tmp_path / "review.jsonl", "d")
    patches = [
        {"op": "add", "path": "/bathrooms", "value": 1},
        {"op": "add", "path": "/room_count", "value": 4},
        {"op": "add", "path": "/actual_floor", "value": 3},
    ]
    raw = {"archive_listing": {"id": 71}}
    for patch in patches:
        ledger.correct(
            [1], [patch], "reviewer", "observed attribute", ledger.revision()
        )
    corrected, _ = ledger.apply(raw, 1)
    assert (
        corrected["bathrooms"],
        corrected["room_count"],
        corrected["actual_floor"],
    ) == (1, 4, 3)
    with pytest.raises(ReviewLedgerError):
        ledger.correct(
            [1],
            [{"op": "replace", "path": "/archive_listing/id", "value": 72}],
            "reviewer",
            "attempt metadata change",
            ledger.revision(),
        )
    with pytest.raises(ReviewLedgerError):
        ledger.correct(
            [1],
            [{"op": "add", "path": "/captured_at", "value": "2026-09-16"}],
            "reviewer",
            "attempt envelope edit",
            ledger.revision(),
        )
