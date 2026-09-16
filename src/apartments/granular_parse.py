"""Parse one StreetEasy listing capture into lossless granular observations."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit

from streeteasy_archive.extract import _scripts, _selector, flight_text


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _flight_candidates(scripts):
    """Find listing objects while resolving only references on candidate paths."""
    stream = flight_text(scripts)
    records = {}
    decoder = json.JSONDecoder()
    for match in re.finditer(r"(?<![A-Za-z0-9_])([0-9a-f]+):(?=[{\[])", stream):
        try:
            records[match.group(1)], _ = decoder.raw_decode(stream[match.end():])
        except ValueError:
            continue

    memo = {}

    def resolve(value, stack=()):
        if isinstance(value, str) and value.startswith("$") and value[1:] in records:
            key = value[1:]
            if key in stack:
                return value
            if key not in memo:
                memo[key] = resolve(records[key], stack + (key,))
            return memo[key]
        if isinstance(value, list):
            return [resolve(x, stack) for x in value]
        if isinstance(value, dict):
            return {k: resolve(v, stack) for k, v in value.items()}
        return value

    result = []
    seen = set()

    def find(value, stack=()):
        if isinstance(value, str) and value.startswith("$") and value[1:] in records:
            key = value[1:]
            if key not in stack:
                find(records[key], stack + (key,))
            return
        if isinstance(value, dict):
            if isinstance(value.get("propertyDetails"), dict):
                candidate = resolve(value)
                marker = _json(candidate)
                if marker not in seen:
                    seen.add(marker)
                    result.append(candidate)
                return
            for child in value.values():
                find(child, stack)
        elif isinstance(value, list):
            for child in value:
                find(child, stack)

    for record in records.values():
        find(record)
    return result


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        return float(match.group()) if match else None
    return None


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if value is not None else None


def _listing_candidates(scripts):
    values = []
    for script in scripts:
        values.extend(_walk(script.get("json")))
    values.extend(_flight_candidates(scripts))
    # Keep object identity while avoiding duplicate inline/Flight copies.
    seen, result = set(), []
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("propertyDetails"), dict):
            continue
        marker = _json(value)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return result


def _event_key(listing_id, event_listing_id, category, episode_index, event_index, event):
    # Semantic identity intentionally excludes capture listing_id and position;
    # those belong to occurrence_key below and may change between page captures.
    payload = {"event_listing_id": event_listing_id, "category": category, "event": event}
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _occurrence_key(event_key, episode_index, event_index):
    return hashlib.sha256(f"{event_key}:{episode_index}:{event_index}".encode()).hexdigest()


def parse_listing(body: bytes, url: str) -> tuple[dict, list[dict]]:
    """Parse a listing page, retaining every rental and sale history occurrence."""
    scripts = _scripts(_selector(body))
    candidates = _listing_candidates(scripts)
    path = urlsplit(url).path
    requested_type = "sale" if re.search(r"/(?:sale|sales)/", path) else "rental"
    requested_match = re.search(r"/(?:rental|sale)/(\d+)(?:[-/]|$)", path)
    requested_id = requested_match.group(1) if requested_match else None
    matching = [x for x in candidates if requested_id is None or str(x.get("id")) == requested_id]
    if requested_id is not None and not matching:
        return ({"url": url, "listing_id": requested_id, "listing_type": requested_type, "building_slug": None,
                 "unit_label": None, "bedrooms": None, "bathrooms": None, "square_feet": None,
                 "room_count": None, "source_created_at": None, "features_json": None,
                 "amenities_json": None, "pricing_json": None, "raw_listing_json": None,
                 "parse_status": "failed", "error": "listing object id does not match requested URL"}, [])
    candidates = matching or candidates
    listing = max(candidates, key=lambda x: int(isinstance(x.get("propertyHistory"), list) and bool(x.get("propertyHistory")))) if candidates else None
    if listing is None:
        return ({"url": url, "listing_id": None, "listing_type": requested_type, "building_slug": None,
                 "unit_label": None, "bedrooms": None, "bathrooms": None, "square_feet": None,
                 "room_count": None, "source_created_at": None, "features_json": None,
                 "amenities_json": None, "pricing_json": None, "raw_listing_json": None,
                 "parse_status": "failed", "error": "listing object not found"}, [])

    details = listing.get("propertyDetails") or {}
    address = details.get("address") or {}
    listing_id = str(listing.get("id")) if listing.get("id") is not None else None
    history = listing.get("propertyHistory")
    history_complete = isinstance(history, list) and bool(history)
    errors = []
    full_candidates = [x for x in candidates if isinstance(x.get("propertyHistory"), list) and x.get("propertyHistory")]
    if len({_json(x) for x in full_candidates}) > 1:
        errors.append("conflicting history-bearing listing objects")
    if not history_complete:
        errors.append("propertyHistory missing or unresolved")
        history = []
    building_slug = None
    address_link = _selector(body).css('[data-testid="addressLink"]::attr(href)').get()
    for candidate in (address_link, address.get("url"), address.get("buildingUrl"), url):
        match = re.search(r"/building/([^/?#]+)", str(candidate or ""))
        if match:
            building_slug = match.group(1)
            break
    unit_label = _clean(address.get("displayUnit")) or None
    if not unit_label:
        unit_node = _selector(body).css('[data-testid="address"]')
        unit_match = re.search(r"#\s*([^,]+)$", _clean(unit_node.xpath("string(.)").get() if unit_node else ""))
        unit_label = _clean(unit_match.group(1)) if unit_match else None
    full = _number(details.get("fullBathroomCount"))
    half = _number(details.get("halfBathroomCount"))
    bathrooms = ((full or 0) + (half or 0) * 0.5
                 if full is not None or half is not None else _number(details.get("bathroomCount")))
    listing_type = requested_type
    if any(isinstance(ep, dict) and ep.get("saleEventsOfInterest") for ep in history):
        if not any(isinstance(ep, dict) and ep.get("rentalEventsOfInterest") for ep in history):
            listing_type = "sale"
    row = {
        "url": url, "listing_id": listing_id, "listing_type": listing_type, "building_slug": building_slug,
        "unit_label": unit_label, "bedrooms": _number(details.get("bedroomCount")),
        "bathrooms": bathrooms, "square_feet": _number(details.get("livingAreaSize")),
        "room_count": _number(details.get("roomCount")),
        "source_created_at": listing.get("createdAt") or listing.get("created_at"),
        "source_updated_at": listing.get("updatedAt") or listing.get("updated_at"),
        "features_json": _json((details.get("features") or {}).get("list") or details.get("features")),
        "amenities_json": _json((details.get("amenities") or {}).get("list") or details.get("amenities")),
        "pricing_json": _json(listing.get("pricing") if listing.get("pricing") is not None else
                                {k: listing.get(k) for k in ("price", "pricePerSquareFoot", "fee", "taxes") if k in listing}),
        "raw_listing_json": _json(listing), "parse_status": "ok" if history_complete and not errors else "partial",
        "error": "; ".join(errors) or None,
    }
    events = []
    for episode_index, episode in enumerate(history):
        if not isinstance(episode, dict):
            row["parse_status"], row["error"] = "partial", "invalid history episode"
            continue
        episode_id = episode.get("listingId") or episode.get("id")
        event_listing_id = str(episode_id) if episode_id is not None else listing_id
        for category, key in (("rental", "rentalEventsOfInterest"), ("sale", "saleEventsOfInterest")):
            source_events = episode.get(key)
            if source_events is None:
                continue
            if not isinstance(source_events, list):
                row["parse_status"], row["error"] = "partial", f"unresolved {key}"
                continue
            for event_index, event in enumerate(source_events):
                if not isinstance(event, dict):
                    row["parse_status"], row["error"] = "partial", "invalid history event"
                    continue
                events.append({"episode_index": episode_index, "event_index": event_index,
                               "listing_id": listing_id, "event_listing_id": event_listing_id,
                               "event_category": category, "event_date": event.get("date"),
                               "price": _number(event.get("price")), "status": event.get("status"),
                               "percent_change": _number(event.get("pricePercentChange")),
                               "event_json": _json(event),
                               "event_key": _event_key(listing_id, event_listing_id, category, episode_index, event_index, event)})
                events[-1]["occurrence_key"] = _occurrence_key(events[-1]["event_key"], episode_index, event_index)
    return row, events
