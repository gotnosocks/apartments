from copy import deepcopy
import json

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import current_source_review as m


def fixture():
    row = {
        "audit_id": "a",
        "capture_id": "c",
        "source_listing_id": "123",
        "unit_id": "u",
        "canonical_unit_url": "https://streeteasy.com/building/example/1a",
        "known_at": "2026-09-18T12:00:00Z",
        "asking_rent": 6000.0,
        "building": "example",
        "bedrooms": 1,
        "bathrooms": 1,
        "reported_full_bathrooms": 1,
        "reported_half_bathrooms": 0,
        "bathroom_count_evidence": {"flags": [], "composition_status": "reported"},
        "analysis_price_basis": "current_capture_gross_ask",
    }
    evidence = {k: row[k] for k in m.IDENTITY}
    evidence.update(
        description="One full bath and an additional powder room.",
        collected_at="2026-09-18T11:00:00Z",
        body_sha256="a" * 64,
        raw_listing_sha256="b" * 64,
    )
    review = {k: row[k] for k in m.IDENTITY if k != "capture_id"}
    review.update(
        source_row_sha256=m.cohort.hashed(row),
        source_evidence_sha256=m.cohort.hashed(evidence),
        body_sha256=evidence["body_sha256"],
        raw_listing_sha256=evidence["raw_listing_sha256"],
        flags=[],
        wording_findings=[],
    )
    case = {
        "source_listing_id": "123",
        "action": "mask_bathroom_composition",
        "reason": "Conflicting source composition",
        "quotes": ["additional powder room"],
        "expected_reported_bathrooms": [1, 0],
        "residual_review_tags": ["bathroom_conflict"],
    }
    return row, evidence, review, case


def test_mask_preserves_original_values_and_input_and_records_review_clock():
    row, evidence, review, case = fixture()
    before = deepcopy(row)
    result, decision = m.apply_case(
        row, evidence, review, case, interpreted_at="2026-09-18T13:00:00Z"
    )
    assert row == before
    assert all(result[k] == v for k, v in row.items() if k != "bathroom_count_evidence")
    assert result["bathroom_count_evidence"]["flags"] == [m.MASK]
    assert (
        result["research_review_history"][0]["interpreted_at"] == "2026-09-18T13:00:00Z"
    )
    assert decision["evidence"][0]["literal"] == "additional powder room"


@pytest.mark.parametrize(
    "damage",
    [
        "row",
        "evidence",
        "identity",
        "hash",
        "clock",
        "quote",
        "counts",
        "action",
        "reason",
    ],
)
def test_invalid_review_refused(damage):
    row, evidence, review, case = fixture()
    at = "2026-09-18T13:00:00Z"
    if damage == "row":
        row["asking_rent"] = 7000
    if damage == "evidence":
        evidence["description"] += " altered"
    if damage == "identity":
        review["unit_id"] = "other"
    if damage == "hash":
        review["body_sha256"] = "c" * 64
    if damage == "clock":
        at = "2026-09-18T10:00:00Z"
    if damage == "quote":
        case["quotes"] = ["not present"]
    if damage == "counts":
        case["expected_reported_bathrooms"] = [2, 0]
    if damage == "action":
        case["action"] = "repair_price"
    if damage == "reason":
        case["reason"] = ""
    with pytest.raises(ValueError):
        m.apply_case(row, evidence, review, case, interpreted_at=at)


def test_unflagged_retention_preserves_row_and_flagged_requires_explicit_case():
    row, evidence, review, _ = fixture()
    policy = {
        "version": m.POLICY_VERSION,
        "interpreted_at": "2026-09-18T13:00:00Z",
        "cases": [],
    }
    out, decisions = m.assemble([row], [evidence], [review], policy)
    assert out == [row] and decisions[0]["action"] == "retain_source"
    review["flags"] = ["price_conflict"]
    with pytest.raises(ValueError, match="explicit review"):
        m.assemble([row], [evidence], [review], policy)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "absent_case"])
def test_coverage_and_named_review_identity(damage):
    row, evidence, review, case = fixture()
    policy = {
        "version": m.POLICY_VERSION,
        "interpreted_at": "2026-09-18T13:00:00Z",
        "cases": [case],
    }
    reviews = [review]
    if damage == "missing":
        reviews = []
    if damage == "duplicate":
        reviews *= 2
    if damage == "absent_case":
        case["source_listing_id"] = "other"
    with pytest.raises(ValueError):
        m.assemble([row], [evidence], reviews, policy)


def test_publication_replays_and_preserves_historical_rows(tmp_path):
    row, evidence, review, case = fixture()
    history = {
        **row,
        "audit_id": "old",
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
    }
    dataset, audit, policy, output = [
        tmp_path / p for p in ("dataset", "audit", "policy.json", "out")
    ]
    publish_bundle(
        dataset,
        {
            "observations.jsonl": canonical(history) + "\n" + canonical(row) + "\n",
            "current-source-evidence.jsonl": canonical(evidence) + "\n",
        },
        {"version": m.cohort.VERSION},
    )
    publish_bundle(
        audit,
        {"review.jsonl": canonical(review) + "\n"},
        {
            "version": m.audit.VERSION,
            "dataset_manifest_sha256": digest(dataset / "complete.json"),
            "dataset_observations_sha256": digest(dataset / "observations.jsonl"),
        },
    )
    rule = {
        "version": m.POLICY_VERSION,
        "interpreted_at": "2026-09-18T13:00:00Z",
        "cases": [case],
        "dataset_manifest_sha256": digest(dataset / "complete.json"),
        "audit_manifest_sha256": digest(audit / "complete.json"),
    }
    policy.write_text(canonical(rule))
    first = m.run(dataset, audit, policy, output)
    assert m.run(dataset, audit, policy, output) == first
    assert first["summary"]["action_counts"] == {"mask_bathroom_composition": 1}
    assert (
        json.loads((output / "observations.jsonl").read_text().splitlines()[0])
        == history
    )
    rule["dataset_manifest_sha256"] = "changed"
    policy.write_text(canonical(rule))
    with pytest.raises(ValueError, match="lineage"):
        m.run(dataset, audit, policy, output)
