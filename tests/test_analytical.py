from copy import deepcopy
from datetime import UTC, datetime
import json

import pytest

from apartments import corrections
from apartments.analytical import attributes, build_dataset, project_records


def record(at="2026-01-01", beds=0, *, version="v1", recorded="2026-01-02", **attrs):
    return {
        "observation": {
            "source": "streeteasy",
            "source_listing_id": "b/1d",
            "version_id": version,
            "capture_id": version,
            "episode_id": "123",
            "building_slug": "b",
            "unit": "1D",
            "collected_at": at,
            "recorded_at": recorded,
        },
        "raw": {
            "attributes": {"bedrooms": beds, "bathrooms": 1, **attrs},
            "building_slug": "b",
            "status": "ACTIVE",
            "asking_rent": 2500,
            "price_history": [{"date": "2015-01-01", "base_rent": 1000}],
            "archive_listing": {"createdAt": "2015-01-01"},
        },
        "provenance": {"body_hash": version},
    }


def test_dated_intervals_never_backproject_price_or_attributes():
    first = record()
    second = record("2026-02-01", 1, version="v2", recorded="2026-02-02")
    result = project_records([second, first], as_of="2026-03-01")
    assert [
        (
            r["bedrooms"],
            r["valid_from"][:10],
            r["valid_until"] and r["valid_until"][:10],
        )
        for r in result["intervals"]
    ] == [(0, "2026-01-01", "2026-02-01"), (1, "2026-02-01", None)]
    assert [r["rent"] for r in result["observations"]] == [2500, 2500]
    assert all(
        "change date unverified" in r["attribute_time_basis"]
        for r in result["intervals"]
    )
    assert result == project_records(
        [first, second, deepcopy(first)], as_of="2026-03-01"
    )
    assert first == record()  # The input evidence remains immutable.


def test_knowledge_cutoff_excludes_later_reparse_and_capture():
    old = record()
    future = record("2026-02-01", 1, recorded="2026-02-02")
    reparse = record(beds=2, version="reparse", recorded="2026-02-03")
    result = project_records([old, future, reparse], as_of="2026-01-10")
    assert len(result["observations"]) == 1
    assert result["observations"][0]["bedrooms"] == 0
    assert result["intervals"][0]["valid_until"] is None
    result = project_records([old, reparse], as_of="2026-03-01")
    assert not result["observations"]
    assert result["quarantine"][0]["reason"] == "conflicting_same_time_attributes"


def test_nulls_false_and_floor_labels_are_not_inferred():
    raw = record(elevator=False, advertised_floor=14)["raw"]
    raw["home_features"] = ["DISHWASHER"]
    out = attributes(raw)
    assert out["bedrooms"] == 0
    assert out["elevator"] is False
    assert out["physical_floor"] is None
    assert out["floors_above_ground"] is None
    assert out["laundry_type"] is None
    assert (
        attributes(
            {"attributes": {}, "building_amenities": ["ELEVATOR", "DOORMAN", "LAUNDRY"]}
        )["laundry_type"]
        == "in_building"
    )
    assert (
        attributes(
            {"attributes": {"laundry_type": None}, "home_features": ["WASHER_DRYER"]}
        )["laundry_type"]
        is None
    )


def test_overlay_splits_effective_intervals_without_duplicate_price_rows(
    tmp_path, monkeypatch
):
    ledger = tmp_path / "edits.jsonl"
    monkeypatch.setattr(corrections, "now", lambda: datetime(2026, 2, 20, tzinfo=UTC))
    edit = corrections.append(
        ledger,
        author="Ben",
        reason="Renovation records",
        edit={
            "target": {"source": "streeteasy", "source_listing_id": "b/1d"},
            "validity": {"from": "2026-01-15", "until": "2026-02-15"},
            "patch": [{"op": "replace", "path": "/attributes/bedrooms", "value": 1}],
        },
    )
    overlay = corrections.Overlay(ledger, as_of="2026-03-01")
    result = project_records([record()], as_of="2026-03-01", overlay=overlay)
    assert [r["bedrooms"] for r in result["intervals"]] == [0, 1, 0]
    assert len(result["observations"]) == 1
    assert result["intervals"][1]["evidence"][0]["corrections"][0]["id"] == edit["id"]
    assert result["intervals"][1]["evidence"][0]["raw"]["attributes"]["bedrooms"] == 0
    old = corrections.Overlay(ledger, as_of="2026-02-01")
    assert (
        len(project_records([record()], as_of="2026-02-01", overlay=old)["intervals"])
        == 1
    )
    with pytest.raises(ValueError, match="knowledge"):
        project_records([record()], as_of="2026-02-01", overlay=overlay)


def test_inactive_and_missing_current_prices_remain_audited():
    old = record()
    old["raw"]["status"] = "RENTED"
    result = project_records([old], as_of="2026-03-01")
    assert len(result["intervals"]) == 1
    assert not result["observations"]
    assert result["quarantine"][0]["reason"] == "listing_not_confirmed_active"
    del old["raw"]["asking_rent"]
    old["raw"]["status"] = "ACTIVE"
    old["raw"]["archive_listing"]["pricing"] = {
        "netEffectiveRent": 2200,
        "rentedPrice": 2000,
    }
    result = project_records([old], as_of="2026-03-01")
    assert not result["observations"]
    assert (
        result["quarantine"][0]["reason"]
        == "missing_or_invalid_contemporary_asking_rent"
    )


def test_idempotent_publish_rejects_changed_inputs_and_detects_corruption(tmp_path):
    out = tmp_path / "dataset"
    manifest = build_dataset([record()], out, as_of="2026-03-01")
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert build_dataset([record()], out, as_of="2026-03-01") == manifest
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
    with pytest.raises(ValueError, match="identity changed"):
        build_dataset([record(beds=1)], out, as_of="2026-03-01")
    (out / "observations.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="integrity"):
        build_dataset([record()], out, as_of="2026-03-01")


def test_database_adapter_reads_existing_capture_history(tmp_path):
    from apartments.db import connect
    from apartments.temporal import retain_capture

    db = connect(tmp_path / "source.duckdb")
    raw = record()["raw"]
    raw.update(
        source="streeteasy",
        source_listing_id="b/1d",
        canonical_url="https://streeteasy.com/building/b/1d",
        captured_at="2026-01-01T00:00:00Z",
        unit="1D",
    )
    retain_capture(db, "capture", raw)
    db.execute("UPDATE attribute_versions SET recorded_at=TIMESTAMPTZ '2026-01-02'")
    db.close()
    manifest = build_dataset(
        tmp_path / "source.duckdb", tmp_path / "out", as_of="2026-03-01"
    )
    assert manifest["counts"]["observations"] == 1
    row = json.loads((tmp_path / "out/observations.jsonl").read_text())
    assert row["unit_id"] == "streeteasy:b/1d"
    assert row["rent"] == 2500


def test_explicit_historical_assertions_do_not_backfill_unmentioned_fields(
    tmp_path, monkeypatch
):
    ledger = tmp_path / "historical.jsonl"
    monkeypatch.setattr(corrections, "now", lambda: datetime(2026, 2, 20, tzinfo=UTC))
    for start, until, beds in [
        ("2015-01-01", "2020-01-01", 0),
        ("2020-01-01", None, 1),
    ]:
        validity = {"from": start}
        if until:
            validity["until"] = until
        corrections.append(
            ledger,
            author="Ben",
            reason="Dated renovation evidence",
            edit={
                "target": {"source": "streeteasy", "source_listing_id": "b/1d"},
                "validity": validity,
                "patch": [
                    {"op": "replace", "path": "/attributes/bedrooms", "value": beds}
                ],
            },
        )
    result = project_records(
        [record(beds=1)],
        as_of="2026-03-01",
        overlay=corrections.Overlay(ledger, as_of="2026-03-01"),
    )
    facts = sorted(result["attribute_assertions"], key=lambda r: r["valid_from"])
    assert [(r["value"], r["valid_from"][:10]) for r in facts] == [
        (0, "2015-01-01"),
        (1, "2020-01-01"),
    ]
    assert all(r["path"] == "/attributes/bedrooms" for r in facts)
    assert all("rent" not in r and "bathrooms" not in r for r in facts)
    assert result["intervals"][0]["valid_from"].startswith("2026-01-01")
    assert len(result["observations"]) == 1


def test_conflicting_historical_assertions_fail_before_first_capture(
    tmp_path, monkeypatch
):
    ledger = tmp_path / "conflict.jsonl"
    monkeypatch.setattr(corrections, "now", lambda: datetime(2026, 2, 20, tzinfo=UTC))
    for beds in (0, 1):
        corrections.append(
            ledger,
            author="Ben",
            reason="Conflicting histories",
            edit={
                "target": {"source": "streeteasy", "source_listing_id": "b/1d"},
                "validity": {"from": "2015-01-01", "until": "2020-01-01"},
                "patch": [
                    {"op": "replace", "path": "/attributes/bedrooms", "value": beds}
                ],
            },
        )
    with pytest.raises(corrections.CorrectionError, match="Conflicting"):
        project_records(
            [record()],
            as_of="2026-03-01",
            overlay=corrections.Overlay(ledger, as_of="2026-03-01"),
        )


def test_unknown_time_is_quarantined_and_future_knowledge_not_exposed():
    unknown = record(at=None)
    result = project_records([unknown], as_of="2026-03-01")
    assert result["quarantine"][0]["reason"] == "unknown_collection_or_knowledge_time"
    unknown["observation"]["recorded_at"] = "2026-04-01"
    assert not project_records([unknown], as_of="2026-03-01")["quarantine"]


def test_furnished_short_term_and_concession_flags_preserve_price_basis():
    row = record()
    row["raw"]["archive_listing"]["pricing"] = {
        "price": 2500,
        "monthsFree": 1,
        "furnishedRent": 2500,
        "leaseTermMonths": 3,
        "netEffectiveRent": 2200,
    }
    out = project_records([row], as_of="2026-03-01")["observations"][0]
    assert out["furnished"] and out["short_term"] and out["concession"]
    assert out["rent"] == 2500
    assert out["price_basis"] == "gross_advertised_rent"


def test_assertions_reflect_final_sequential_patch_value(tmp_path, monkeypatch):
    ledger = tmp_path / "sequential.jsonl"
    monkeypatch.setattr(corrections, "now", lambda: datetime(2026, 2, 20, tzinfo=UTC))
    corrections.append(
        ledger,
        author="Ben",
        reason="Sequential JSON Patch",
        edit={
            "target": {"source": "streeteasy", "source_listing_id": "b/1d"},
            "validity": {"from": "2015-01-01", "until": "2020-01-01"},
            "patch": [
                {"op": "replace", "path": "/attributes/bedrooms", "value": 0},
                {"op": "replace", "path": "/attributes/bedrooms", "value": 1},
            ],
        },
    )
    out = project_records(
        [record()],
        as_of="2026-03-01",
        overlay=corrections.Overlay(ledger, as_of="2026-03-01"),
    )
    assert len(out["attribute_assertions"]) == 1
    assert out["attribute_assertions"][0]["value"] == 1
