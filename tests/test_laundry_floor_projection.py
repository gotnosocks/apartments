from copy import deepcopy
import json

import pytest

from apartments import laundry_floor_split as split
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import laundry_floor_projection as projection
from tests.test_reviewed_source_lineage import observations_hash

CLOCK = "2026-09-19T08:00:00Z"
SHA = "a" * 64


def capture(row, capture_id):
    return {
        **{
            k: row[k]
            for k in (
                "audit_id",
                "unit_id",
                "building",
                "source_listing_id",
                "laundry_type",
            )
        },
        "capture_id": capture_id,
        "body_sha256": SHA,
        "raw_listing_sha256": SHA,
        "description_sha256": SHA,
        "source_collected_at": row["known_at"],
        "known_at": row["known_at"],
        "measurement": {
            "most_convenient_reported_option": "on_floor",
            "states": {"shared_same_floor": True},
            "conflicts": [],
            "installation_review_required": False,
            "claims": [
                {
                    "scope": "shared_same_floor",
                    "present": True,
                    "source_path": "/description",
                    "start": 0,
                    "end": 21,
                    "literal": "laundry on each floor",
                }
            ],
        },
    }


def extend(parent, rows, index=2):
    """Add an actual split after valid correction lineage in reader fixtures."""
    updated = deepcopy(rows)
    row = updated[index]
    assert row["laundry_type"] == "in_building"
    # Fixture callers must establish capture membership before hashing ancestors.
    group = [capture(row, cid) for _, cid in split.capture_ids(row)]
    revised, _ = projection.assemble([row], group, SHA, CLOCK)
    updated[index] = revised[0]
    return {
        "version": split.VERSION,
        "source_manifest": parent,
        "source_manifest_sha256": split.manifest_hash(parent),
        "measurement_manifest_sha256": SHA,
        "interpreted_at": CLOCK,
        "changed_audit_ids": [row["audit_id"]],
        "files": {"observations.jsonl": observations_hash(updated)},
    }, updated


def fixture():
    rows = [
        {
            "audit_id": str(i),
            "unit_id": "u" + str(i),
            "building": "b",
            "source_listing_id": str(100 + i),
            "capture_ids": [i, str(i)],
            "known_at": "2026-09-18T00:00:00Z",
            "asking_rent": 3000 + i,
            "analysis_price_basis": "historical_initial_own_advertisement_ask",
            "laundry_type": category,
        }
        for i, category in enumerate(
            ["in_building", None, "in_unit", "none", "in_building"]
        )
    ]
    captures = [capture(row, cid) for row in rows for cid in row["capture_ids"]]
    # A second capture is ambiguous: preserve the whole fifth row.
    captures[-1]["measurement"]["most_convenient_reported_option"] = None
    parent = {
        "version": split.PARENT,
        "files": {"observations.jsonl": observations_hash(rows)},
    }
    revised, changes = projection.assemble(rows, captures, SHA, CLOCK)
    manifest = {
        "version": split.VERSION,
        "source_manifest": parent,
        "source_manifest_sha256": split.manifest_hash(parent),
        "measurement_manifest_sha256": SHA,
        "interpreted_at": CLOCK,
        "changed_audit_ids": [c["audit_id"] for c in changes],
    }
    return rows, captures, revised, manifest


def test_only_unanimous_accepted_building_laundry_changes_and_exact_inverse():
    rows, _, revised, manifest = fixture()
    assert revised[0]["laundry_type"] == "on_floor"
    assert revised[1:] == rows[1:]
    assert split.parent_rows(manifest, revised) == (manifest["source_manifest"], rows)
    assert rows[0]["laundry_type"] == "in_building"
    assert split.FIELD in revised[0]  # Inverse does not mutate inputs.


@pytest.mark.parametrize(
    "fault",
    ["missing_capture", "duplicate_capture", "typed_id", "foreign_ad", "category"],
)
def test_assembly_requires_complete_exact_capture_membership(fault):
    rows, captures, _, _ = fixture()
    if fault == "missing_capture":
        captures.pop(0)
    elif fault == "duplicate_capture":
        captures.append(deepcopy(captures[0]))
    elif fault == "typed_id":
        captures[0]["capture_id"] = 99
    elif fault == "foreign_ad":
        captures[0]["source_listing_id"] = "wrong"
    elif fault == "category":
        captures[0]["laundry_type"] = None
    with pytest.raises(ValueError):
        projection.assemble(rows, captures, SHA, CLOCK)


@pytest.mark.parametrize("fault", ["conflict", "installation", "absent", "unspecified"])
def test_any_attached_capture_can_withhold_the_split(fault):
    rows, captures, _, _ = fixture()
    measurement = captures[1]["measurement"]
    if fault == "conflict":
        measurement["conflicts"] = ["contradiction"]
    elif fault == "installation":
        measurement["installation_review_required"] = True
    elif fault == "absent":
        measurement["states"]["shared_same_floor"] = False
    elif fault == "unspecified":
        measurement["most_convenient_reported_option"] = "in_building"
    revised, changes = projection.assemble(rows, captures, SHA, CLOCK)
    assert revised == rows and changes == []


@pytest.mark.parametrize(
    "fault",
    [
        "price",
        "clock",
        "order",
        "extra_field",
        "missing_claim",
        "negative_claim",
        "span",
        "hash",
        "future_capture",
        "interpretation",
        "unlisted",
        "coverage",
    ],
)
def test_inverse_rejects_source_and_evidence_mutations_even_rehashed(fault):
    _, _, rows, manifest = fixture()
    evidence = rows[0][split.FIELD]
    c = evidence["captures"][0]
    if fault == "price":
        rows[0]["asking_rent"] += 1
    elif fault == "clock":
        rows[1]["known_at"] = "2026-09-17T00:00:00Z"
    elif fault == "order":
        rows.reverse()
    elif fault == "extra_field":
        rows[2]["invented"] = True
    elif fault == "missing_claim":
        c["same_floor_claims"] = []
    elif fault == "negative_claim":
        c["same_floor_claims"][0]["present"] = False
    elif fault == "span":
        c["same_floor_claims"][0]["end"] = 22
    elif fault == "hash":
        del c["description_sha256"]
    elif fault == "future_capture":
        c["known_at"] = "2026-09-20T00:00:00Z"
    elif fault == "interpretation":
        manifest["interpreted_at"] = "2026-09-17T00:00:00Z"
    elif fault == "unlisted":
        manifest["changed_audit_ids"] = ["other"]
    elif fault == "coverage":
        evidence["captures"].pop()
    manifest["files"] = {"observations.jsonl": observations_hash(rows)}
    with pytest.raises(ValueError):
        split.parent_rows(manifest, rows)


def test_projection_publishes_idempotently_and_binds_measurement(tmp_path):
    rows, captures, _, _ = fixture()
    source, measurement, output = [
        tmp_path / name for name in ("source", "measurement", "output")
    ]
    publish_bundle(
        source,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"version": split.PARENT},
    )
    publish_bundle(
        measurement,
        {"captures.jsonl": "".join(canonical(c) + "\n" for c in captures)},
        {
            "version": "full-cohort-scoped-laundry-measurement-v1",
            "dataset_manifest_sha256": digest(source / "complete.json"),
        },
    )
    result = projection.run(source, measurement, CLOCK, output)
    assert result["changed_rows"] == 1 and result["changed_current_rows"] == 0
    before = {p.name: digest(p) for p in output.iterdir()}
    assert projection.run(source, measurement, CLOCK, output) == result
    assert before == {p.name: digest(p) for p in output.iterdir()}
    manifest = json.loads((output / "complete.json").read_text())
    published = [
        json.loads(line)
        for line in (output / "observations.jsonl").read_text().splitlines()
    ]
    assert split.parent_rows(manifest, published)[1] == rows
