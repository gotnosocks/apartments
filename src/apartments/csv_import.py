import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .db import connect
from .scope import in_scope, load_targets, normalize_address


def _number(value: str | None, kind=float):
    try:
        return kind(float(value)) if value not in (None, "") else None
    except ValueError:
        return None


def ingest_csv(path: Path, scope: str, db_path: str = "data/apartments.duckdb") -> int:
    targets = load_targets()
    db = connect(db_path)
    count = 0
    with path.open(newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            address = row.get("address")
            if not in_scope(address, scope, targets):
                continue
            source = row.get("source") or "manual"
            listing_id = row.get("source_listing_id") or hashlib.sha256(
                f"{source}|{address}|{row.get('unit')}|{row_number}".encode()
            ).hexdigest()[:20]
            observed_at = row.get("observed_at") or datetime.now(timezone.utc).isoformat()
            raw = json.dumps(row)
            db.execute(
                """INSERT INTO listings (
                    source, source_listing_id, address_line, canonical_address, unit,
                    city, state, zipcode, property_type, bedrooms, bathrooms,
                    square_feet, listing_type, raw_json
                ) VALUES (?, ?, ?, ?, ?, 'New York', 'NY', ?, ?, ?, ?, ?, 'Rental', ?)
                ON CONFLICT (source, source_listing_id) DO UPDATE SET
                    last_seen_at=now(), raw_json=excluded.raw_json""",
                [source, listing_id, address, normalize_address(address), row.get("unit"),
                 row.get("zipcode"), row.get("property_type"), _number(row.get("bedrooms")),
                 _number(row.get("bathrooms")), _number(row.get("square_feet"), int), raw],
            )
            db.execute(
                """INSERT INTO listing_snapshots (
                    source, source_listing_id, observed_at, status, asking_rent,
                    listed_date, removed_date, days_on_market, scope, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                [source, listing_id, observed_at, row.get("status"), _number(row.get("asking_rent"), int),
                 row.get("listed_date") or None, row.get("removed_date") or None,
                 _number(row.get("days_on_market"), int), scope, raw],
            )
            count += 1
    db.close()
    return count
