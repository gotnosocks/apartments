import json

import pytest

from apartments.corrections import canonical
from apartments.outdoor_evidence import extract
from apartments.research_pipeline import publish_bundle
from models.outdoor_scope_audit import run


def sources(tmp_path, *, mismatched=False, future=False):
    row = {
        "audit_id": "ad",
        "source_listing_id": "1",
        "unit_id": "u1",
        "capture_ids": [1],
        "asking_rent": 3000,
        "private_outdoor_category": "TERRACE",
        "shared_outdoor_category": "ROOF_DECK",
        "known_at": "2026-01-03T00:00:00Z",
    }
    details = {"features": {"privateOutdoorSpaceTypes": ["TERRACE"]}}
    text = "A terrace off the living room. Shared roof deck."
    capture = {
        "audit_id": "ad",
        "source_listing_id": "1",
        "unit_id": "other" if mismatched else "u1",
        "capture_id": 1,
        "source_collected_at": "2026-01-04T00:00:00Z"
        if future
        else "2026-01-02T00:00:00Z",
        "property_details": details,
        "description": text,
        "extraction": extract({"propertyDetails": details, "description": text}),
    }
    evidence = tmp_path / "evidence"
    em = publish_bundle(
        evidence, {"evidence.jsonl": canonical(capture) + "\n"}, {"version": "fixture"}
    )
    dataset = tmp_path / "dataset"
    publish_bundle(
        dataset,
        {"observations.jsonl": canonical(row) + "\n"},
        {
            "dataset_version": "advertised-outdoor-types-v1",
            "outdoor_audit_manifest": em,
        },
    )
    return dataset, evidence


def test_measurement_preserves_rows_and_replays_without_promoting_features(tmp_path):
    dataset, evidence = sources(tmp_path)
    output = tmp_path / "out"
    result = run(dataset, evidence, output)
    assert result["summary"]["rows"] == 1
    assert result["summary"]["rows_by_scope"] == {"shared": 1, "unit_access": 1}
    measured = json.loads((output / "measurements.jsonl").read_text())
    assert measured["asking_rent"] == 3000
    assert measured["private_outdoor_category"] == "TERRACE"
    assert measured["types_by_scope"]["private_explicit"] == []
    assert measured["types_by_scope"]["unit_access"] == ["TERRACE"]
    assert run(dataset, evidence, output) == result
    assert not (output / "observations.jsonl").exists()


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"mismatched": True}, "identity mismatch"),
        ({"future": True}, "knowledge clock"),
    ],
)
def test_scope_driver_rejects_unbound_identity_and_future_evidence(
    tmp_path, kwargs, match
):
    dataset, evidence = sources(tmp_path, **kwargs)
    with pytest.raises(ValueError, match=match):
        run(dataset, evidence, tmp_path / "out")
