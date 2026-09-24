"""Paid requests are bounded; fresh source evidence never inherits old status."""

import asyncio
import json
import shutil

import pytest
from scrapy.http import HtmlResponse

from apartments import candidate_refresh as refresh, corrections
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from apartments.unit_canonical import canonical_unit_id


def source(tmp_path, count=2, overlay=None):
    rows = []
    for index in range(count):
        url = f"https://streeteasy.com/building/demo/{index}d"
        rows.append(
            dict(
                unit_id=canonical_unit_id(url),
                building_id="demo",
                canonical_unit_url=url,
                source="streeteasy",
                source_listing_id=str(100 + index),
                capture_id=str(index),
                collected_at="2026-09-17T10:00:00Z",
                known_at="2026-09-17T11:00:00Z",
                listing_status="ACTIVE",
                rent=3500,
                price_basis="gross_advertised_rent",
                bedrooms=0,
                bathrooms=1,
            )
        )
    root = tmp_path / "source"
    publish_bundle(
        root,
        {"candidates.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {
            "snapshot_version": "canonical-candidate-captures-v1",
            "as_of": "2026-09-18T16:00:00Z",
            "overlay": overlay,
        },
    )
    return root, rows


def html(row, *, status="ACTIVE", rent=3700, canonical_url=None):
    listing = {
        "id": int(row["source_listing_id"]),
        "status": status,
        "pricing": {"price": rent},
        "description": "Studio apartment with a washer/dryer in unit.",
        "propertyDetails": {
            "address": {"displayUnit": row["canonical_unit_url"].split("/")[-1]},
            "bedroomCount": 0,
            "fullBathroomCount": 1,
        },
    }
    # Current price/status are usable even when the historical event panel is absent.
    return (
        '<html><head><link rel="canonical" href="'
        + (canonical_url or row["canonical_unit_url"])
        + '"></head><body><script type="application/json">'
        + json.dumps({"listing": listing})
        + "</script></body></html>"
    ).encode()


def run(*args, **kwargs):
    return asyncio.run(refresh.refresh(*args, **kwargs))


def test_bounded_refresh_resume_replay_and_changed_status(tmp_path):
    src, rows = source(tmp_path)
    output = tmp_path / "refresh"
    calls = []

    async def fetch(request):
        calls.append(request.url)
        row = next(r for r in rows if request.url.endswith(r["source_listing_id"]))
        request.meta["archive_provider"] = {
            "submission_attempts": 1,
            "password": "fixture-secret",
            "results": [
                {
                    "content": "must-not-duplicate-body",
                    "status_code": 200,
                    "job_id": "fixture-job",
                }
            ],
        }
        return HtmlResponse(
            request.url,
            request=request,
            body=html(row, status="RENTED" if len(calls) == 2 else "ACTIVE"),
        )

    paused = run(src, output, fetch=fetch, max_new_requests=1)
    assert paused["status"] == "paused_at_declared_limit" and len(calls) == 1
    finished = run(src, output, fetch=fetch)
    assert finished["report"]["listing_status_counts"] == {"ACTIVE": 1, "RENTED": 1}
    assert len(calls) == 2 and finished["report"]["failed"] == 0
    before = (output / "snapshot" / "candidates.jsonl").read_bytes()
    assert run(src, output, fetch=fetch) == finished and len(calls) == 2
    assert (output / "snapshot" / "candidates.jsonl").read_bytes() == before
    fresh = [json.loads(s) for s in before.splitlines()]
    assert all(
        r["rent"] == 3700 and r["capture_id"].startswith("refresh:") for r in fresh
    )
    assert all(
        r["refresh_provenance"]["history_warning"]
        == "propertyHistory missing or unresolved"
        for r in fresh
    )
    assert all(r["collected_at"] != rows[0]["collected_at"] for r in fresh)
    # Rebuild interpretation after losing only the derived checkpoint: reuse raw
    # evidence, never fetch the paid advertisement again.
    shutil.rmtree(output / "results" / "0000")
    shutil.rmtree(output / "snapshot")
    rebuilt = run(src, output, fetch=fetch)
    assert rebuilt["report"]["parsed"] == 2 and len(calls) == 2
    archive = refresh.ArchiveStore(output / "archive")
    try:
        metadata = [
            r[0]
            for r in archive.db.execute("SELECT capture_metadata FROM observations")
        ]
        assert len(metadata) == 2
        assert all(
            "fixture-secret" not in m and "must-not-duplicate-body" not in m
            for m in metadata
        )
        assert all("fixture-job" in m for m in metadata)
    finally:
        archive.close()
    with pytest.raises(ValueError, match="no silent truncation"):
        refresh.prepare(src, tmp_path / "too-small", max_targets=1)


@pytest.mark.parametrize("failure", ["http", "identity"])
def test_failed_refresh_never_falls_back(tmp_path, failure):
    src, rows = source(tmp_path, count=1)

    async def fetch(request):
        return HtmlResponse(
            request.url,
            request=request,
            status=404 if failure == "http" else 200,
            body=html(
                rows[0], canonical_url="https://streeteasy.com/building/demo/wrong"
            ),
        )

    output = tmp_path / "refresh"
    result = run(src, output, fetch=fetch)
    assert result["report"]["parsed"] == 0 and result["report"]["failed"] == 1
    assert (output / "snapshot" / "candidates.jsonl").read_text() == ""


def test_interrupted_unknown_submission_does_not_repeat(tmp_path):
    src, _ = source(tmp_path, count=1)
    output = tmp_path / "refresh"
    plan, ph = refresh.prepare(src, output)
    publish_bundle(
        output / "requests" / "0000",
        {"intent.json": "{}\n"},
        {
            "version": refresh.VERSION,
            "plan_sha256": ph,
            "target_sha256": refresh._hash(plan["targets"][0]),
            "index": 0,
        },
    )

    async def unexpected(request):
        raise AssertionError("An uncertain submission must not be repeated")

    result = run(src, output, fetch=unexpected)
    assert result["report"]["failure_reasons"] == {
        "interrupted_request_outcome_unknown": 1
    }


def test_blocked_response_pause_survives_restart_and_checkpoint_gap(tmp_path):
    src, _ = source(tmp_path)
    output = tmp_path / "refresh"
    calls = []

    async def fetch(request):
        calls.append(request.url)
        return HtmlResponse(
            request.url, request=request, status=429, body=b"Rate limited"
        )

    first = run(src, output, fetch=fetch)
    assert first["status"] == "paused_after_blocked_response" and len(calls) == 1
    assert run(src, output, fetch=fetch) == first and len(calls) == 1
    # Simulate interruption after result publication but before pause publication.
    shutil.rmtree(output / "pause")
    assert run(src, output, fetch=fetch) == first and len(calls) == 1


def test_frozen_correction_ledger_applies_to_new_capture(tmp_path, monkeypatch):
    ledger = tmp_path / "corrections.jsonl"
    monkeypatch.setattr(
        corrections, "now", lambda: corrections.instant("2026-09-18T12:00:00Z")
    )
    corrections.append(
        ledger,
        author="reviewer",
        reason="confirmed layout",
        edit={
            "target": {"source": "streeteasy", "source_listing_id": "100"},
            "validity": {"from": "2026-09-18"},
            "patch": [{"op": "replace", "path": "/attributes/bedrooms", "value": 1}],
        },
    )
    overlay = corrections.Overlay(ledger, as_of="2026-09-18T16:00:00Z")
    src, rows = source(tmp_path, count=1, overlay=overlay.manifest)

    async def fetch(request):
        return HtmlResponse(request.url, request=request, body=html(rows[0]))

    with pytest.raises(ValueError, match="same correction ledger"):
        refresh.prepare(src, tmp_path / "missing-ledger")
    output = tmp_path / "refresh"
    run(src, output, fetch=fetch, ledger=ledger)
    row = json.loads((output / "snapshot" / "candidates.jsonl").read_text())
    assert (
        row["bedrooms"] == 1 and row["corrections"][0]["reason"] == "confirmed layout"
    )
