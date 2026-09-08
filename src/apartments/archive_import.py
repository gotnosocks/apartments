"""Import normalized listing history from a live StreetEasy Archive."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

from .db import connect
from .streeteasy import ingest_item


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _money(value: str | None) -> int | None:
    match = re.search(r"\$([\d,]+)", _clean(value))
    return int(match.group(1).replace(",", "")) if match else None


def _number(value: str, pattern: str) -> float | None:
    match = re.search(pattern, value, re.I)
    return float(match.group(1).replace(",", "")) if match else None


def _flight_text(soup: BeautifulSoup) -> str:
    chunks: list[str] = []
    decoder = json.JSONDecoder()
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        for match in re.finditer(r"self\.__next_f\.push\(", text):
            try:
                value, _ = decoder.raw_decode(text[match.end():])
            except ValueError:
                continue
            if isinstance(value, list) and len(value) > 1 and value[0] == 1 and isinstance(value[1], str):
                chunks.append(value[1])
    return "".join(chunks)


def _embedded_listing(soup: BeautifulSoup) -> dict:
    stream = _flight_text(soup)
    decoder = json.JSONDecoder()
    for match in re.finditer(r'"listing"\s*:', stream):
        try:
            value, _ = decoder.raw_decode(stream[match.end():].lstrip())
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("propertyDetails"), dict):
            return value
    return {}


def _event_label(event: dict, source: str | None) -> str:
    status = str(event.get("status") or "").upper()
    if status == "ACTIVE":
        return f"Listed by {source}" if source else "Listed"
    if status == "NO_LONGER_AVAILABLE":
        return "No longer available"
    if status == "IN_CONTRACT":
        return "In contract"
    if status == "RENTED":
        return f"Rented by {source}" if source else "Rented"
    change = event.get("pricePercentChange")
    if isinstance(change, (int, float)):
        direction = "increased" if change > 0 else "decreased"
        amount = abs(change)
        display = "<1" if 0 < amount < 1 else f"{amount:.0f}"
        return f"Price {direction} by {display}%"
    return status.replace("_", " ").title() if status else "Price recorded"


def normalize_listing(body: bytes, url: str, observed: float) -> dict | None:
    """Convert one archived page into the analysis project's stable capture shape."""
    soup = BeautifulSoup(body, "html.parser")
    listing = _embedded_listing(soup)
    details = listing.get("propertyDetails", {})
    address_data = details.get("address", {})

    address_node = soup.select_one('[data-testid="address"]')
    address_with_unit = _clean(address_node.get_text(" ") if address_node else "")
    unit = _clean(str(address_data.get("displayUnit") or "")).removeprefix("#")
    if not unit:
        match = re.search(r"#\s*(.+)$", address_with_unit)
        unit = _clean(match.group(1)) if match else ""

    building_link = soup.select_one('[data-testid="addressLink"]')
    building_href = building_link.get("href") if building_link else None
    building_match = re.search(r"/building/([^/?#]+)", building_href or url)
    if not listing or not unit or not building_match:
        return None
    building_slug = building_match.group(1)
    address = _clean(str(address_data.get("street") or ""))
    if not address:
        address = _clean(re.sub(r"\s*#\s*.+$", "", address_with_unit))

    property_history = listing.get("propertyHistory") or []
    path = urlparse(url).path
    price_node = soup.select_one('[data-testid="priceInfo"]')
    price_text = _clean(price_node.get_text(" ") if price_node else "")
    has_rental_history = any("rentalEventsOfInterest" in value for value in property_history)
    has_sale_history = any("saleEventsOfInterest" in value for value in property_history)
    if (
        path.startswith("/sale/")
        or (has_sale_history and not has_rental_history)
        or (not has_rental_history and path.startswith("/building/") and "for rent" not in price_text.lower())
    ):
        return None

    history = []
    for historical_listing in property_history:
        source = historical_listing.get("sourceGroupLabel")
        listing_id = historical_listing.get("listingId")
        for event in historical_listing.get("rentalEventsOfInterest") or []:
            history.append({
                "date": event.get("date"),
                "base_rent": event.get("price"),
                "event": _event_label(event, source),
                "listing_url": f"https://streeteasy.com/rental/{listing_id}" if listing_id else None,
                "archive_event": event,
                "source_group": source,
            })

    # Older captures may lack embedded history, but their rendered table is still useful.
    if not history:
        from .streeteasy import parse_price_history_html

        history = parse_price_history_html(str(soup))

    spec_text = _clean(soup.select_one('[data-testid="propertyDetails"]').get_text(" ")) if soup.select_one('[data-testid="propertyDetails"]') else ""
    full_baths = details.get("fullBathroomCount")
    half_baths = details.get("halfBathroomCount")
    bathrooms = None
    if isinstance(full_baths, (int, float)) or isinstance(half_baths, (int, float)):
        bathrooms = (full_baths or 0) + (half_baths or 0) * 0.5
    canonical = soup.select_one('link[rel="canonical"]')
    canonical_url = canonical.get("href") if canonical else url
    rental_match = re.search(r"/(?:rental/)(\d+)", urlparse(canonical_url).path)
    features = (details.get("features") or {}).get("list") or []
    amenities = (details.get("amenities") or {}).get("list") or []

    return {
        "schema_version": 4,
        "source": "streeteasy",
        "captured_at": datetime.fromtimestamp(observed, UTC).isoformat(),
        "canonical_url": canonical_url,
        "source_listing_id": f"{building_slug}/{unit.replace(' ', '').replace('-', '').lower()}",
        "street_easy_rental_id": rental_match.group(1) if rental_match else listing.get("id"),
        "building_slug": building_slug,
        "unit": unit,
        "address": address,
        "building_address": ", ".join(filter(None, [address, str(address_data.get("city") or "").title(), address_data.get("state"), address_data.get("zipCode")])),
        "zipcode": address_data.get("zipCode"),
        "asking_rent": listing.get("price") or _money(price_node.get_text(" ") if price_node else ""),
        "status": listing.get("status"),
        "days_on_market": listing.get("daysOnMarket"),
        "attributes": {
            "square_feet": details.get("livingAreaSize") or _number(spec_text, r"([\d,]+)\s*ft²"),
            "bedrooms": details.get("bedroomCount") if details.get("bedroomCount") is not None else (0 if re.search(r"\bstudio\b", spec_text, re.I) else _number(spec_text, r"([\d.]+)\s*(?:bed|bedroom)")),
            "bathrooms": bathrooms if bathrooms is not None else _number(spec_text, r"([\d.]+)\s*bath"),
            "rooms": details.get("roomCount"),
        },
        "home_features": features,
        "building_amenities": amenities,
        "description": listing.get("description"),
        "price_history": history,
        "archive_listing": listing,
    }


def import_archive(
    archive_root: Path,
    db_path: Path | str = "data/apartments.duckdb",
    limit: int = 0,
) -> dict[str, int]:
    """Import new listing snapshots from a live archive without locking its writer."""
    archive_root = archive_root.expanduser().resolve()
    sqlite_path = archive_root / "archive.sqlite3"
    if not sqlite_path.exists():
        raise FileNotFoundError(f"StreetEasy archive database not found: {sqlite_path}")
    source = sqlite3.connect(f"file:{quote(str(sqlite_path))}?mode=ro", uri=True, timeout=30)
    rows = source.execute(
        """SELECT s.id,s.url,s.observed,s.body_hash,b.path
           FROM snapshots s
           JOIN bodies b ON b.hash=s.body_hash
           JOIN frontier f ON f.generation=s.generation AND f.url=s.url
           WHERE f.kind='listing'
           ORDER BY s.id"""
    )
    target = connect(db_path)
    known = {row[0] for row in target.execute(
        "SELECT capture_id FROM captures WHERE json_extract_string(manifest_json, '$.source')='streeteasy-archive'"
    ).fetchall()}
    counts = {"examined": 0, "imported": 0, "skipped": 0, "unrecognized": 0, "failed": 0, "events": 0}
    target.execute("""CREATE TABLE IF NOT EXISTS archive_imports (
        capture_id VARCHAR PRIMARY KEY, outcome VARCHAR NOT NULL,
        imported_at TIMESTAMPTZ DEFAULT current_timestamp
    )""")
    known.update(row[0] for row in target.execute("SELECT capture_id FROM archive_imports").fetchall())
    try:
        for snapshot_id, url, observed, body_hash, relative_path in rows:
            capture_id = hashlib.sha256(f"streeteasy-archive|{snapshot_id}|{url}|{body_hash}".encode()).hexdigest()
            counts["examined"] += 1
            if capture_id in known:
                counts["skipped"] += 1
                continue
            target.execute("BEGIN TRANSACTION")
            try:
                body_path = (archive_root / relative_path).resolve()
                if not body_path.is_relative_to(archive_root):
                    raise ValueError("Archived body path escapes archive directory")
                with gzip.open(body_path, "rb") as stream:
                    item = normalize_listing(stream.read(), url, observed)
                event_count = 0
                if item is not None:
                    _, event_count = ingest_item(
                        item, str(db_path), connection=target,
                        bundle_path=archive_root, page_html_path=body_path,
                        manifest={"source": "streeteasy-archive", "snapshot_id": snapshot_id,
                                  "url": url, "body_hash": body_hash},
                        capture_id=capture_id,
                    )
                target.execute("INSERT INTO archive_imports(capture_id,outcome) VALUES (?,?)",
                               [capture_id, "rental" if item is not None else "not_rental"])
                target.execute("COMMIT")
                counts["imported" if item is not None else "unrecognized"] += 1
                counts["events"] += event_count
                known.add(capture_id)
            except Exception as error:
                target.execute("ROLLBACK")
                counts["failed"] += 1
                print(f"Import failed for snapshot {snapshot_id} ({url}): {error}", file=sys.stderr)
            if limit and counts["imported"] >= limit:
                break
    finally:
        source.close()
        target.close()
    return counts
