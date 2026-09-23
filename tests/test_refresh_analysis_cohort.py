import asyncio
from copy import deepcopy

import pytest
from scrapy.http import HtmlResponse

from apartments import discovery_detail_refresh
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import refresh_analysis_cohort as m
from tests.test_candidate_refresh import html
from tests.test_discovery_detail_refresh import fixture


def candidate(**changes):
    return {
        "unit_id": "u1",
        "building_id": "demo",
        "source": "streeteasy",
        "source_listing_id": "100",
        "capture_id": "capture1",
        "canonical_unit_url": "https://streeteasy.com/building/demo/1d",
        "collected_at": "2026-09-18T10:00:00Z",
        "known_at": "2026-09-18T10:01:00Z",
        "listing_status": "ACTIVE",
        "price_basis": "gross_advertised_rent",
        "rent": 4000,
        "bedrooms": 1,
        "bathrooms": 1,
        **changes,
    }


def failure(**changes):
    return {
        "source_listing_id": "100",
        "collected_at": "2026-09-18T11:00:00Z",
        "interpreted_at": "2026-09-18T11:01:00Z",
        "reason": "canonical_unit_mismatch",
        **changes,
    }


def test_failure_blocks_old_advertisement_but_is_not_inactivity():
    old = candidate()
    f = failure()
    retained, excluded = m.combine_records([old], [f], as_of="2026-09-18T12:00:00Z")
    assert not retained and excluded[0]["reason"] == "later_refresh_failed_no_fallback"
    assert old["listing_status"] == "ACTIVE" and excluded[0]["failures"] == [f]


def test_failure_knowledge_clock_and_later_success():
    old = candidate()
    f = failure()
    assert m.combine_records([old], [f], as_of="2026-09-18T11:00:30Z") == ([old], [])
    newer = candidate(
        collected_at="2026-09-18T12:00:00Z", known_at="2026-09-18T12:01:00Z"
    )
    assert m.combine_records([newer], [f], as_of="2026-09-18T13:00:00Z") == (
        [newer],
        [],
    )


def test_identity_drift_is_not_two_separate_units_or_silent_merge():
    old = candidate()
    changed = candidate(
        unit_id="u2", canonical_unit_url="https://streeteasy.com/building/demo/2d"
    )
    kept, excluded = m.combine_records([old, changed], [], as_of="2026-09-18T12:00:00Z")
    assert not kept and len(excluded) == 2
    assert {r["reason"] for r in excluded} == {"advertisement_identity_changed"}


def historical(**changes):
    return {
        "audit_id": "historical1",
        "unit_id": "u1",
        "building": "demo",
        "source_listing_id": "old",
        "known_at": "2026-09-17T00:00:00Z",
        "period": "2020-01-01",
        "analysis_price_basis": "historical_initial_own_advertisement_ask",
        "bedrooms": 0,
        "bathrooms": 1,
        "asking_rent": 2500,
        "research_review_history": [{"decision_id": "keep-this-source-review"}],
        **changes,
    }


def evidence(row, root):
    return {
        "capture_id": row["capture_id"],
        "bathroom_fields": {
            "fullBathroomCount": {"present": True, "value": 1},
            "halfBathroomCount": {"present": True, "value": 0},
        },
    }


def test_preserves_reviewed_history_and_missing_search_ad(monkeypatch):
    monkeypatch.setattr(m, "capture_evidence", evidence)
    old = candidate()
    new = candidate(
        source_listing_id="101",
        unit_id="u2",
        capture_id="capture2",
        canonical_unit_url="https://streeteasy.com/building/demo/2d",
        bedrooms=2,
    )
    parent = historical()
    before = deepcopy(parent)
    rows, _, _, summary = m.assemble(
        [parent],
        [old, new],
        [],
        {"capture1": None, "capture2": None},
        as_of="2026-09-18T12:00:00Z",
        max_age_days=7,
    )
    assert rows[0] == before and parent == before
    assert summary["current_rows"] == 2
    assert {r["source_listing_id"] for r in rows[1:]} == {"100", "101"}
    assert rows[1]["bedrooms"] == 1  # not backfilled into historical studio


def test_latest_inactive_capture_removes_old_success(monkeypatch):
    monkeypatch.setattr(m, "capture_evidence", evidence)
    old = candidate()
    inactive = candidate(
        capture_id="inactive",
        listing_status="RENTED",
        collected_at="2026-09-18T11:00:00Z",
        known_at="2026-09-18T11:01:00Z",
    )
    another = candidate(source_listing_id="101", unit_id="u2", capture_id="c2")
    rows, _, _, summary = m.assemble(
        [historical()],
        [old, inactive, another],
        [],
        {"c2": None},
        as_of="2026-09-18T12:00:00Z",
        max_age_days=7,
    )
    assert summary["current_rows"] == 1 and rows[-1]["source_listing_id"] == "101"
    assert summary["exclusions"]["latest_capture_not_confirmed_active"] == 1


def test_same_month_and_knowledge_contract(monkeypatch):
    monkeypatch.setattr(m, "capture_evidence", evidence)
    kwargs = dict(
        candidates=[candidate()],
        failures=[],
        sources={"capture1": None},
        as_of="2026-09-18T12:00:00Z",
        max_age_days=7,
    )
    with pytest.raises(ValueError, match="later than cutoff"):
        m.assemble([historical(known_at="2026-09-19T00:00:00Z")], **kwargs)
    with pytest.raises(ValueError, match="same-month"):
        m.assemble([historical(period="2026-09-01")], **kwargs)


def test_saved_collection_transform_replay_and_body_integrity(tmp_path):
    review, report, _, _ = fixture(tmp_path)

    async def fetch(request):
        identifier = request.url.rsplit("/", 1)[1]
        row = {
            "source_listing_id": identifier,
            "canonical_unit_url": "https://streeteasy.com/building/demo/"
            + ("1d" if identifier == "100" else "2d"),
        }
        return HtmlResponse(request.url, request=request, body=html(row))

    collection = tmp_path / "collection"
    result = asyncio.run(
        discovery_detail_refresh.collect(review, report, collection, fetch=fetch)
    )
    cutoff = result["report"]["latest_known_at"]
    parent = tmp_path / "parent"
    publish_bundle(
        parent,
        {"observations.jsonl": canonical(historical()) + "\n"},
        {"version": m.PARENT_VERSION},
    )
    output = tmp_path / "output"
    kwargs = dict(parent=parent, collections=[collection], output=output, as_of=cutoff)
    first = m.run(**kwargs)
    assert first["summary"]["current_rows"] == 2
    assert m.run(**kwargs) == first
    candidates, _, _, _ = m.load_collection(collection)
    sha = candidates[0]["refresh_provenance"]["body_sha256"]
    import gzip

    (collection / "archive/bodies" / sha[:2] / (sha + ".gz")).write_bytes(
        gzip.compress(b"changed")
    )
    with pytest.raises(ValueError, match="source body changed"):
        m.run(**kwargs)


def test_existing_current_review_cannot_be_lost(monkeypatch):
    monkeypatch.setattr(m, "capture_evidence", evidence)
    args = dict(
        candidates=[candidate()],
        failures=[],
        sources={"capture1": None},
        as_of="2026-09-18T12:00:00Z",
        max_age_days=7,
    )
    rows, _, _, _ = m.assemble([historical()], **args)
    rows[-1]["bathroom_count_evidence"]["flags"].append("reviewed_composition_conflict")
    with pytest.raises(ValueError, match="explicit reapplication"):
        m.assemble(rows, **args)
