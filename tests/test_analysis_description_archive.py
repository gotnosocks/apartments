"""Complete, source-bound description export is independent of feature matches."""

import gzip
import hashlib
import json

import duckdb
import pandas as pd
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models.analysis_description_archive import run


@pytest.fixture
def archive_case(tmp_path, monkeypatch):
    def make(problem=None):
        archive = tmp_path / "archive"
        raw = [
            canonical({"description": "A quiet apartment.\u2028No outdoor wording."}),
            canonical({"description": "$L123"}),
            canonical({"description": "$L456"}),
        ]
        source_files = {}
        listing_rows = [
            {
                "snapshot_id": i,
                "listing_id": str(100 + i),
                "canonical_unit_url": f"unit:{i}",
                "raw_listing_json": text,
                "collected_at": 1789743600.0,
            }
            for i, text in enumerate(raw, 1)
        ]
        if problem == "historical_identity":
            listing_rows[0]["canonical_unit_url"] = "wrong:unit"
        if problem == "capture_clock":
            listing_rows[0]["collected_at"] += 7200
        for name, frame in {
            "listing_observations": pd.DataFrame(listing_rows),
            "snapshots": pd.DataFrame(
                [{"snapshot_id": i, "body_hash": f"body:{i}"} for i in range(1, 4)]
            ),
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
        recovered = {
            "snapshot_id": 3,
            "listing_id": "103",
            "canonical_unit_url": "unit:3",
            "source_body_sha256": "body:3",
            "original_raw_listing_sha256": hashlib.sha256(raw[2].encode()).hexdigest(),
            "resolved_description": "Recovered plain description.",
            "interpreted_at": "2026-09-18T15:30:00Z",
        }
        if problem == "recovery_clock":
            recovered["interpreted_at"] = "2026-09-18T17:00:00Z"
        if problem == "recovery_hash":
            recovered["original_raw_listing_sha256"] = "changed"
        recovery = tmp_path / "recovery"
        publish_bundle(
            recovery,
            {"accepted.jsonl": canonical(recovered) + "\n"},
            {"version": "fixture"},
        )
        refresh = tmp_path / "refresh"
        body = b"verified current body"
        sha = hashlib.sha256(body).hexdigest()
        body_path = refresh / "archive/bodies" / sha[:2] / (sha + ".gz")
        body_path.parent.mkdir(parents=True)
        body_path.write_bytes(
            gzip.compress(b"wrong" if problem == "body_hash" else body)
        )
        parsed = {
            "listing_id": "104",
            "canonical_unit_url": "unit:4",
            "raw_listing_json": canonical(
                {"description": "Current unit has original detail."}
            ),
        }
        if problem == "current_parse_identity":
            parsed["listing_id"] = "other"
        monkeypatch.setattr(
            "models.analysis_description_archive.granular_parse.parse_listing",
            lambda body, url: (parsed, None),
        )
        common = {
            "building_id": "building:1",
            "period": "2026-09-01",
            "known_at": "2026-09-18T16:00:00Z",
            "collected_at": "2026-09-18T15:00:00Z",
        }
        rows = [
            {
                **common,
                "audit_id": f"old:{i}",
                "source_listing_id": str(100 + i),
                "canonical_unit_url": f"unit:{i}",
                "unit_id": f"canonical:{i}",
                "capture_ids": [i],
                "analysis_price_basis": "historical_initial_own_advertisement_ask",
            }
            for i in range(1, 4)
        ]
        current = {
            **common,
            "audit_id": "fresh",
            "source_listing_id": "104",
            "canonical_unit_url": "unit:4",
            "unit_id": "canonical:4",
            "capture_id": "fresh:1",
            "analysis_price_basis": "current_capture_gross_ask",
            "refresh_provenance": {"body_sha256": sha, "requested_url": "source:104"},
        }
        candidate = {**current}
        if problem == "current_unit_identity":
            candidate["unit_id"] = "other-unit"
        fm = publish_bundle(
            refresh / "snapshot",
            {"candidates.jsonl": canonical(candidate) + "\n"},
            {"version": "fixture"},
        )
        rows.append(current)
        dataset = tmp_path / "dataset"
        publish_bundle(
            dataset,
            {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
            {"historical_manifest": hm, "current_snapshot_manifest": fm},
        )
        return dataset, archive, historical, recovery, refresh, tmp_path / "output"

    return make


def test_archive_retains_all_captures_including_unmatched_and_unknown_text_and_replays(
    archive_case,
):
    args = archive_case()
    result = run(*args)
    summary = result["summary"]
    assert summary["rows"] == summary["captures"] == 4
    assert summary["description_captures"] == 3
    assert summary["no_text_captures"] == summary["rows_without_description"] == 1
    assert summary["current_description_captures"] == 1
    rows = [
        json.loads(line)
        for line in (args[-1] / "evidence.jsonl").read_text().split("\n")
        if line
    ]
    by_id = {r["audit_id"]: r for r in rows}
    assert "\u2028" in by_id["old:1"]["description"]
    assert by_id["old:2"]["description"] is None
    assert by_id["old:2"]["description_sha256"] is None
    assert by_id["old:3"]["description_source"] == "verified_recovery"
    for row in rows:
        if row["description"] is not None:
            assert (
                row["description_sha256"]
                == hashlib.sha256(row["description"].encode()).hexdigest()
            )
    assert run(*args) == result


@pytest.mark.parametrize(
    "problem,message",
    [
        ("historical_identity", "Source capture identity"),
        ("capture_clock", "Capture later"),
        ("recovery_clock", "Recovered description identity"),
        ("recovery_hash", "Recovered description identity"),
        ("body_hash", "Current body hash"),
        ("current_parse_identity", "Current capture identity"),
        ("current_unit_identity", "Current snapshot identity"),
    ],
)
def test_invalid_source_binding_or_clocks_fail_without_publication(
    archive_case, problem, message
):
    args = archive_case(problem)
    with pytest.raises(ValueError, match=message):
        run(*args)
    assert not (args[-1] / "complete.json").exists()


def test_source_shard_tampering_fails_before_replay(archive_case):
    args = archive_case()
    run(*args)
    shard = args[1] / "listing_observations/part.parquet"
    shard.write_bytes(shard.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="Source shard hash mismatch"):
        run(*args)
