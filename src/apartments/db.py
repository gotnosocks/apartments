from pathlib import Path

import duckdb

DEFAULT_DB = Path("data/apartments.duckdb")

SCHEMA = """
CREATE TABLE IF NOT EXISTS buildings (
    source VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    bbl VARCHAR,
    bin VARCHAR,
    canonical_address VARCHAR,
    borough VARCHAR,
    zipcode VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    year_built INTEGER,
    residential_units INTEGER,
    total_units INTEGER,
    floors DOUBLE,
    building_class VARCHAR,
    raw_json JSON,
    updated_at TIMESTAMPTZ DEFAULT current_timestamp,
    PRIMARY KEY (source, source_id)
);

CREATE TABLE IF NOT EXISTS listings (
    source VARCHAR NOT NULL,
    source_listing_id VARCHAR NOT NULL,
    address_line VARCHAR,
    canonical_address VARCHAR,
    unit VARCHAR,
    city VARCHAR,
    state VARCHAR,
    zipcode VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    property_type VARCHAR,
    bedrooms DOUBLE,
    bathrooms DOUBLE,
    square_feet INTEGER,
    year_built INTEGER,
    listing_type VARCHAR,
    first_seen_at TIMESTAMPTZ DEFAULT current_timestamp,
    last_seen_at TIMESTAMPTZ DEFAULT current_timestamp,
    raw_json JSON,
    PRIMARY KEY (source, source_listing_id)
);

ALTER TABLE listings ADD COLUMN IF NOT EXISTS floor INTEGER;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS unit_letter VARCHAR;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS unit_format VARCHAR;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS unit_suffix VARCHAR;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS floor_inference VARCHAR;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS unit_kind VARCHAR;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS unit_is_specific BOOLEAN;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS is_furnished BOOLEAN;

CREATE TABLE IF NOT EXISTS unit_aliases (
    building_slug VARCHAR NOT NULL,
    canonical_unit VARCHAR NOT NULL,
    alias_unit VARCHAR NOT NULL,
    evidence_type VARCHAR NOT NULL,
    evidence_url VARCHAR,
    confidence DOUBLE,
    notes VARCHAR,
    created_at TIMESTAMPTZ DEFAULT current_timestamp,
    PRIMARY KEY (building_slug, canonical_unit, alias_unit)
);

CREATE TABLE IF NOT EXISTS listing_snapshots (
    source VARCHAR NOT NULL,
    source_listing_id VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    status VARCHAR,
    asking_rent INTEGER,
    listed_date TIMESTAMPTZ,
    removed_date TIMESTAMPTZ,
    days_on_market INTEGER,
    scope VARCHAR,
    raw_json JSON,
    PRIMARY KEY (source, source_listing_id, observed_at)
);

CREATE TABLE IF NOT EXISTS listing_events (
    event_key VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,
    source_listing_id VARCHAR NOT NULL,
    event_at TIMESTAMPTZ,
    event_type VARCHAR,
    price INTEGER,
    raw_json JSON
);

CREATE TABLE IF NOT EXISTS captures (
    capture_id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,
    source_listing_id VARCHAR NOT NULL,
    captured_at TIMESTAMPTZ,
    bundle_path VARCHAR,
    page_html_path VARCHAR,
    manifest_json JSON,
    structured_json JSON
);

CREATE TABLE IF NOT EXISTS assets (
    asset_key VARCHAR PRIMARY KEY,
    source_url VARCHAR NOT NULL,
    category VARCHAR,
    local_path VARCHAR,
    sha256 VARCHAR,
    bytes BIGINT,
    metadata_json JSON
);

CREATE TABLE IF NOT EXISTS capture_assets (
    capture_id VARCHAR NOT NULL,
    asset_key VARCHAR NOT NULL,
    PRIMARY KEY (capture_id, asset_key)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,
    scope VARCHAR NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    requested_count INTEGER,
    accepted_count INTEGER,
    raw_path VARCHAR,
    error VARCHAR
);
"""


def connect(path: Path | str = DEFAULT_DB) -> duckdb.DuckDBPyConnection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    connection.execute(SCHEMA)
    return connection
