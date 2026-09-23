from copy import deepcopy
from types import SimpleNamespace

import pytest

from apartments import elevator_corrections as lineage
from models.elevator_correction_projection import project


def fixture(mask=False):
    row = {
        "audit_id": "a",
        "source_listing_id": "42",
        "unit_id": "u",
        "building": "b",
        "elevator": True,
        "known_at": "2026-09-18T00:00:00Z",
        "capture_ids": [1],
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
        "asking_rent": 4000,
        "attribute_review_history": [{"id": "earlier"}],
    }
    text = "A non-elevator building."
    literal = {
        "audit_id": "a",
        "capture_id": 1,
        "known_at": row["known_at"],
        "description": text,
    }
    claim = {
        "attribute": "elevator",
        "value": False,
        "method": "description_pattern",
        "source_path": "/description",
        "start": 0,
        "end": len(text),
        "literal": text,
    }
    replay = {
        **literal,
        "building": "b",
        "stored_elevator": True,
        "after": {"value": None if mask else False, "claims": [claim], "conflicts": []},
    }
    if mask:
        replay["after"]["claims"].append(
            {
                "value": True,
                "attribute": "elevator",
                "method": "structured",
                "source_path": "/propertyDetails/amenities/list/0",
                "literal": "ELEVATOR",
            }
        )
        replay["after"]["conflicts"] = [True, False]
    edit = {
        "action": "edit",
        "id": "edit-a",
        "recorded_at": "2026-09-19T00:00:00Z",
        "target": {
            "source": "streeteasy",
            "source_listing_id": "42",
            "version_id": lineage.sha(row),
        },
        "validity": {"all_time": True},
        "patch": [
            {"op": "test", "path": "/elevator", "value": True},
            {"op": "replace", "path": "/elevator", "value": None if mask else False},
        ],
    }
    meta = {"active_ids": ["edit-a"], "corrections_as_of": "2026-09-19T01:00:00Z"}
    overlay = SimpleNamespace(active=[edit], manifest=meta)
    parent = {
        "version": lineage.PARENT,
        "files": {"observations.jsonl": lineage.records_hash([row])},
    }
    return row, literal, replay, overlay, parent


def manifest(parent, overlay, changes):
    return {
        "version": lineage.VERSION,
        "source_manifest": parent,
        "source_rows": 1,
        "source_manifest_sha256": lineage.records_hash([parent]),
        "overlay": overlay.manifest,
        "files": {lineage.SIDECAR: lineage.records_hash(changes)},
    }


def extend(parent, rows, index=1):
    """Layer an exact elevator revision onto a synthetic quarantined source."""
    row = rows[index]
    edit = {
        "action": "edit",
        "id": "elevator-revision",
        "recorded_at": "2026-09-19T07:00:00Z",
        "target": {
            "source": "streeteasy",
            "source_listing_id": row["source_listing_id"],
            "version_id": lineage.sha(row),
        },
        "validity": {"all_time": True},
        "patch": [
            {"op": "test", "path": "/elevator", "value": True},
            {"op": "replace", "path": "/elevator", "value": False},
        ],
    }
    overlay = {"active_ids": [edit["id"]], "corrections_as_of": "2026-09-19T08:00:00Z"}
    changes = [{"source_index": index, "observation": deepcopy(row), "edit": edit}]
    revised = deepcopy(rows)
    revised[index] = lineage.corrected_row(row, edit, overlay["corrections_as_of"])
    m = {
        "version": lineage.VERSION,
        "source_manifest": parent,
        "source_rows": len(rows),
        "source_manifest_sha256": lineage.records_hash([parent]),
        "overlay": overlay,
        "files": {
            lineage.SIDECAR: lineage.records_hash(changes),
            "observations.jsonl": lineage.records_hash(revised),
        },
    }
    return m, revised, changes


@pytest.mark.parametrize("mask", [False, True])
def test_projection_preserves_history_prices_clocks_and_exact_ordered_inverse(mask):
    row, literal, replay, overlay, parent = fixture(mask)
    before = deepcopy(row)
    revised, changes = project([row], {"a": [literal]}, [replay], overlay)
    assert row == before and revised[0]["elevator"] is (None if mask else False)
    assert (
        revised[0]["asking_rent"] == row["asking_rent"]
        and revised[0]["known_at"] == row["known_at"]
    )
    assert (
        revised[0]["attribute_review_history"][:-1] == row["attribute_review_history"]
    )
    assert lineage.parent_rows(
        manifest(parent, overlay, changes), revised, changes
    ) == (parent, [row])
    assert project([row], {"a": [literal]}, [replay], overlay) == (revised, changes)


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "duplicate",
        "typed_capture",
        "literal",
        "value",
        "unscoped",
        "clock",
        "unmatched",
    ],
)
def test_incomplete_or_misbound_capture_evidence_cannot_project(damage):
    row, literal, replay, overlay, _ = fixture()
    replays = [replay]
    if damage == "missing":
        replays = []
    if damage == "duplicate":
        replays.append(deepcopy(replay))
    if damage == "typed_capture":
        replay["capture_id"] = "1"
    if damage == "literal":
        replay["after"]["claims"][0]["literal"] = "non elevator"
    if damage == "value":
        replay["after"]["value"] = True
    if damage == "unscoped":
        literal["description"] = replay["description"] = "An unrelated sentence."
        replay["after"]["claims"][0].update(
            literal=literal["description"], end=len(literal["description"])
        )
    if damage == "clock":
        literal["known_at"] = replay["known_at"] = "2026-09-20T00:00:00Z"
    if damage == "unmatched":
        overlay.active[0]["target"]["version_id"] = "missing"
    with pytest.raises(ValueError):
        project([row], {"a": [literal]}, replays, overlay)


@pytest.mark.parametrize(
    "damage",
    [
        "extra_field",
        "rent",
        "history",
        "sidecar",
        "parent",
        "index",
        "active",
        "scope",
        "date",
        "replacement",
    ],
)
def test_inverse_refuses_unrelated_or_unreviewed_mutations(damage):
    row, literal, replay, overlay, parent = fixture()
    revised, changes = project([row], {"a": [literal]}, [replay], overlay)
    m = manifest(parent, overlay, changes)
    if damage == "extra_field":
        revised[0]["new"] = 1
    if damage == "rent":
        revised[0]["asking_rent"] = 3000
    if damage == "history":
        revised[0]["attribute_review_history"][0]["id"] = "altered"
    if damage == "sidecar":
        m["files"][lineage.SIDECAR] = "wrong"
    if damage == "parent":
        m["source_manifest_sha256"] = "wrong"
    if damage == "index":
        changes[0]["source_index"] = 1
    if damage == "active":
        m["overlay"]["active_ids"] = ["missing"]
    if damage == "scope":
        changes[0]["edit"]["target"]["version_id"] = "wrong"
    if damage == "date":
        changes[0]["edit"]["recorded_at"] = "2026-09-17T00:00:00Z"
    if damage == "replacement":
        changes[0]["edit"]["patch"][-1]["value"] = True
    if damage in ("index", "scope", "date", "replacement"):
        m["files"][lineage.SIDECAR] = lineage.records_hash(changes)
    with pytest.raises(ValueError):
        lineage.parent_rows(m, revised, changes)


def test_structured_conflict_cannot_be_forced_to_false():
    row, literal, replay, overlay, _ = fixture(mask=True)
    overlay.active[0]["patch"][-1]["value"] = replay["after"]["value"] = False
    with pytest.raises(ValueError, match="Opposing"):
        project([row], {"a": [literal]}, [replay], overlay)
