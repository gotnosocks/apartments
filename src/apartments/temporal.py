"""Append-only capture interpretations and collection evidence.

Source dates are assertions by StreetEasy, not proof of when an attribute changed.
"""

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlparse

SCHEMA = """
CREATE TABLE IF NOT EXISTS attribute_versions (
    version_id VARCHAR PRIMARY KEY,
    capture_id VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    source_listing_id VARCHAR NOT NULL,
    episode_id VARCHAR,
    building_slug VARCHAR,
    unit VARCHAR,
    collected_at TIMESTAMPTZ,
    collection_time_basis VARCHAR NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT current_timestamp,
    parser_version VARCHAR NOT NULL,
    source_created_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    source_on_market_date DATE,
    bedrooms DOUBLE,
    bathrooms DOUBLE,
    square_feet DOUBLE,
    attributes_json JSON NOT NULL,
    structured_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS event_capture_evidence (
    version_id VARCHAR NOT NULL,
    event_key VARCHAR NOT NULL,
    event_json JSON NOT NULL,
    PRIMARY KEY(version_id,event_key)
);
CREATE TABLE IF NOT EXISTS archive_observations (
    archive_key VARCHAR NOT NULL,
    observation_id BIGINT NOT NULL,
    generation BIGINT,
    url VARCHAR NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT current_timestamp,
    status INTEGER,
    body_hash VARCHAR,
    not_modified BOOLEAN,
    error VARCHAR,
    content_type VARCHAR,
    headers_json JSON,
    body_relative_path VARCHAR,
    PRIMARY KEY(archive_key,observation_id)
);
CREATE OR REPLACE VIEW attribute_collection_evidence AS
SELECT v.version_id,v.capture_id,v.source,v.source_listing_id,v.episode_id,
       o.archive_key,o.observation_id,o.collected_at,v.recorded_at,
       o.status,o.not_modified,o.body_hash
FROM attribute_versions v JOIN archive_observations o
  ON o.url=json_extract_string(v.provenance_json,'$.url')
 AND o.body_hash=json_extract_string(v.provenance_json,'$.body_hash')
WHERE o.error IS NULL AND (o.status BETWEEN 200 AND 299 OR o.status=304);
"""
PARSER_VERSION = "capture-history-v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def retain_capture(
    db, capture_id, item, manifest=None, *, collected_at=None, time_basis=None
):
    """Retain an immutable interpretation even when captures/current rows are updated."""
    manifest = manifest or {}
    collected_at = collected_at if collected_at is not None else item.get("captured_at")
    basis = time_basis or ("capture_timestamp" if collected_at else "unknown")
    source_id = item.get("source_listing_id") or urlparse(
        item["canonical_url"]
    ).path.strip("/").removeprefix("building/")
    listing = item.get("archive_listing") or {}
    episode = (
        item.get("street_easy_rental_id")
        or listing.get("id")
        or item.get("canonical_url")
    )
    attrs = {
        key: value
        for key, value in item.items()
        if key not in ("price_history", "captured_at", "archive_listing")
    }
    # Hash the entire interpretation, not only selected columns. Re-parsing the
    # same source with changed fields creates another version rather than replacing it.
    payload = {
        "capture_id": capture_id,
        "item": item,
        "manifest": manifest,
        "collected_at": str(collected_at) if collected_at is not None else None,
        "time_basis": basis,
        "parser_version": PARSER_VERSION,
    }
    version_id = hashlib.sha256(canonical(payload).encode()).hexdigest()
    if db.execute(
        "SELECT 1 FROM attribute_versions WHERE version_id=?", [version_id]
    ).fetchone():
        evidence_count = db.execute(
            "SELECT count(*) FROM event_capture_evidence WHERE version_id=?",
            [version_id],
        ).fetchone()[0]
        if evidence_count == len(item.get("price_history", [])):
            return version_id
    numeric = item.get("attributes") or {}
    db.execute(
        """INSERT INTO attribute_versions(
        version_id,capture_id,source,source_listing_id,episode_id,building_slug,unit,
        collected_at,collection_time_basis,parser_version,source_created_at,
        source_updated_at,source_on_market_date,bedrooms,bathrooms,square_feet,
        attributes_json,structured_json,provenance_json)
        VALUES (?,?,?,?,?,?,?,TRY_CAST(? AS TIMESTAMPTZ),?,?,TRY_CAST(? AS TIMESTAMPTZ),
        TRY_CAST(? AS TIMESTAMPTZ),TRY_CAST(? AS DATE),?,?,?,CAST(? AS JSON),CAST(? AS JSON),CAST(? AS JSON))
        ON CONFLICT DO NOTHING""",
        [
            version_id,
            capture_id,
            item.get("source", "streeteasy"),
            source_id,
            str(episode) if episode is not None else None,
            item.get("building_slug"),
            item.get("unit"),
            collected_at,
            basis,
            PARSER_VERSION,
            listing.get("createdAt"),
            listing.get("updatedAt"),
            listing.get("onMarketAt"),
            numeric.get("bedrooms"),
            numeric.get("bathrooms"),
            numeric.get("square_feet"),
            canonical(attrs),
            canonical(item),
            canonical(manifest),
        ],
    )
    from .streeteasy import _event_datetime

    evidence = []
    for event in item.get("price_history", []):
        event_at = _event_datetime(event.get("date"))
        text = f"streeteasy|{source_id}|{event_at}|{event.get('event')}|{event.get('base_rent')}|{event.get('listing_url')}"
        key = hashlib.sha256(text.encode()).hexdigest()
        evidence.append([version_id, key, canonical(event)])
    if evidence:
        db.executemany(
            "INSERT INTO event_capture_evidence VALUES (?,?,?) ON CONFLICT DO NOTHING",
            evidence,
        )
    return version_id


def sync_observations(source, target):
    """Mirror every fetch, including 304s/errors, without re-reading body files."""
    tables = {
        r[0]
        for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "observations" not in tables:
        return 0  # Also permits small synthetic import fixtures.
    first = source.execute(
        "SELECT url,fetched FROM observations ORDER BY id LIMIT 1"
    ).fetchone()
    if first is None:
        return 0
    # Stable across moving/copying the archive; excludes filesystem location.
    archive_key = hashlib.sha256(canonical(list(first)).encode()).hexdigest()
    known = {
        r[0]
        for r in target.execute(
            "SELECT observation_id FROM archive_observations WHERE archive_key=?",
            [archive_key],
        ).fetchall()
    }
    rows = source.execute("""SELECT o.id,o.generation,o.url,o.fetched,o.status,o.body_hash,
        o.not_modified,o.error,o.content_type,o.headers,b.path FROM observations o
        LEFT JOIN bodies b ON b.hash=o.body_hash ORDER BY o.id""")
    batch = [
        [archive_key, *list(r[:3]), datetime.fromtimestamp(r[3], UTC), *list(r[4:])]
        for r in rows
        if r[0] not in known
    ]
    if batch:
        target.executemany(
            """INSERT INTO archive_observations(archive_key,observation_id,generation,url,
            collected_at,status,body_hash,not_modified,error,content_type,headers_json,body_relative_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
            batch,
        )
    return len(batch)


def backfill_capture_history(db, source=None):
    """Reconstruct evidence from existing captures; never guess historic import time."""
    original_times = {}
    if source is not None:
        original_times = dict(
            source.execute("""SELECT s.id, min(o.fetched) FROM snapshots s
            JOIN observations o ON o.generation=s.generation AND o.url=s.url AND o.body_hash=s.body_hash
            WHERE o.error IS NULL AND (o.status BETWEEN 200 AND 299 OR o.status=304)
            GROUP BY s.id""").fetchall()
        )
    rows = db.execute(
        "SELECT capture_id,structured_json,manifest_json FROM captures"
    ).fetchall()
    before = db.execute("SELECT count(*) FROM attribute_versions").fetchone()[0]
    for start in range(0, len(rows), 20):
        db.execute("BEGIN TRANSACTION")
        try:
            for cid, raw, provenance in rows[start : start + 20]:
                item = json.loads(raw)
                manifest = json.loads(provenance) if provenance else {}
                epoch = original_times.get(manifest.get("snapshot_id"))
                collected_at = (
                    datetime.fromtimestamp(epoch, UTC).isoformat()
                    if epoch is not None
                    else None
                )
                retain_capture(
                    db,
                    cid,
                    item,
                    manifest,
                    collected_at=collected_at,
                    time_basis="archive_response_fetched"
                    if epoch is not None
                    else None,
                )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return db.execute("SELECT count(*) FROM attribute_versions").fetchone()[0] - before
