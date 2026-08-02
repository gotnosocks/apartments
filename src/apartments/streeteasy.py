import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .db import connect
from .scope import normalize_address

EXCLUDED_UNITS_PATH = Path("config/excluded_units.json")
BUILDING_OVERRIDES_PATH = Path("config/building_overrides.json")


def building_override(building_slug: str | None) -> dict:
    if not BUILDING_OVERRIDES_PATH.exists():
        return {}
    return json.loads(BUILDING_OVERRIDES_PATH.read_text(encoding="utf-8")).get(
        building_slug or "", {}
    )


def floor_override(
    building_slug: str | None,
    unit: str | None,
    format_name: str,
) -> int | None:
    """Return a building-specific marketed floor without altering raw captures."""
    overrides = building_override(building_slug)
    by_unit = {key.upper(): value for key, value in overrides.get("floor_by_unit", {}).items()}
    if str(unit).upper() in by_unit:
        return int(by_unit[str(unit).upper()])
    by_format = overrides.get("floor_by_unit_format", {})
    value = by_format.get(format_name)
    return int(value) if value is not None else None


def physical_floor(marketed_floor: int | None, has_floor_13: bool | None) -> int | None:
    """Convert a marketed floor label to its physical elevation index."""
    if marketed_floor is None:
        return None
    if has_floor_13 is False and marketed_floor > 13:
        return marketed_floor - 1
    return marketed_floor


def unit_facing(
    building_slug: str | None,
    suffix: str | None,
) -> tuple[bool | None, bool | None]:
    """Return canonical (garden, street) exposure from a configured suffix split."""
    rule = building_override(building_slug).get("facing_suffix_split")
    value = (suffix or "").strip().upper()
    if not rule or len(value) != 1 or not value.isalpha():
        return None, None
    pivot = str(rule["pivot"]).upper()
    if value < pivot:
        faces = {str(rule["lower"]).lower()}
    elif value > pivot:
        faces = {str(rule["upper"]).lower()}
    else:
        faces = {str(face).lower() for face in rule.get("pivot_faces", [])}
    return "garden" in faces, "street" in faces


def unit_is_excluded(building_slug: str | None, unit: str | None) -> bool:
    if not EXCLUDED_UNITS_PATH.exists():
        return False
    exclusions = json.loads(EXCLUDED_UNITS_PATH.read_text(encoding="utf-8"))
    return str(unit).upper() in {key.upper() for key in exclusions.get(building_slug or "", {})}


def parse_price_history_html(html: str) -> list[dict]:
    """Parse both the older three-column and newer two-column history tables."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one('[data-testid="priceHistoryTable"]')
    if not table:
        return []
    events = []
    seen = set()
    for row in table.select("tbody tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue
        date_match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", cells[0].get_text(" ", strip=True))
        price_match = re.search(r"\$([\d,]+)", cells[1].get_text(" ", strip=True))
        if not date_match:
            continue
        if len(cells) >= 3:
            event = cells[2].get_text(" ", strip=True)
        else:
            paragraphs = [p.get_text(" ", strip=True) for p in cells[1].select("p") if not p.select_one("b")]
            event = " ".join(value for value in paragraphs if value and not re.fullmatch(r"\$[\d,]+", value))
        link = row.select_one('[data-testid="priceHistoryLink"], a[href]')
        parsed = {
            "date": date_match.group(0),
            "base_rent": int(price_match.group(1).replace(",", "")) if price_match else None,
            "event": event,
            "listing_url": link.get("href") if link else None,
        }
        key = tuple(parsed.values())
        if key not in seen:
            seen.add(key)
            events.append(parsed)
    return events


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
    format_name = item.get("unit_format") or unit_format(item.get("unit"))
    floor = item.get("floor") if item.get("floor") is not None else inferred_floor
    configured_floor = floor_override(item.get("building_slug"), item.get("unit"), format_name)
    if configured_floor is not None:
        floor = configured_floor
    override = building_override(item.get("building_slug"))
    has_floor_13 = override.get("has_floor_13")
    physical_floor_value = physical_floor(floor, has_floor_13)
    unit_letter = item.get("unit_letter") or inferred_letter
    suffix = item.get("unit_suffix") or unit_suffix(item.get("unit"))
    is_garden_facing, is_street_facing = unit_facing(item.get("building_slug"), suffix)
    floor_inference = (
        "building-override"
        if configured_floor is not None
        else item.get("floor_inference")
        or (
            "heuristic-first-digit" if format_name == "numeric" else
            "parsed-floor-letter" if format_name == "floor-letter" else None
        )
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
            source, source_id, canonical_address, borough, zipcode,
            has_floor_13, raw_json, updated_at
        ) VALUES ('streeteasy', ?, ?, 'Manhattan', ?, ?, ?, now())
        ON CONFLICT (source, source_id) DO UPDATE SET
            canonical_address=excluded.canonical_address, zipcode=excluded.zipcode,
            has_floor_13=excluded.has_floor_13,
            raw_json=excluded.raw_json, updated_at=now()""",
        [item.get("building_slug"), item.get("building_address"), item.get("zipcode"),
         has_floor_13, building_raw],
    )
    db.execute(
        """INSERT INTO listings (
            source, source_listing_id, address_line, canonical_address, unit,
            floor, physical_floor, unit_letter, unit_suffix, unit_format, floor_inference,
            unit_kind, unit_is_specific, is_furnished, is_garden_facing,
            is_street_facing, city, state, zipcode, property_type, bedrooms,
            bathrooms, square_feet, listing_type, raw_json
        ) VALUES ('streeteasy', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New York', 'NY', ?, 'Rental unit', ?, ?, ?, 'Rental', ?)
        ON CONFLICT (source, source_listing_id) DO UPDATE SET
            address_line=excluded.address_line, canonical_address=excluded.canonical_address,
            unit=excluded.unit, floor=excluded.floor, physical_floor=excluded.physical_floor,
            unit_letter=excluded.unit_letter,
            unit_suffix=excluded.unit_suffix, unit_format=excluded.unit_format,
            floor_inference=excluded.floor_inference, unit_kind=excluded.unit_kind,
            unit_is_specific=excluded.unit_is_specific,
            is_furnished=excluded.is_furnished,
            is_garden_facing=excluded.is_garden_facing,
            is_street_facing=excluded.is_street_facing,
            bedrooms=excluded.bedrooms, bathrooms=excluded.bathrooms,
            square_feet=excluded.square_feet, last_seen_at=now(),
            raw_json=excluded.raw_json""",
        [source_id, item.get("address"), normalize_address(item.get("address")),
         item.get("unit"), floor, physical_floor_value, unit_letter, suffix, format_name, floor_inference,
         kind, is_specific, is_furnished, is_garden_facing, is_street_facing,
         item.get("zipcode"), attributes.get("bedrooms"),
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


def reparse_capture_histories(
    root: Path,
    db_path: str = "data/apartments.duckdb",
) -> tuple[int, int]:
    """Replace structured history with rows reparsed from each latest rendered page."""
    latest: dict[str, tuple[str, Path, dict]] = {}
    for structured_path in root.rglob("structured.json"):
        if ":Zone.Identifier" in str(structured_path):
            continue
        item = json.loads(structured_path.read_text(encoding="utf-8"))
        source_id = item.get("source_listing_id")
        html_path = structured_path.parent / "page.html"
        if not source_id or not html_path.exists() or unit_is_excluded(item.get("building_slug"), item.get("unit")):
            continue
        captured_at = item.get("captured_at") or ""
        if source_id not in latest or captured_at > latest[source_id][0]:
            latest[source_id] = (captured_at, html_path, item)

    db = connect(db_path)
    units_reparsed = 0
    events_written = 0
    for source_id, (_, html_path, _) in sorted(latest.items()):
        events = parse_price_history_html(html_path.read_text(encoding="utf-8", errors="replace"))
        if not events:
            continue
        db.execute(
            "DELETE FROM listing_events WHERE source='streeteasy' AND source_listing_id=?",
            [source_id],
        )
        for event in events:
            event_at = _event_datetime(event.get("date"))
            event_type = event.get("event") or ""
            event_price = event.get("base_rent")
            key_text = f"streeteasy|{source_id}|{event_at}|{event_type}|{event_price}|{event.get('listing_url')}"
            event_key = hashlib.sha256(key_text.encode()).hexdigest()
            db.execute(
                """INSERT INTO listing_events VALUES (?, 'streeteasy', ?, ?, ?, ?, ?)
                   ON CONFLICT DO NOTHING""",
                [event_key, source_id, event_at, event_type, event_price, json.dumps(event)],
            )
        units_reparsed += 1
        events_written += len(events)
    db.close()
    return units_reparsed, events_written


def infer_furnishing_periods(
    db_path: str = "data/apartments.duckdb",
    building_slug: str = "the-sierra-chelsea",
) -> list[dict]:
    """Infer historical furnished eras from explicit Blueground listing events."""
    db = connect(db_path)
    db.execute(
        "DELETE FROM unit_furnishing_periods WHERE source='streeteasy' AND building_slug=?",
        [building_slug],
    )
    rows = db.execute(
        """SELECT l.unit, min(CAST(e.event_at AS DATE)) AS first_event,
                  min(CAST(e.event_at AS DATE)) FILTER (
                    WHERE lower(e.event_type) = 'listed by the blueground'
                  ) AS first_blueground
           FROM listings l
           JOIN listing_events e USING (source, source_listing_id)
           WHERE l.source='streeteasy' AND l.source_listing_id LIKE ?
             AND l.is_furnished
           GROUP BY l.unit ORDER BY l.unit""",
        [f"{building_slug}/%"],
    ).fetchall()
    periods = []

    def add(unit, start, end, status, confidence, evidence, operator=None):
        if not start or (end and end < start):
            return
        record = {
            "unit": unit, "starts_on": start, "ends_on": end,
            "furnishing_status": status, "operator": operator,
            "confidence": confidence, "evidence": evidence,
        }
        periods.append(record)
        db.execute(
            """INSERT INTO unit_furnishing_periods VALUES
               ('streeteasy', ?, ?, ?, ?, ?, ?, ?, ?, now())""",
            [building_slug, unit, start, end, status, operator, confidence, evidence],
        )

    for unit, first_event, first_blueground in rows:
        if not first_blueground:
            continue
        prior_rented = db.execute(
            """SELECT max(CAST(e.event_at AS DATE))
               FROM listing_events e JOIN listings l USING (source, source_listing_id)
               WHERE l.source='streeteasy' AND l.source_listing_id=?
                 AND CAST(e.event_at AS DATE) < ?
                 AND lower(e.event_type) LIKE 'rented by %'
                 AND lower(e.event_type) NOT LIKE '%blueground%'""",
            [f"{building_slug}/{unit.lower()}", first_blueground],
        ).fetchone()[0]
        if first_event < first_blueground:
            likely_end = prior_rented or (first_blueground - timedelta(days=1))
            add(
                unit, first_event, likely_end, "likely-unfurnished", 0.8,
                "Pre-Blueground history is attributed to conventional building managers or brokers.",
            )
            if prior_rented and prior_rented + timedelta(days=1) < first_blueground:
                add(
                    unit, prior_rented + timedelta(days=1), first_blueground - timedelta(days=1),
                    "unknown-transition", 0.4,
                    "After a non-Blueground rented event but before the first explicit Blueground listing.",
                )
        add(
            unit, first_blueground, None, "confirmed-furnished", 0.95,
            "First explicit 'Listed by The Blueground' event; current page says Furnished and advertises flexible stays.",
            "The Blueground",
        )
    db.close()
    return periods
