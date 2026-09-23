import hashlib
import json

import duckdb
import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from apartments.rent_basis_measurement import measure
from models.rent_basis_price_review import own_event_review, run


def test_initial_target_uses_own_rental_active_event_and_calendar_date():
    row = {
        "source_listing_id": "12",
        "price_at": "2019-03-12T00:00:00Z",
        "asking_rent": 2878,
    }
    event = {
        "snapshot_id": 1,
        "event_listing_id": "12",
        "event_category": "rental",
        "status": "ACTIVE",
        "event_date": "2019-03-12",
        "price": 2878,
    }
    noise = [
        {**event, "event_listing_id": "99", "price": 1},
        {**event, "event_category": "sale", "price": 1},
        {**event, "snapshot_id": 2, "price": 1},
        {**event, "status": "RENTED", "price": 3100},
    ]
    result = own_event_review(row, 1, [event, *noise])
    assert (
        result["initial_active_events"] == [event]
        and result["initial_event_matches_analytical_target"]
    )
    assert not own_event_review({**row, "price_at": "2019-03-13"}, 1, [event])[
        "initial_event_matches_analytical_target"
    ]
    assert not own_event_review(row, 1, [])["initial_event_matches_analytical_target"]


@pytest.mark.parametrize("fault", [None, "raw_hash", "missing_capture", "event_shard"])
def test_packet_reads_bound_raw_prices_and_events_without_converting_rent(
    tmp_path, fault
):
    archive, history, audit, output = [
        tmp_path / n for n in ("archive", "history", "audit", "output")
    ]
    (archive / "listing_observations").mkdir(parents=True)
    (archive / "event_mentions").mkdir()
    payload = {
        "id": "12",
        "pricing": {
            "priceChanges": [
                {"changedAt": "2019-03-12T20:56:30-04:00", "price": 2878},
                {"changedAt": "2019-03-25T11:00:06-04:00", "price": 3100},
            ],
            "monthsFree": None,
        },
    }
    raw = canonical(payload)
    listing, events = (
        archive / "listing_observations/part-00000.parquet",
        archive / "event_mentions/part-00000.parquet",
    )
    with duckdb.connect() as db:
        db.execute("CREATE TABLE listing(snapshot_id BIGINT, raw_listing_json VARCHAR)")
        db.execute("INSERT INTO listing VALUES (1, ?)", [raw])
        db.execute("COPY listing TO ? (FORMAT PARQUET)", [str(listing)])
        db.execute(
            "CREATE TABLE events AS SELECT 1 AS snapshot_id, '12' AS event_listing_id, 'rental' AS event_category, "
            "'ACTIVE' AS status, '2019-03-12' AS event_date, 2878 AS price, 0 AS episode_index, 0 AS event_index"
        )
        db.execute("COPY events TO ? (FORMAT PARQUET)", [str(events)])
    inventory = {str(p.relative_to(archive)): digest(p) for p in (listing, events)}
    if fault == "event_shard":
        inventory["event_mentions/part-00000.parquet"] = "a" * 64
    publish_bundle(
        history,
        {"source-files.json": canonical(inventory) + "\n"},
        {"version": "historical-test"},
    )
    capture = {
        "capture_id": 2 if fault == "missing_capture" else 1,
        "raw_listing_sha256": "a" * 64
        if fault == "raw_hash"
        else hashlib.sha256(raw.encode()).hexdigest(),
        "measurement": measure("Net rent $2,878. Gross rent $3,100.", 2878),
    }
    case = {
        "source_record": {
            "audit_id": "row",
            "source_listing_id": "12",
            "asking_rent": 2878,
            "price_at": "2019-03-12T00:00:00Z",
            "analysis_price_basis": "historical_initial_own_advertisement_ask",
        },
        "classification": "all_captures_match_explicit_net_only",
        "captures": [capture],
    }
    publish_bundle(
        audit,
        {"cases.jsonl": canonical(case) + "\n"},
        {
            "version": "literal-rent-basis-source-audit-v1",
            "dataset_manifest_sha256": "s" * 64,
        },
    )
    if fault:
        with pytest.raises(ValueError):
            run(audit, history, archive, output)
    else:
        run(audit, history, archive, output)
        result = json.loads((output / "cases.jsonl").read_text())
        assert result["source_record"]["asking_rent"] == 2878
        assert result["original_price_records"][0]["pricing"] == payload["pricing"]
        assert result["original_price_records"][0][
            "initial_event_matches_analytical_target"
        ]
