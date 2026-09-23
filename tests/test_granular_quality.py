from pathlib import Path

import duckdb

from apartments.granular_quality import audit_dataset


def test_audit_dataset_reports_quality_without_dropping_duplicate_events(
    tmp_path: Path,
):
    db = duckdb.connect()
    try:
        (tmp_path / "listing_observations").mkdir()
        (tmp_path / "event_mentions").mkdir()
        db.execute("""CREATE TABLE listings AS SELECT * FROM (VALUES
            (1::BIGINT, 'u', 'l1', 'rental', 'house', '2A', 2.0, 1.0, 800.0, 3.0, 1.0, 1.0, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, 'ok', NULL::VARCHAR),
            (2::BIGINT, 'u', 'l1', 'rental', 'house-2', '2B', -1.0, NULL::DOUBLE, -4.0, 3.0, 1.0, 1.0, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, 'error', 'bad')
        ) x(snapshot_id,url,listing_id,listing_type,building_slug,unit_label,bedrooms,bathrooms,square_feet,room_count,collected_at,parsed_at,source_created_at,features_json,amenities_json,pricing_json,parse_status,error)""")
        db.execute(
            "COPY listings TO ? (FORMAT PARQUET)",
            [str(tmp_path / "listing_observations" / "part.parquet")],
        )
        db.execute("""CREATE TABLE events AS SELECT * FROM (VALUES
            (1::BIGINT, 0::BIGINT, 0::BIGINT, 'l1', 'l1', 'rental', '2024-01-01', 2000.0, 'x', NULL::DOUBLE, '{}', 'same'),
            (1::BIGINT, 0::BIGINT, 1::BIGINT, 'l1', 'l1', 'rental', '2024-01-01', 2000.0, 'x', NULL::DOUBLE, '{}', 'same'),
            (1::BIGINT, 0::BIGINT, 2::BIGINT, 'l1', 'l1', 'rental', 'bad-date', -1.0, 'x', NULL::DOUBLE, '{}', 'bad')
        ) x(snapshot_id,episode_index,event_index,listing_id,event_listing_id,event_category,event_date,price,status,percent_change,event_json,event_key)""")
        db.execute(
            "COPY events TO ? (FORMAT PARQUET)",
            [str(tmp_path / "event_mentions" / "part.parquet")],
        )
    finally:
        db.close()

    report = audit_dataset(tmp_path)
    assert report["tables"]["counts"] == {
        "listing_observations": 2,
        "event_mentions": 3,
        "snapshots": 0,
        "fetch_observations": 0,
        "building_observations": 0,
        "inventory_rows": 0,
    }
    assert report["event_mentions"]["event_key"] == {
        "rows": 3,
        "distinct": 2,
        "duplicate_rows": 1,
    }
    assert report["event_mentions"]["dates"] == {"parseable": 2, "unparseable": 1}
    assert report["numeric"]["listing_observations"]["bedrooms"]["invalid"] == 1
    assert len(report["listing_observations"]["attribute_disagreements"]) == 1
    assert report["listing_observations"]["distinct_listing_identities"] == 1
    assert report["listing_observations"]["source_pairs"]["rental"] == 2
    assert report["event_mentions"]["occurrence_uniqueness"] == {
        "rows": 3,
        "distinct_occurrences": 3,
    }
    assert report["event_mentions"]["years"] == {"min": 2024, "max": 2024}


def test_audit_optional_inventory_and_building_diagnostics(tmp_path: Path):
    db = duckdb.connect()
    try:
        (tmp_path / "snapshots").mkdir()
        (tmp_path / "building_observations").mkdir()
        (tmp_path / "inventory_observations").mkdir()
        db.execute(
            "CREATE TABLE s AS SELECT 1::BIGINT snapshot_id, 'u' url, 'h' body_hash, 'listing' kind, 1.0 observed_at"
        )
        db.execute(
            "COPY s TO ? (FORMAT PARQUET)", [str(tmp_path / "snapshots" / "p.parquet")]
        )
        db.execute(
            "CREATE TABLE b AS SELECT 1::BIGINT snapshot_id, 'b' building_slug, 'id' building_id, 2.0 residential_units, 1.0 latitude, 2.0 longitude, '{}' raw_building_json, 'partial' parse_status, 'x' AS \"error\""
        )
        db.execute(
            "COPY b TO ? (FORMAT PARQUET)",
            [str(tmp_path / "building_observations" / "p.parquet")],
        )
        db.execute(
            "CREATE TABLE i AS SELECT 1::BIGINT snapshot_id, 3::BIGINT \"count\", 2::BIGINT row_count, '[]' expected_counts_json, '{}' raw_inventory_json, 'ok' parse_status, NULL::VARCHAR AS \"error\""
        )
        db.execute(
            "COPY i TO ? (FORMAT PARQUET)",
            [str(tmp_path / "inventory_observations" / "p.parquet")],
        )
    finally:
        db.close()
    report = audit_dataset(tmp_path)
    assert report["parse_failures"]["building_observations"]["by_status"] == {
        "partial": 1
    }
    assert report["inventory_observations"]["count_vs_row_count"]["mismatch_rows"] == 1
    assert report["referential_checks"]["building_observations_missing_snapshot"] == 0
