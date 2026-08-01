import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .db import connect
from .scope import in_scope, load_targets, normalize_address

ENDPOINT = "https://api.rentcast.io/v1/listings/rental/long-term"


def _integer(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def fetch_rentals(api_key: str, limit: int = 500) -> list[dict[str, Any]]:
    targets = load_targets()
    street = targets["street"]
    params = {
        "latitude": street["search_latitude"],
        "longitude": street["search_longitude"],
        "radius": street["search_radius_miles"],
        "status": "Active",
        "limit": limit,
    }
    response = httpx.get(
        ENDPOINT,
        params=params,
        headers={"X-Api-Key": api_key, "Accept": "application/json"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Expected RentCast to return a JSON list")
    return payload


def _history_items(history: Any):
    if isinstance(history, dict):
        for date, event in history.items():
            yield date, event if isinstance(event, dict) else {"event": event}
    elif isinstance(history, list):
        for event in history:
            if isinstance(event, dict):
                yield event.get("date") or event.get("eventDate"), event


def ingest_payload(
    payload: list[dict[str, Any]],
    scope: str,
    db_path: str = "data/apartments.duckdb",
    observed_at: datetime | None = None,
) -> int:
    targets = load_targets()
    observed_at = observed_at or datetime.now(timezone.utc)
    db = connect(db_path)
    accepted = 0
    for item in payload:
        listing_id = str(item.get("id") or item.get("listingId") or "")
        address = item.get("addressLine1") or item.get("formattedAddress")
        if not listing_id or not in_scope(address, scope, targets):
            continue
        accepted += 1
        raw = json.dumps(item, separators=(",", ":"), sort_keys=True)
        db.execute(
            """INSERT INTO listings (
                source, source_listing_id, address_line, canonical_address, unit,
                city, state, zipcode, latitude, longitude, property_type,
                bedrooms, bathrooms, square_feet, year_built, listing_type, raw_json
            ) VALUES ('rentcast', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, source_listing_id) DO UPDATE SET
                address_line=excluded.address_line, canonical_address=excluded.canonical_address,
                unit=excluded.unit, latitude=excluded.latitude, longitude=excluded.longitude,
                property_type=excluded.property_type, bedrooms=excluded.bedrooms,
                bathrooms=excluded.bathrooms, square_feet=excluded.square_feet,
                year_built=excluded.year_built, listing_type=excluded.listing_type,
                last_seen_at=now(), raw_json=excluded.raw_json""",
            [
                listing_id, address, normalize_address(address), item.get("addressLine2"),
                item.get("city"), item.get("state"), item.get("zipCode"),
                item.get("latitude"), item.get("longitude"), item.get("propertyType"),
                item.get("bedrooms"), item.get("bathrooms"), _integer(item.get("squareFootage")),
                _integer(item.get("yearBuilt")), item.get("listingType"), raw,
            ],
        )
        db.execute(
            """INSERT INTO listing_snapshots VALUES
                ('rentcast', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
            [
                listing_id, observed_at, item.get("status"), _integer(item.get("price")),
                item.get("listedDate"), item.get("removedDate"), _integer(item.get("daysOnMarket")),
                scope, raw,
            ],
        )
        for event_at, event in _history_items(item.get("history")):
            event_raw = json.dumps(event, separators=(",", ":"), sort_keys=True)
            event_type = event.get("event") or event.get("eventType") or event.get("status")
            event_price = _integer(event.get("price"))
            key_text = f"rentcast|{listing_id}|{event_at}|{event_type}|{event_price}"
            event_key = hashlib.sha256(key_text.encode()).hexdigest()
            db.execute(
                """INSERT INTO listing_events VALUES (?, 'rentcast', ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [event_key, listing_id, event_at, event_type, event_price, event_raw],
            )
    db.close()
    return accepted


def collect(scope: str, db_path: str = "data/apartments.duckdb") -> tuple[int, int, Path]:
    api_key = os.getenv("RENTCAST_API_KEY")
    if not api_key:
        raise RuntimeError("RENTCAST_API_KEY is missing; copy .env.example to .env")
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    payload = fetch_rentals(api_key)
    raw_path = Path("data/raw/rentcast") / f"{started:%Y-%m-%dT%H-%M-%SZ}_{scope}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(payload, indent=2))
    accepted = ingest_payload(payload, scope, db_path, started)
    db = connect(db_path)
    db.execute(
        "INSERT INTO collection_runs VALUES (?, 'rentcast', ?, ?, ?, ?, ?, ?, NULL)",
        [run_id, scope, started, datetime.now(timezone.utc), len(payload), accepted, str(raw_path)],
    )
    db.close()
    return len(payload), accepted, raw_path
