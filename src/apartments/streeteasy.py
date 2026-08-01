import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .db import connect
from .scope import normalize_address

EXCLUDED_UNITS_PATH = Path("config/excluded_units.json")


def unit_is_excluded(building_slug: str | None, unit: str | None) -> bool:
    if not EXCLUDED_UNITS_PATH.exists():
        return False
    exclusions = json.loads(EXCLUDED_UNITS_PATH.read_text(encoding="utf-8"))
    return str(unit).upper() in {key.upper() for key in exclusions.get(building_slug or "", {})}


def _event_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _is_generic_layout(unit: str | None) -> bool:
    value = re.sub(r"[ _]", "-", (unit or "").strip().upper())
    return bool(
        re.match(r"^\d+(?:BD|BR|BED|BEDROOM)S?[-/]?\d+(?:BA|BATH|BATHROOM)S?$", value)
        or re.match(r"^\d+-?(?:BD|BR|BED|BEDROOM)S?$", value)
    )


def split_unit(unit: str | None) -> tuple[int | None, str | None]:
    """Parse floor-letter units; infer a numeric unit's floor from its first digit."""
    value = (unit or "").strip()
    if _is_generic_layout(value):
        return None, None
    penthouse = re.match(r"^PH([A-Z0-9-]*)$", value, re.I)
    if penthouse:
        suffix = penthouse.group(1).upper() or None
        return None, suffix if suffix and suffix.isalpha() else None
    match = re.match(r"^(\d{1,2})\s*[- ]?\s*([A-Z]+)$", value, re.I)
    if match:
        return int(match.group(1)), match.group(2).upper()
    if value.isdigit():
        return int(value[0]), None
    return None, None


def unit_suffix(unit: str | None) -> str | None:
    value = (unit or "").strip().upper()
    if _is_generic_layout(value):
        return None
    penthouse = re.match(r"^PH([A-Z0-9-]*)$", value)
    if penthouse:
        return penthouse.group(1) or None
    match = re.match(r"^(\d{1,2})\s*[- ]?\s*([A-Z]+)$", value)
    if match:
        return match.group(2)
    return value[1:] or None if value.isdigit() else None


def unit_format(unit: str | None) -> str:
    value = (unit or "").strip()
    if _is_generic_layout(value):
        return "generic-layout"
    if re.match(r"^PH[A-Z0-9-]*$", value, re.I):
        return "penthouse"
    if re.match(r"^\d{1,2}\s*[- ]?\s*[A-Z]+$", value, re.I):
        return "floor-letter"
    return "numeric" if value.isdigit() else "other"


def unit_kind(unit: str | None) -> str:
    return "generic-layout" if _is_generic_layout(unit) else "physical-unit"


def listing_is_furnished(item: dict) -> bool:
    return any(
        "furnished" in str(feature).lower()
        for feature in item.get("home_features", [])
    )


def ingest_export(
    path: Path,
    db_path: str = "data/apartments.duckdb",
    connection=None,
) -> tuple[str, int]:
    item = json.loads(path.read_text(encoding="utf-8"))
    if item.get("source") != "streeteasy" or not isinstance(item.get("price_history"), list):
        raise ValueError("This does not look like a StreetEasy exporter JSON file")

    source_id = item.get("source_listing_id")
    if not source_id:
        source_id = urlparse(item["canonical_url"]).path.strip("/").removeprefix("building/")
    if unit_is_excluded(item.get("building_slug"), item.get("unit")):
        return source_id, 0
    attributes = item.get("attributes", {})
    inferred_floor, inferred_letter = split_unit(item.get("unit"))
    floor = item.get("floor") if item.get("floor") is not None else inferred_floor
    unit_letter = item.get("unit_letter") or inferred_letter
    suffix = item.get("unit_suffix") or unit_suffix(item.get("unit"))
    format_name = item.get("unit_format") or unit_format(item.get("unit"))
    floor_inference = item.get("floor_inference") or (
        "heuristic-first-digit" if format_name == "numeric" else
        "parsed-floor-letter" if format_name == "floor-letter" else None
    )
    kind = item.get("unit_kind") or unit_kind(item.get("unit"))
    is_specific = item.get("unit_is_specific") if item.get("unit_is_specific") is not None else kind == "physical-unit"
    is_furnished = listing_is_furnished(item)
    raw = json.dumps(item, separators=(",", ":"), sort_keys=True)
    owns_connection = connection is None
    db = connection or connect(db_path)
    building_raw = json.dumps({
        "building_slug": item.get("building_slug"),
        "building_address": item.get("building_address"),
        "building_amenities": item.get("building_amenities", []),
    })
    db.execute(
        """INSERT INTO buildings (
            source, source_id, canonical_address, borough, zipcode, raw_json, updated_at
        ) VALUES ('streeteasy', ?, ?, 'Manhattan', ?, ?, now())
        ON CONFLICT (source, source_id) DO UPDATE SET
            canonical_address=excluded.canonical_address, zipcode=excluded.zipcode,
            raw_json=excluded.raw_json, updated_at=now()""",
        [item.get("building_slug"), item.get("building_address"), item.get("zipcode"), building_raw],
    )
    db.execute(
        """INSERT INTO listings (
            source, source_listing_id, address_line, canonical_address, unit,
            floor, unit_letter, unit_suffix, unit_format, floor_inference,
            unit_kind, unit_is_specific, is_furnished, city, state, zipcode, property_type, bedrooms,
            bathrooms, square_feet, listing_type, raw_json
        ) VALUES ('streeteasy', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New York', 'NY', ?, 'Rental unit', ?, ?, ?, 'Rental', ?)
        ON CONFLICT (source, source_listing_id) DO UPDATE SET
            address_line=excluded.address_line, canonical_address=excluded.canonical_address,
            unit=excluded.unit, floor=excluded.floor, unit_letter=excluded.unit_letter,
            unit_suffix=excluded.unit_suffix, unit_format=excluded.unit_format,
            floor_inference=excluded.floor_inference, unit_kind=excluded.unit_kind,
            unit_is_specific=excluded.unit_is_specific,
            is_furnished=excluded.is_furnished,
            bedrooms=excluded.bedrooms, bathrooms=excluded.bathrooms,
            square_feet=excluded.square_feet, last_seen_at=now(),
            raw_json=excluded.raw_json""",
        [source_id, item.get("address"), normalize_address(item.get("address")),
         item.get("unit"), floor, unit_letter, suffix, format_name, floor_inference,
         kind, is_specific, is_furnished, item.get("zipcode"), attributes.get("bedrooms"),
         attributes.get("bathrooms"), attributes.get("square_feet"), raw],
    )
    captured_at = item.get("captured_at")
    db.execute(
        """INSERT INTO listing_snapshots (
            source, source_listing_id, observed_at, status, asking_rent,
            days_on_market, scope, raw_json
        ) VALUES ('streeteasy', ?, ?, ?, ?, ?, 'building', ?)
        ON CONFLICT DO NOTHING""",
        [source_id, captured_at, item.get("status"), item.get("asking_rent"),
         item.get("days_on_market"), raw],
    )
    event_count = 0
    for event in item["price_history"]:
        event_at = _event_datetime(event.get("date"))
        key_text = f"streeteasy|{source_id}|{event_at}|{event.get('event')}|{event.get('base_rent')}|{event.get('listing_url')}"
        event_key = hashlib.sha256(key_text.encode()).hexdigest()
        db.execute(
            """INSERT INTO listing_events VALUES (?, 'streeteasy', ?, ?, ?, ?, ?)
               ON CONFLICT DO NOTHING""",
            [event_key, source_id, event_at, event.get("event"),
             event.get("base_rent"), json.dumps(event)],
        )
        event_count += 1
    capture_id = hashlib.sha256(
        f"streeteasy|{source_id}|{item.get('captured_at')}".encode()
    ).hexdigest()
    manifest_path = path.parent / "manifest.json"
    assets_path = path.parent / "assets.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    db.execute(
        """INSERT INTO captures VALUES (?, 'streeteasy', ?, ?, ?, ?, ?, ?)
           ON CONFLICT (capture_id) DO UPDATE SET
             bundle_path=excluded.bundle_path, page_html_path=excluded.page_html_path,
             manifest_json=excluded.manifest_json, structured_json=excluded.structured_json""",
        [capture_id, source_id, item.get("captured_at"), str(path.parent),
         str(path.parent / "page.html") if (path.parent / "page.html").exists() else None,
         json.dumps(manifest), raw],
    )
    if assets_path.exists():
        for asset in json.loads(assets_path.read_text(encoding="utf-8")):
            asset_key = asset.get("sha256") or hashlib.sha256(asset["url"].encode()).hexdigest()
            local_path = str(path.parent / asset["local_file"]) if asset.get("local_file") else None
            db.execute(
                """INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (asset_key) DO UPDATE SET
                     source_url=excluded.source_url, category=excluded.category,
                     local_path=excluded.local_path, sha256=excluded.sha256,
                     bytes=excluded.bytes, metadata_json=excluded.metadata_json""",
                [asset_key, asset["url"], asset.get("category"), local_path,
                 asset.get("sha256"), asset.get("bytes"), json.dumps(asset)],
            )
            db.execute(
                "INSERT INTO capture_assets VALUES (?, ?) ON CONFLICT DO NOTHING",
                [capture_id, asset_key],
            )
    if owns_connection:
        db.close()
    return source_id, event_count
