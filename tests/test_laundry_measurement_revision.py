from copy import deepcopy
import hashlib

import pytest

from apartments import laundry_measurement
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models.laundry_measurement_revision import (
    compare_capture,
    identity,
    replay_payload,
    run,
    support,
)


def case():
    text = "Laundry on every floor."
    payload = {
        "description": text,
        "propertyDetails": {
            "features": [None, "DISHWASHER", "WASHER_DRYER"],
            "amenities": {"list": ["ELEVATOR", "LAUNDRY"]},
        },
    }
    evidence = dict(
        audit_id="a",
        capture_id=2,
        source_listing_id="3",
        unit_id="u",
        body_sha256="body",
        raw_listing_sha256="raw",
        description_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_collected_at="2026-01-01T00:00:00Z",
        known_at="2026-01-01T00:00:00Z",
        description_interpreted_at=None,
        source_path="/description",
        description=text,
    )
    before = {
        **laundry_measurement.extract(payload),
        "version": "scoped-laundry-measurement-v3",
    }
    capture = {
        **{k: v for k, v in evidence.items() if k != "description"},
        "building": "b",
        "laundry_type": "in_building",
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
        "measurement": before,
    }
    return payload, capture, evidence


def legacy_on_unchanged_case(raw):
    return {
        **laundry_measurement.extract(raw),
        "version": "scoped-laundry-measurement-v3",
    }


def test_minimal_input_preserves_structured_indices_clocks_and_literal_spans():
    payload, capture, evidence = case()
    saved = deepcopy((capture, evidence))
    reconstructed = replay_payload(capture, evidence)
    assert reconstructed["propertyDetails"] == {
        "features": [None, None, "WASHER_DRYER"],
        "amenities": {"list": [None, "LAUNDRY"]},
    }
    before, after, text = compare_capture(capture, evidence, legacy_on_unchanged_case)
    assert before == legacy_on_unchanged_case(payload)
    assert {**after, "version": before["version"]} == before
    assert text == evidence["description"]
    assert (capture, evidence) == saved


@pytest.mark.parametrize(
    "fault",
    [
        "text",
        "ad",
        "typed_capture",
        "clock",
        "path",
        "span",
        "code_path",
        "duplicate_code",
    ],
)
def test_identity_literal_clock_and_exact_baseline_failures_are_refused(fault):
    _, capture, evidence = case()
    if fault == "text":
        evidence["description"] += "changed"
    elif fault == "ad":
        evidence["source_listing_id"] = "4"
    elif fault == "typed_capture":
        evidence["capture_id"] = "2"
    elif fault == "clock":
        evidence["known_at"] = "2026-01-02T00:00:00Z"
    elif fault == "path":
        evidence["source_path"] = "/other"
    elif fault == "span":
        capture["measurement"]["claims"][-1]["start"] += 1
    elif fault == "code_path":
        capture["measurement"]["claims"][0]["source_path"] = "/unexpected"
    elif fault == "duplicate_code":
        capture["measurement"]["claims"].append(capture["measurement"]["claims"][0])
    with pytest.raises(ValueError):
        compare_capture(capture, evidence, legacy_on_unchanged_case)


def test_missing_prose_is_not_inferred_absence_and_typed_ids_stay_distinct():
    _, capture, evidence = case()
    evidence.update(description=None, description_sha256=None)
    capture["description_sha256"] = None
    capture["measurement"] = legacy_on_unchanged_case({"description": None})
    _, after, _ = compare_capture(capture, evidence, legacy_on_unchanged_case)
    assert after["most_convenient_reported_option"] is None
    assert identity({"audit_id": "a", "capture_id": 2}) != identity(
        {"audit_id": "a", "capture_id": "2"}
    )
    with pytest.raises(ValueError):
        identity({"audit_id": "a", "capture_id": True})


def test_disk_index_full_replay_is_idempotent_and_refuses_unmatched_archive(tmp_path):
    _, capture, evidence = case()
    # This tiny frozen reference deliberately covers an unchanged legacy phrase.
    frozen = (
        "from apartments.laundry_measurement import extract as current\n"
        'VERSION = "scoped-laundry-measurement-v3"\n'
        'def extract(raw): return {**current(raw), "version": VERSION}\n'
    )
    baseline, descriptions, output = [
        tmp_path / n for n in ("baseline", "descriptions", "output")
    ]
    publish_bundle(
        descriptions, {"evidence.jsonl": canonical(evidence) + "\n"}, {"captures": 1}
    )
    counts = support([{**capture, "before": "in_unit"}], "before")
    publish_bundle(
        baseline,
        {
            "captures.jsonl": canonical(capture) + "\n",
            "laundry_measurement.py": frozen,
            "summary.json": canonical(
                {"captures": 1, "observations": 1, "candidate_support": counts}
            )
            + "\n",
        },
        {
            "version": "full-cohort-scoped-laundry-measurement-v1",
            "descriptions_manifest_sha256": digest(descriptions / "complete.json"),
            "dataset_manifest_sha256": "source",
        },
    )
    result = run(baseline, descriptions, output)
    assert result["captures_replayed_exactly"] == 1
    assert result["changed_measurement_captures"] == 0
    saved = (output / "complete.json").read_bytes()
    assert run(baseline, descriptions, output) == result
    assert (output / "complete.json").read_bytes() == saved
    (descriptions / "evidence.jsonl").write_text(
        canonical({**evidence, "capture_id": 99}) + "\n"
    )
    with pytest.raises(ValueError):
        run(baseline, descriptions, tmp_path / "bad")
    assert not (tmp_path / "bad/complete.json").exists()
