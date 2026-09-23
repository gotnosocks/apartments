from copy import deepcopy

import pytest

from models.refresh_bayesian_evidence import assemble


def inputs():
    history = {
        "audit_id": "old",
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
        "capture_ids": [1],
        "asking_rent": 4000,
    }
    current = {
        "audit_id": "current",
        "analysis_price_basis": "current_capture_gross_ask",
        "capture_id": "new",
        "source_listing_id": "123",
        "unit_id": "u",
        "canonical_unit_url": "url",
        "known_at": "2026-09-18T12:00:00Z",
        "collected_at": "2026-09-18T11:00:00Z",
        "source_raw_sha256": "raw",
        "refresh_provenance": {"body_sha256": "body"},
    }
    evidence = {
        k: v
        for k, v in current.items()
        if k not in ("analysis_price_basis", "source_raw_sha256", "refresh_provenance")
    }
    evidence.update(
        description="New literal\u2028text",
        body_sha256="body",
        raw_listing_sha256="raw",
    )
    mapping = {
        "old": [{"audit_id": "old", "capture_id": 1, "description": "Old literal"}]
    }
    return [history], [deepcopy(history), current], [evidence], mapping


def test_combine_preserves_history_and_own_current_literal_without_latest_backfill():
    parent, rows, evidence, mapping = inputs()
    before = deepcopy((parent, rows, evidence, mapping))
    out = assemble(parent, rows, evidence, mapping)
    assert (parent, rows, evidence, mapping) == before
    assert out[0]["description"] == evidence[0]["description"]
    assert out[1] == mapping["old"][0]
    assert out[0]["description_source"] == "verified_current_own_listing"


@pytest.mark.parametrize(
    "fault",
    [
        "history",
        "historical_capture",
        "missing_current",
        "duplicate_current",
        "identity",
        "raw_hash",
        "body_hash",
        "clock",
        "text",
    ],
)
def test_inexact_lineage_or_evidence_fails(fault):
    parent, rows, evidence, mapping = inputs()
    if fault == "history":
        rows[0]["asking_rent"] = 5000
    if fault == "historical_capture":
        mapping["old"][0]["capture_id"] = "1"
    if fault == "missing_current":
        evidence = []
    if fault == "duplicate_current":
        evidence *= 2
    if fault == "identity":
        evidence[0]["unit_id"] = "different"
    if fault == "raw_hash":
        evidence[0]["raw_listing_sha256"] = "different"
    if fault == "body_hash":
        evidence[0]["body_sha256"] = "different"
    if fault == "clock":
        evidence[0]["known_at"] = "2026-09-19T12:00:00Z"
    if fault == "text":
        evidence[0]["description"] = {"inferred": "text"}
    with pytest.raises(ValueError):
        assemble(parent, rows, evidence, mapping)
