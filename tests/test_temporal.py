import json
import sqlite3
from apartments.db import connect
from apartments.streeteasy import ingest_item
from apartments.temporal import (
    retain_capture,
    backfill_capture_history,
    sync_observations,
)


def item(at="2026-09-07T12:00:00Z", size=700):
    return {
        "source": "streeteasy",
        "source_listing_id": "b/1a",
        "building_slug": "b",
        "unit": "1A",
        "address": "1 Test Street",
        "captured_at": at,
        "canonical_url": "https://streeteasy.com/rental/123",
        "street_easy_rental_id": "123",
        "attributes": {"square_feet": size, "bedrooms": 1, "bathrooms": 1},
        "home_features": ["Dishwasher"],
        "archive_listing": {
            "createdAt": "2015-01-01T00:00:00Z",
            "updatedAt": "2015-02-01T00:00:00Z",
        },
        "price_history": [{"date": "1/1/2015", "base_rent": 2000, "event": "Listed"}],
    }


def test_versions_survive_reparse_and_source_dates_are_not_collection_dates(tmp_path):
    db = connect(tmp_path / "test.duckdb")
    first = item()
    ingest_item(first, connection=db, capture_id="first")
    second = item("2026-09-08T12:00:00Z", 800)
    ingest_item(second, connection=db, capture_id="second")
    changed = item(size=710)
    ingest_item(changed, connection=db, capture_id="first")
    ingest_item(changed, connection=db, capture_id="first")
    assert db.execute(
        "SELECT square_feet FROM attribute_versions ORDER BY square_feet"
    ).fetchall() == [(700.0,), (710.0,), (800.0,)]
    assert (
        db.execute(
            "SELECT count(*) FROM attribute_versions WHERE collected_at < TIMESTAMPTZ '2020-01-01'"
        ).fetchone()[0]
        == 0
    )
    assert db.execute("SELECT count(*) FROM event_capture_evidence").fetchone()[0] == 3
    assert db.execute("SELECT count(*) FROM listing_events").fetchone()[0] == 1
    assert (
        db.execute(
            "SELECT count(*) FROM attribute_versions WHERE source_created_at < TIMESTAMPTZ '2020-01-01'"
        ).fetchone()[0]
        == 3
    )
    assert (
        db.execute(
            "SELECT count(DISTINCT version_id) FROM attribute_versions"
        ).fetchone()[0]
        == 3
    )
    db.close()


def test_unchanged_fetches_and_errors_are_retained_idempotently(tmp_path):
    raw = sqlite3.connect(":memory:")
    raw.executescript("""CREATE TABLE observations(id,generation,url,fetched,status,body_hash,not_modified,error,content_type,headers);
    CREATE TABLE bodies(hash,path); INSERT INTO bodies VALUES ('hash','bodies/ha/hash.gz');
    INSERT INTO observations VALUES(1,1,'url',1000,200,'hash',0,NULL,'text/html','{}');
    INSERT INTO observations VALUES(2,2,'url',2000,304,'hash',1,NULL,'text/html','{}');
    INSERT INTO observations VALUES(3,2,'url',3000,403,NULL,0,'blocked','text/html','{}');""")
    db = connect(tmp_path / "test.duckdb")
    assert sync_observations(raw, db) == 3
    assert sync_observations(raw, db) == 0
    retain_capture(db, "c", item(), {"url": "url", "body_hash": "hash"})
    assert db.execute(
        "SELECT observation_id FROM attribute_collection_evidence ORDER BY 1"
    ).fetchall() == [(1,), (2,)]
    assert (
        db.execute(
            "SELECT count(*) FROM archive_observations WHERE status=403"
        ).fetchone()[0]
        == 1
    )
    db.close()


def test_capture_without_source_id_uses_existing_url_fallback(tmp_path):
    db = connect(tmp_path / "test.duckdb")
    capture = item()
    del capture["source_listing_id"]
    source_id, _ = ingest_item(capture, connection=db, capture_id="fallback")
    assert (
        db.execute("SELECT source_listing_id FROM attribute_versions").fetchone()[0]
        == source_id
    )
    assert (
        db.execute("""SELECT count(*) FROM event_capture_evidence
        JOIN listing_events USING (event_key)""").fetchone()[0]
        == 1
    )
    db.close()


def test_backfill_uses_original_fetch_not_extraction_time(tmp_path):
    raw = sqlite3.connect(":memory:")
    raw.executescript("""CREATE TABLE snapshots(id,generation,url,body_hash);
        CREATE TABLE observations(generation,url,body_hash,fetched,status,error);
        INSERT INTO snapshots VALUES(1,1,'url','hash');
        INSERT INTO observations VALUES(1,'url','hash',1000,200,NULL);""")
    db = connect(tmp_path / "test.duckdb")
    db.execute(
        "INSERT INTO captures VALUES('c','streeteasy','b/1a',now(),NULL,NULL,?,?)",
        [json.dumps({"snapshot_id": 1}), json.dumps(item())],
    )
    assert backfill_capture_history(db, raw) == 1
    assert backfill_capture_history(db, raw) == 0
    assert (
        db.execute("SELECT epoch(collected_at) FROM attribute_versions").fetchone()[0]
        == 1000
    )
    assert (
        db.execute("SELECT collection_time_basis FROM attribute_versions").fetchone()[0]
        == "archive_response_fetched"
    )
    db.close()
