import pytest

from apartments.review_ledger import GENESIS, ReviewConflict, ReviewLedgerError
from apartments.unit_identity import (
    UnitIdentityLedger,
    expand_ids,
    identity_map,
    resolve_unit,
)


def merge(ledger, ids, request_id):
    return ledger.write(
        "merge",
        listing_ids=sorted(ids),
        review_revision=GENESIS,
        author="Ben",
        reason="Verified same home",
        request_id=request_id,
        expected_revision=ledger.revision(ledger.events()),
    )


def undo(ledger, event, request_id):
    return ledger.write(
        "undo",
        merge_id=event["id"],
        author="Ben",
        reason="Mistaken identity",
        request_id=request_id,
        expected_revision=ledger.revision(ledger.events()),
    )


def test_persistent_identity_expansion_and_dependent_undo(tmp_path):
    ledger = UnitIdentityLedger(tmp_path / "identities.jsonl", "dataset")
    first = merge(ledger, ["1", "2"], "first")
    reopened = UnitIdentityLedger(ledger.path, "dataset")
    assert (
        resolve_unit("1", reopened.events())
        == resolve_unit("2", reopened.events())
        == first["unit_id"]
    )
    assert resolve_unit("3", reopened.events()) == "streeteasy:rental:3"
    assert expand_ids(["1", "3"], reopened.events()) == ["1", "2", "3"]
    with pytest.raises(ValueError, match="every listing"):
        merge(reopened, ["1", "3"], "partial")
    second = merge(reopened, ["1", "2", "3"], "second")
    assert second["unit_id"] == first["unit_id"]
    with pytest.raises(ValueError, match="later merge"):
        undo(reopened, first, "wrong-order")
    undo(reopened, second, "undo-second")
    assert resolve_unit("3", reopened.events()) == "streeteasy:rental:3"
    assert resolve_unit("2", reopened.events()) == first["unit_id"]
    undo(reopened, first, "undo-first")
    assert identity_map(reopened.events()) == {}


def test_identity_retry_conflict_and_integrity(tmp_path):
    ledger = UnitIdentityLedger(tmp_path / "identities.jsonl", "dataset")
    args = dict(
        listing_ids=["1", "2"],
        review_revision=GENESIS,
        author="Ben",
        reason="same home",
        request_id="one",
        expected_revision=GENESIS,
    )
    saved = ledger.write("merge", **args)
    assert ledger.write("merge", **args) == saved
    assert len(ledger.events()) == 1
    with pytest.raises(ReviewConflict):
        ledger.write("merge", **{**args, "reason": "different"})
    with pytest.raises(ReviewConflict):
        ledger.write(
            "merge", **{**args, "request_id": "two", "listing_ids": ["3", "4"]}
        )
    ledger.path.write_text(ledger.path.read_text().replace("same home", "tampered"))
    with pytest.raises(ReviewLedgerError, match="hash chain"):
        ledger.events()


def test_merge_two_existing_units_and_restore(tmp_path):
    ledger = UnitIdentityLedger(tmp_path / "identities.jsonl", "dataset")
    a = merge(ledger, ["1", "2"], "a")
    b = merge(ledger, ["3", "4"], "b")
    both = merge(ledger, ["1", "2", "3", "4"], "both")
    assert set(identity_map(ledger.events()).values()) == {a["unit_id"]}
    undo(ledger, both, "undo")
    assert identity_map(ledger.events()) == {
        "1": a["unit_id"],
        "2": a["unit_id"],
        "3": b["unit_id"],
        "4": b["unit_id"],
    }


def test_association_batch_is_atomic_retryable_and_individually_reversible(tmp_path):
    from apartments.unit_identity import active_decisions

    ledger = UnitIdentityLedger(tmp_path / "units.jsonl", "dataset")
    args = dict(
        proposals=[
            {"listing_ids": ["1", "2"], "evidence": {"canonical_url": "/building/a/1"}},
            {"listing_ids": ["3", "4"], "evidence": {"canonical_url": "/building/a/2"}},
        ],
        review_revision=GENESIS,
        author="Ben",
        reason="Source associations",
        request_id="batch",
        expected_revision=GENESIS,
    )
    event = ledger.write("associate_batch", **args)
    assert ledger.write("associate_batch", **args) == event
    assert len(ledger.events()) == 1  # Entire batch is one committed ledger record.
    assert len(set(identity_map(ledger.events()).values())) == 2
    assert {e["basis"] for e in active_decisions(ledger.events())} == {"streeteasy"}
    first = active_decisions(ledger.events())[0]
    manual = merge(ledger, ["1", "2", "5"], "expanded")
    with pytest.raises(ValueError, match="later merge"):
        ledger.write(
            "undo_batch",
            batch_id=event["id"],
            author="Ben",
            reason="undo",
            request_id="undo-batch",
            expected_revision=ledger.revision(ledger.events()),
        )
    undo(ledger, manual, "undo-manual")
    undo(ledger, first, "undo-individual")
    assert set(identity_map(ledger.events())) == {"3", "4"}
    undo_args = dict(
        batch_id=event["id"],
        author="Ben",
        reason="undo",
        request_id="undo-batch",
        expected_revision=ledger.revision(ledger.events()),
    )
    result = ledger.write("undo_batch", **undo_args)
    assert ledger.write("undo_batch", **undo_args) == result
    assert identity_map(ledger.events()) == {}
    with pytest.raises(ValueError, match="distinct"):
        ledger.write(
            "associate_batch",
            **{
                **args,
                "proposals": [args["proposals"][0], args["proposals"][0]],
                "request_id": "invalid",
                "expected_revision": ledger.revision(ledger.events()),
            },
        )
    assert len(ledger.events()) == 5


def separate(ledger, ids, request_id="separate"):
    return ledger.write(
        "separate",
        listing_ids=sorted(ids),
        review_revision=GENESIS,
        author="Ben",
        reason="Different homes",
        request_id=request_id,
        expected_revision=ledger.revision(ledger.events()),
    )


def test_keep_separate_preserves_units_blocks_crossing_merges_and_is_reversible(
    tmp_path,
):
    ledger = UnitIdentityLedger(tmp_path / "identities.jsonl", "dataset")
    merged = merge(ledger, ["1", "2"], "merged")
    before = identity_map(ledger.events())
    with pytest.raises(ValueError, match="every listing"):
        separate(ledger, ["1", "3"])
    with pytest.raises(ValueError, match="already belong"):
        separate(ledger, ["1", "2"])
    saved = separate(ledger, ["1", "2", "3"])
    assert saved["groups"] == [["1", "2"], ["3"]]
    assert identity_map(ledger.events()) == before
    assert separate(ledger, ["1", "2", "3"]) == saved
    with pytest.raises(ValueError, match="keep-separate"):
        merge(ledger, ["1", "2", "3"], "blocked")
    # A new member of either home cannot be used to bypass the saved decision.
    merge(ledger, ["1", "2", "4"], "expand")
    with pytest.raises(ValueError, match="keep-separate"):
        merge(ledger, ["1", "2", "3", "4"], "indirect")
    args = dict(
        separation_id=saved["id"],
        author="Ben",
        reason="Reconsidered",
        request_id="undo-separate",
        expected_revision=ledger.revision(ledger.events()),
    )
    undo_event = ledger.write("undo_separate", **args)
    assert ledger.write("undo_separate", **args) == undo_event
    assert (
        merge(ledger, ["1", "2", "3", "4"], "allowed")["unit_id"] == merged["unit_id"]
    )


def test_keep_separate_prevents_batch_association_and_stale_decisions(tmp_path):
    ledger = UnitIdentityLedger(tmp_path / "identities.jsonl", "dataset")
    saved = separate(ledger, ["1", "2"])
    with pytest.raises(ReviewConflict):
        ledger.write(
            "separate",
            listing_ids=["3", "4"],
            author="Ben",
            reason="Different",
            request_id="stale",
            expected_revision=GENESIS,
        )
    with pytest.raises(ValueError, match="keep-separate"):
        ledger.write(
            "associate_batch",
            proposals=[{"listing_ids": ["1", "2"], "evidence": {}}],
            author="Ben",
            reason="source",
            request_id="batch",
            expected_revision=saved["hash"],
        )
    assert len(ledger.events()) == 1
