"""Search prices/statuses belong to the capture, never an initial price event."""

import hashlib
import json

import duckdb
import pytest

from apartments import candidate_snapshot as snapshot, corrections
from apartments.research_pipeline import digest, publish_bundle
from apartments.corrections import canonical


def capture():
    return dict(
        snapshot_id=1,
        listing_id="ad",
        listing_type="rental",
        building_slug="b",
        unit_label="1D",
        canonical_unit_url="https://streeteasy.com/building/b/1d",
        bedrooms=0,
        bathrooms=1,
        square_feet=400,
        collected_at="2026-09-17T10:00:00Z",
        parsed_at="2026-09-17T11:00:00Z",
        features_json="[]",
        amenities_json="[]",
        raw_listing_json=json.dumps(
            {
                "id": "ad",
                "status": "ACTIVE",
                "pricing": {"price": 3500},
                "description": "A studio apartment.",
                "propertyHistory": [{"price": 900, "date": "2010-01-01"}],
            }
        ),
    )


def member():
    return dict(
        listing_id="ad",
        unit_id="canonical-u",
        canonical_unit_url="https://streeteasy.com/building/b/1d",
        status="associated",
        rule="canonical-url-v1",
    )


def test_capture_price_status_clocks_and_effective_correction(tmp_path, monkeypatch):
    cap = capture()
    identity = "2026-09-17T20:00:00Z"
    row, reason = snapshot.project_capture(
        cap, [member()], as_of="2026-09-18", identity_known_at=identity
    )
    assert reason is None and row["rent"] == 3500 and row["listing_status"] == "ACTIVE"
    assert (
        row["known_at"] == identity
        and row["collected_at"] == "2026-09-17T10:00:00+00:00"
    )
    assert row["price_path"] == "/archive_listing/pricing/price"
    assert (
        row["source_raw_sha256"]
        == hashlib.sha256(cap["raw_listing_json"].encode()).hexdigest()
    )
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(
        corrections, "now", lambda: corrections.instant("2026-09-18T01:00:00Z")
    )
    corrections.append(
        ledger,
        author="reviewer",
        reason="studio mislabeled at this capture",
        edit={
            "target": {"source": "streeteasy", "source_listing_id": "ad"},
            "validity": {"from": "2026-09-16", "until": "2026-09-18"},
            "patch": [{"op": "replace", "path": "/attributes/bedrooms", "value": 1}],
        },
    )
    row, _ = snapshot.project_capture(
        cap,
        [member()],
        as_of="2026-09-18T02:00:00Z",
        identity_known_at=identity,
        overlay=corrections.Overlay(ledger, as_of="2026-09-18T02:00:00Z"),
    )
    assert row["bedrooms"] == 1 and row["known_at"] == "2026-09-18T01:00:00+00:00"
    assert cap["bedrooms"] == 0 and row["corrections"][0]["changes"]
    unavailable, reason = snapshot.project_capture(
        cap, [member()], as_of="2026-09-17T19:00:00Z", identity_known_at=identity
    )
    assert unavailable is None and reason == "not_known_at_cutoff"
    bad = {**cap, "canonical_unit_url": "https://streeteasy.com/building/b/2d"}
    assert (
        snapshot.project_capture(
            bad, [member()], as_of="2026-09-18", identity_known_at=identity
        )[1]
        == "conflicting_canonical_url"
    )


def test_snapshot_real_parquet_preserves_inactive_and_detects_changed_source(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    cap = capture()
    inactive = {
        **cap,
        "snapshot_id": 2,
        "collected_at": "2026-09-17T12:00:00Z",
        "parsed_at": "2026-09-17T13:00:00Z",
        "raw_listing_json": json.dumps(
            {"id": "ad", "status": "DELISTED", "pricing": {"price": 3500}}
        ),
    }
    for row in (cap, inactive):
        for clock in ("collected_at", "parsed_at"):
            row[clock] = corrections.instant(row[clock]).timestamp()
    files = {}
    counts = {}
    with duckdb.connect() as db:
        for table, rows in [
            ("listing_observations", [cap, inactive]),
            ("rental_unit_memberships", [member()]),
        ]:
            directory = root / table
            directory.mkdir()
            source = tmp_path / (table + ".json")
            source.write_text(json.dumps(rows))
            dest = directory / "part.parquet"
            db.read_json(str(source)).write_parquet(str(dest))
            files[str(dest.relative_to(root))] = digest(dest)
            counts[table] = len(rows)
    complete = root / "complete.json"
    complete.write_text(
        json.dumps(
            {
                "unit_association_rule": "canonical-url-v1",
                "finished_at": corrections.instant("2026-09-17T20:00:00Z").timestamp(),
                "counts": counts,
            }
        )
    )
    files["complete.json"] = digest(complete)
    reference = tmp_path / "reference"
    publish_bundle(
        reference,
        {"source-files.json": canonical(files) + "\n"},
        {
            "dataset_version": "historical-own-advertisement-v1",
            "source_manifest_sha256": hashlib.sha256(
                canonical(files).encode()
            ).hexdigest(),
        },
    )
    output = tmp_path / "snapshot"
    kwargs = {"as_of": "2026-09-18"}
    result = snapshot.build_snapshot(root, reference, output, **kwargs)
    assert snapshot.build_snapshot(root, reference, output, **kwargs) == result
    rows = [
        json.loads(s)
        for s in (output / "candidates.jsonl").read_text().split("\n")
        if s
    ]
    assert [r["listing_status"] for r in rows] == ["ACTIVE", "DELISTED"]
    assert all(r["unit_id"] == "canonical-u" for r in rows)
    complete.write_text("{}")
    with pytest.raises(ValueError, match="source changed"):
        snapshot.build_snapshot(root, reference, tmp_path / "bad", **kwargs)
