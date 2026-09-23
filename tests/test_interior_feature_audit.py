import gzip
import hashlib
import json

import duckdb
import pandas as pd
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models.interior_feature_audit import checked_description, json_rows, run


def test_recovery_preserves_unicode_and_rejects_identity_source_and_future_knowledge():
    raw = canonical({"description": "$1"})
    row = {
        "source_listing_id": "123",
        "canonical_unit_url": "unit:1",
        "known_at": "2026-09-18T16:00:00Z",
    }
    recovery = {
        "original_raw_listing_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "source_body_sha256": "body",
        "listing_id": "123",
        "canonical_unit_url": "unit:1",
        "interpreted_at": "2026-09-18T15:00:00Z",
        "resolved_description": "Duplex\u2028with skylight.",
    }
    description, _ = checked_description(raw, "body", recovery, row)
    assert description == recovery["resolved_description"]
    assert (
        len(
            json_rows(
                (
                    json.dumps({"description": description}, ensure_ascii=False) + "\n"
                ).encode()
            )
        )
        == 1
    )
    for field, wrong in [
        ("listing_id", "456"),
        ("canonical_unit_url", "unit:2"),
        ("source_body_sha256", "wrong"),
        ("original_raw_listing_sha256", "wrong"),
        ("interpreted_at", "2026-09-18T17:00:00Z"),
    ]:
        with pytest.raises(ValueError, match="mismatch"):
            checked_description(raw, "body", {**recovery, field: wrong}, row)
    assert checked_description(raw, "body", None, row)[0] is None


def test_cohort_audit_binds_sources_counts_rows_and_replays(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    source_files = {}
    raw = canonical({"description": "This duplex has 18-foot ceilings and a skylight."})
    for name, frame in {
        "listing_observations": pd.DataFrame(
            [
                {
                    "snapshot_id": 1,
                    "listing_id": "123",
                    "canonical_unit_url": "unit:1",
                    "raw_listing_json": raw,
                    "collected_at": 1789743600.0,
                }
            ]
        ),
        "snapshots": pd.DataFrame([{"snapshot_id": 1, "body_hash": "historical-body"}]),
    }.items():
        path = archive / name / "part.parquet"
        path.parent.mkdir(parents=True)
        with duckdb.connect() as db:
            db.from_df(frame).write_parquet(str(path))
        source_files[str(path.relative_to(archive))] = digest(path)
    historical = tmp_path / "historical"
    hm = publish_bundle(
        historical,
        {"source-files.json": canonical(source_files)},
        {"version": "fixture"},
    )
    recovery = tmp_path / "recovery"
    publish_bundle(recovery, {"accepted.jsonl": ""}, {"version": "fixture"})
    refresh = tmp_path / "refresh"
    fm = publish_bundle(
        refresh / "snapshot", {"candidates.jsonl": ""}, {"version": "fixture"}
    )
    body = b"verified fresh body"
    sha = hashlib.sha256(body).hexdigest()
    path = refresh / "archive/bodies" / sha[:2] / (sha + ".gz")
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress(body))
    monkeypatch.setattr(
        "models.interior_feature_audit.granular_parse.parse_listing",
        lambda body, url: (
            {
                "listing_id": "456",
                "canonical_unit_url": "unit:2",
                "raw_listing_json": canonical({"description": "Floor-thru apartment."}),
            },
            None,
        ),
    )
    common = {
        "building": "building:1",
        "period": "2026-09-01",
        "known_at": "2026-09-18T16:00:00Z",
        "collected_at": "2026-09-18T15:00:00Z",
    }
    rows = [
        {
            **common,
            "audit_id": "old",
            "source_listing_id": "123",
            "canonical_unit_url": "unit:1",
            "unit_id": "unit:1",
            "capture_ids": [1],
            "analysis_price_basis": "historical_initial_own_advertisement_ask",
        },
        {
            **common,
            "audit_id": "fresh",
            "source_listing_id": "456",
            "canonical_unit_url": "unit:2",
            "unit_id": "unit:2",
            "capture_id": "fresh:1",
            "analysis_price_basis": "current_capture_gross_ask",
            "refresh_provenance": {"body_sha256": sha, "requested_url": "source:456"},
        },
    ]
    dataset = tmp_path / "dataset"
    dm = publish_bundle(
        dataset,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"historical_manifest": hm, "current_snapshot_manifest": fm},
    )
    residuals = tmp_path / "residuals"
    queue = {
        "audit_id": "old",
        "source_listing_id": "123",
        "asking_rent": 5000,
        "fitted_rent": 4000,
        "asking_vs_fitted_percent": 25,
        "selection_reasons": ["large_positive"],
        "current_capture": False,
    }
    publish_bundle(
        residuals,
        {"review-queue.jsonl": canonical(queue) + "\n"},
        {"dataset_manifest": dm},
    )
    output = tmp_path / "out"
    args = (dataset, archive, historical, recovery, refresh, residuals, output)
    result = run(*args)
    assert result["report"]["cohort_rows"] == 2
    assert result["report"]["rows_with_description"] == 2
    assert result["report"]["feature_support"]["levels"]["residual_queue_rows"] == 1
    assert result["report"]["feature_support"]["floor_through"]["current_rows"] == 1
    assert run(*args) == result
    path.write_bytes(gzip.compress(b"changed body"))
    with pytest.raises(ValueError, match="body hash mismatch"):
        run(*args)
