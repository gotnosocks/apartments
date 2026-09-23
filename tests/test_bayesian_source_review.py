from copy import deepcopy

import pytest

from apartments import bayesian_source_review as m
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    experiment, dataset, evidence = [
        tmp_path / name for name in ("fit", "data", "evidence")
    ]
    row = {
        "audit_id": "a",
        "source_listing_id": "123",
        "unit_id": "u",
        "bedrooms": 0,
        "analysis_price_basis": "current_capture_gross_ask",
    }
    residual = {"audit_id": "a", "asking_rent": 3450.0, "fitted_rent": 2885.0}
    captures = [{"capture_id": "refresh:1", "description": "One-bedroom apartment."}]
    publish_bundle(
        dataset, {"observations.jsonl": canonical(row) + "\n"}, {"version": "test"}
    )
    publish_bundle(
        experiment / "fit",
        {"residuals.jsonl": canonical(residual) + "\n"},
        {"version": "test"},
    )
    publish_bundle(evidence, {"evidence.jsonl": ""}, {"version": "test"})
    monkeypatch.setattr(m, "load_evidence", lambda *args: {"a": deepcopy(captures)})
    case = {
        "source_listing_id": "123",
        "residual": residual,
        "joint_posterior_detail": {"source_record": row},
        "source_captures": deepcopy(captures),
        "review_kind": "bedroom_count_conflict",
        "review_reason": "Count conflicts; do not resolve using rent.",
    }
    metadata = {
        "version": "current-residual-source-case-review-v1",
        "fit_manifest_sha256": digest(experiment / "fit/complete.json"),
        "dataset_manifest_sha256": digest(dataset / "complete.json"),
        "descriptions_manifest_sha256": digest(evidence / "complete.json"),
    }
    return experiment, dataset, evidence, case, metadata


def publish_and_read(inputs, path, cases=None):
    experiment, dataset, evidence, case, metadata = inputs
    cases = cases if cases is not None else [case]
    publish_bundle(
        path,
        {
            "cases.jsonl": "".join(canonical(c) + "\n" for c in cases),
            "summary.json": canonical(
                {"version": metadata["version"], "cases": len(cases)}
            )
            + "\n",
        },
        metadata,
    )
    return m.load_source_review(experiment, dataset, path, evidence=evidence)


def test_verified_notes_do_not_change_counts_or_prices(inputs, tmp_path):
    original = deepcopy(inputs[3])
    notes = publish_and_read(inputs, tmp_path / "review")
    assert notes["a"]["interpretation_limited"] is True
    assert notes["a"]["message"] == original["review_reason"]
    assert inputs[3] == original


@pytest.mark.parametrize(
    "fault",
    ["fit", "dataset", "evidence", "count", "residual", "capture", "advertisement"],
)
def test_notes_cannot_follow_a_different_model_or_source(inputs, tmp_path, fault):
    _, _, _, case, metadata = inputs
    if fault in {"fit", "dataset"}:
        metadata[fault + "_manifest_sha256"] = "wrong"
    if fault == "evidence":
        metadata["descriptions_manifest_sha256"] = "wrong"
    if fault == "count":
        case["joint_posterior_detail"]["source_record"]["bedrooms"] = 1
    if fault == "residual":
        case["residual"]["asking_rent"] = 1
    if fault == "capture":
        case["source_captures"][0]["description"] = "Changed"
    if fault == "advertisement":
        case["source_listing_id"] = "999"
    with pytest.raises(ValueError):
        publish_and_read(inputs, tmp_path / "review")


def test_duplicate_notes_are_rejected(inputs, tmp_path):
    with pytest.raises(ValueError):
        publish_and_read(inputs, tmp_path / "review", [inputs[3], deepcopy(inputs[3])])
