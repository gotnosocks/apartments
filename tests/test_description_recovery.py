import gzip
import hashlib
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from apartments.description_recovery import build_description_recovery, recover_capture
from apartments.granular_parse import parse_listing
from apartments.research_pipeline import read_bundle


def sample(tmp_path, snapshot=1, description="North-facing café windows.", **extra):
    listing = {
        "id": snapshot,
        "description": "$b",
        "propertyDetails": {"address": {"displayUnit": "#4A"}, "bedroomCount": 1},
        "propertyHistory": [
            {
                "listingId": snapshot,
                "rentalEventsOfInterest": [
                    {"date": "2025-01-01", "price": 3000, "status": "ACTIVE"}
                ],
            }
        ],
        **extra,
    }
    stream = (
        "a:"
        + json.dumps(listing)
        + "\nb:T"
        + format(len(description.encode()), "x")
        + ","
        + description
    )
    body = (
        '<link rel="canonical" href="/building/demo/4a"><script>self.__next_f.push('
        + json.dumps([1, stream])
        + ")</script>"
    ).encode()
    body_hash = hashlib.sha256(body).hexdigest()
    body_root = tmp_path / "bodies"
    directory = body_root / body_hash[:2]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (body_hash + ".gz")).write_bytes(gzip.compress(body))
    url = f"https://streeteasy.com/rental/{snapshot}"
    row, _ = parse_listing(body, url)
    old = json.loads(row["raw_listing_json"])
    old["description"] = "$b"
    row.update(
        raw_listing_json=json.dumps(old, sort_keys=True, separators=(",", ":")),
        snapshot_id=snapshot,
        body_hash=body_hash,
        snapshot_url=url,
        snapshot_observed_at=100.0,
        collected_at=100.0,
        parsed_at=200.0,
    )
    return row, body_root


def source_dataset(tmp_path, count=2, description="North-facing café windows."):
    dataset = tmp_path / "source"
    captures = [
        sample(tmp_path, i, description=description)[0] for i in range(1, count + 1)
    ]
    (dataset / "listing_observations").mkdir(parents=True)
    (dataset / "snapshots").mkdir()
    (dataset / "complete.json").write_text(
        json.dumps({"unit_association_rule": "canonical-url-v1"})
    )
    listings = [
        {
            k: v
            for k, v in c.items()
            if k not in ("body_hash", "snapshot_url", "snapshot_observed_at")
        }
        for c in captures
    ]
    snapshots = [
        {
            "snapshot_id": c["snapshot_id"],
            "body_hash": c["body_hash"],
            "url": c["url"],
            "observed_at": c["collected_at"],
        }
        for c in captures
    ]
    pq.write_table(
        pa.Table.from_pylist(listings),
        dataset / "listing_observations" / "part.parquet",
    )
    pq.write_table(
        pa.Table.from_pylist(snapshots), dataset / "snapshots" / "part.parquet"
    )
    return dataset, tmp_path / "bodies"


def test_recovery_binds_exact_capture_and_raw_payload(tmp_path):
    row, bodies = sample(tmp_path)
    result = recover_capture(row, bodies)
    assert result["status"] == "accepted"
    assert (
        result["original_raw_listing_sha256"]
        == hashlib.sha256(row["raw_listing_json"].encode()).hexdigest()
    )
    assert result["source_body_sha256"] == row["body_hash"]
    assert result["resolved_description"] == "North-facing café windows."
    assert (
        result["description_sha256"]
        == hashlib.sha256(result["resolved_description"].encode()).hexdigest()
    )
    assert result["interpreted_at"].endswith("+00:00")
    assert json.loads(row["raw_listing_json"])["description"] == "$b"


def test_capture_hash_identity_and_other_payload_changes_quarantined(tmp_path):
    row, bodies = sample(tmp_path)
    changed = dict(row, unit_label="#5A")
    assert recover_capture(changed, bodies)["reason"] == "source_identity_changed"
    changed = dict(row, listing_id="2")
    assert recover_capture(changed, bodies)["reason"] == "listing_identity_mismatch"
    old = json.loads(row["raw_listing_json"])
    old["propertyDetails"]["bedroomCount"] = 2
    changed = dict(row, raw_listing_json=json.dumps(old))
    assert (
        recover_capture(changed, bodies)["reason"] == "non_description_payload_changed"
    )
    path = bodies / row["body_hash"][:2] / (row["body_hash"] + ".gz")
    path.write_bytes(gzip.compress(b"different immutable body"))
    assert recover_capture(row, bodies)["reason"] == "body_hash_mismatch"
    path.unlink()
    assert recover_capture(row, bodies)["reason"] == "missing_archive_body"


def test_unresolved_invalid_or_oversize_body_quarantined(tmp_path):
    row, bodies = sample(tmp_path, description="$f")
    assert recover_capture(row, bodies)["reason"] == "description_not_recovered"
    row, bodies = sample(tmp_path, snapshot=2, description="x" * 2000)
    result = recover_capture(row, bodies, max_body_bytes=1024)
    assert (
        result["reason"] == "body_read_failure"
        and result["detail"] == "body_decompression_limit"
    )
    assert (
        recover_capture(dict(row, snapshot_url="https://example.com"), bodies)["reason"]
        == "snapshot_url_mismatch"
    )


def test_completed_bundle_reuses_stable_hashes_and_catches_source_change(tmp_path):
    dataset, bodies = source_dataset(tmp_path)
    out = tmp_path / "recovered"
    manifest = build_description_recovery(dataset, bodies, out, workers=1, batch_size=1)
    assert manifest == read_bundle(out)
    assert manifest["coverage"] == {
        "candidates": 2,
        "accepted": 2,
        "quarantined": 0,
        "quarantine_reasons": {},
        "batches": 2,
    }
    assert (
        build_description_recovery(dataset, bodies, out, workers=1, batch_size=1)
        == manifest
    )
    (dataset / "complete.json").write_text(
        json.dumps({"unit_association_rule": "canonical-url-v1", "changed": True})
    )
    with pytest.raises(ValueError, match="inputs or implementation changed"):
        build_description_recovery(dataset, bodies, out, workers=1, batch_size=1)


def test_interruption_resume_keeps_committed_interpretation_time(tmp_path):
    dataset, bodies = source_dataset(tmp_path)
    out = tmp_path / "recovered"

    def stop(progress):
        raise RuntimeError("interrupted after checkpoint")

    with pytest.raises(RuntimeError, match="interrupted"):
        build_description_recovery(
            dataset, bodies, out, workers=1, batch_size=1, progress=stop
        )
    assert not (out / "complete.json").exists()
    first = (out / "parts" / "000000.jsonl").read_bytes()
    manifest = build_description_recovery(dataset, bodies, out, workers=1, batch_size=1)
    assert manifest["coverage"]["accepted"] == 2
    assert (out / "parts" / "000000.jsonl").read_bytes() == first


def test_corrupt_checkpoint_fails_instead_of_silent_recompute(tmp_path):
    dataset, bodies = source_dataset(tmp_path)
    out = tmp_path / "recovered"

    def stop(progress):
        raise RuntimeError("stop")

    with pytest.raises(RuntimeError):
        build_description_recovery(
            dataset, bodies, out, workers=1, batch_size=1, progress=stop
        )
    (out / "parts" / "000000.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="checkpoint integrity"):
        build_description_recovery(dataset, bodies, out, workers=1, batch_size=1)


def test_tampered_complete_artifacts_fail_verification(tmp_path):
    dataset, bodies = source_dataset(tmp_path, count=1)
    out = tmp_path / "recovered"
    build_description_recovery(dataset, bodies, out, workers=1)
    (out / "accepted.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="integrity"):
        build_description_recovery(dataset, bodies, out, workers=1)


def test_bounded_workers_and_separate_source_output(tmp_path):
    dataset, bodies = source_dataset(tmp_path, count=1)
    with pytest.raises(ValueError, match="bounded"):
        build_description_recovery(dataset, bodies, tmp_path / "out", workers=99)
    with pytest.raises(ValueError, match="separate"):
        build_description_recovery(dataset, bodies, dataset / "recovered", workers=1)


def test_parallel_execution_keeps_source_order(tmp_path):
    dataset, bodies = source_dataset(tmp_path, count=3)
    out = tmp_path / "recovered"
    build_description_recovery(dataset, bodies, out, workers=2, batch_size=2)
    with (out / "accepted.jsonl").open(encoding="utf-8", newline="\n") as stream:
        assert [json.loads(s)["snapshot_id"] for s in stream] == [1, 2, 3]


def test_interrupted_resume_preserves_literal_unicode_line_separators(tmp_path):
    description = "North-facing\u2028windows. Courtyard\u2029views. Pets\u0085welcome."
    dataset, bodies = source_dataset(tmp_path, description=description)
    out = tmp_path / "recovered"

    def stop(progress):
        raise RuntimeError("interrupted after first committed batch")

    with pytest.raises(RuntimeError, match="interrupted"):
        build_description_recovery(
            dataset, bodies, out, workers=1, batch_size=1, progress=stop
        )
    checkpoint = out / "parts" / "000000.jsonl"
    committed = checkpoint.read_bytes()
    assert (
        b"\xe2\x80\xa8" in committed
        and b"\xe2\x80\xa9" in committed
        and b"\xc2\x85" in committed
    )
    assert committed.count(b"\n") == 1
    manifest = build_description_recovery(dataset, bodies, out, workers=1, batch_size=1)
    assert manifest["coverage"]["accepted"] == 2
    assert checkpoint.read_bytes() == committed
    with (out / "accepted.jsonl").open(encoding="utf-8", newline="\n") as stream:
        records = [json.loads(line) for line in stream]
    assert [r["resolved_description"] for r in records] == [description, description]
    assert records[0]["interpreted_at"] == json.loads(committed)["interpreted_at"]
