"""Parse rental ads and buildings read from StreetEasy's public GraphQL API.

The area collector (streeteasy_archive.graphql_search) reads up to 500 ads per request with
`rentalsByListingIds` on api-v6.streeteasy.com. It stores each ad as a JSON body of its own:

    {"source": "rentalsByListingIds", "fields": FIELDS_VERSION, "listing_id": "5167317",
     "building": {"id": "17503", "slug": "the-strand-500-west-43-street-new_york",
                  "page": "https://streeteasy.com/building/the-strand-500-west-43-street-new_york"},
     "record": {...}}

The record is the ad's `RentalListing`, the object an ad page carries in its Flight data.
parse_listing_json turns the body into the row and events granular_parse.parse_listing gives
for the ad's page:
  1. It drops `__typename` and writes integral floats as integers, as the page's JavaScript
     serializer does (-6 where the API writes -6.0). Events then serialize byte for byte as
     the page's do, so event keys match.
  2. The page's canonical link is `/building/{building slug}/{record slug}`. The collector
     reads the building's slug through `buildingsByIds` and stores it in the body, and the
     parser rebuilds the link from it. On Midtown West's archived pages the rebuilt link
     matched the page's on 2,493 ads and on the latest ads of 500 unit pages
     (data/probes/graphql-rental-20261015/).
  3. The row's other fields come from the record by granular_parse's own rules.

The record leaves out a few page fields: `listingAddress`, `saleType` (null on rentals), the
open houses' `showingNotes`, and in each history episode `advertisedOnSe`, `closingId`,
`soldDate` and `saleEventsOfInterest` (rentals have no sale events). No code reads them. It
adds `propertyId` and each episode's `offMarketAt`. docs/data/graphql-collection.md compares
the record with the ad page in more detail.

parse_capture takes any listing capture, API or page, and sends it to the matching parser.

Buildings come from `buildingsByIds` and are stored the same way, under
`"source": "buildingsByIds"` with the building's record. export_building hands the export
that record with the latitude and longitude the API nests under `geoCenter` copied to the
top level, where the page has them. The rest keeps the API's layout: `nearby`, for instance,
lists colleges, museums and parks together under `pointsOfInterest`, each with its type.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from apartments import granular_parse
from apartments.granular_parse import (
    _clean,
    _event_key,
    _json,
    _number,
    _occurrence_key,
)
from apartments.unit_canonical import unit_page

SOURCE = "rentalsByListingIds"
FIELDS_VERSION = "rental-listing-fields-v1"
BUILDING_SOURCE = "buildingsByIds"
BUILDING_FIELDS_VERSION = "building-fields-v2"


def normalize(value):
    """The record as the page serializes it: no `__typename`, integral floats as ints."""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k != "__typename"}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def listing_body(listing_id, building, record):
    """The stored body for one ad. An unchanged record gives the same bytes on each read."""
    return json.dumps(
        {
            "source": SOURCE,
            "fields": FIELDS_VERSION,
            "listing_id": str(listing_id),
            "building": building,
            "record": record,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _document(body, source):
    if isinstance(body, str):
        body = body.encode()
    if not isinstance(body, bytes) or body.lstrip()[:1] != b"{":
        return None
    try:
        doc = json.loads(body)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) and doc.get("source") == source else None


def api_document(body):
    """The parsed body when it is an API ad body, else None."""
    return _document(body, SOURCE)


def building_body(building_id, record):
    """The stored body for one building. An unchanged record gives the same bytes."""
    return json.dumps(
        {
            "source": BUILDING_SOURCE,
            "fields": BUILDING_FIELDS_VERSION,
            "building_id": str(building_id),
            "record": record,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def building_document(body):
    """The parsed body when it is an API building body, else None."""
    return _document(body, BUILDING_SOURCE)


def export_building(data):
    """The building object of an API building capture's extracted data, else None."""
    doc = data.get("json") if isinstance(data, dict) else None
    if (
        not isinstance(doc, dict)
        or doc.get("source") != BUILDING_SOURCE
        or not isinstance(doc.get("record"), dict)
    ):
        return None
    record = normalize(doc["record"])
    center = (
        record.get("geoCenter") if isinstance(record.get("geoCenter"), dict) else {}
    )
    return {
        **record,
        "latitude": center.get("latitude"),
        "longitude": center.get("longitude"),
    }


def canonical_link(building, record):
    """The unit page the ad's page names in its canonical link."""
    slug = building.get("slug") if isinstance(building, dict) else None
    unit = record.get("slug") if isinstance(record, dict) else None
    if not isinstance(slug, str) or not slug or not isinstance(unit, str) or not unit:
        return None
    return f"https://streeteasy.com/building/{slug}/{unit}"


def _canonical_fields(doc, record, url):
    href = canonical_link(doc.get("building"), record)
    building_id = (doc.get("building") or {}).get("id")
    error = None
    if href is None:
        error = "API record has no building slug or unit slug"
    elif str(record.get("buildingId")) != str(building_id):
        href, error = None, "API record's buildingId differs from the stored building"
    normalized = unit_page(href, url) if href else None
    if href and not normalized:
        error = "Canonical link is not a unit page"
    return {
        "canonical_href": href,
        "canonical_unit_url": normalized,
        "canonical_unit_error": error,
    }


def _failed(url, listing_id, error, canonical=None):
    return (
        {
            **(
                canonical
                or {
                    "canonical_href": None,
                    "canonical_unit_url": None,
                    "canonical_unit_error": error,
                }
            ),
            "url": url,
            "listing_id": listing_id,
            "listing_type": "rental",
            "building_slug": None,
            "unit_label": None,
            "bedrooms": None,
            "bathrooms": None,
            "square_feet": None,
            "room_count": None,
            "source_created_at": None,
            "features_json": None,
            "amenities_json": None,
            "pricing_json": None,
            "raw_listing_json": None,
            "parse_status": "failed",
            "error": error,
        },
        [],
    )


def parse_listing_json(body, url):
    """Parse an API ad body into granular_parse.parse_listing's row and events."""
    return _parse(api_document(body), url)


def _parse(doc, url):
    match = re.search(r"/rental/(\d+)(?:[-/]|$)", urlsplit(url).path)
    requested_id = match.group(1) if match else None
    if doc is None:
        return _failed(url, requested_id, "not a rentalsByListingIds body")
    record = doc.get("record")
    if not isinstance(record, dict) or not isinstance(
        record.get("propertyDetails"), dict
    ):
        return _failed(url, requested_id, "listing object not found")
    listing = normalize(record)
    listing_id = str(listing.get("id")) if listing.get("id") is not None else None
    canonical = _canonical_fields(doc, listing, url)
    if requested_id is not None and listing_id != requested_id:
        return _failed(
            url,
            requested_id,
            "listing object id does not match requested URL",
            canonical,
        )
    details = listing.get("propertyDetails") or {}
    address = details.get("address") or {}
    history = listing.get("propertyHistory")
    errors = []
    if not (isinstance(history, list) and history):
        errors.append("propertyHistory missing or unresolved")
        history = []
    building = doc.get("building") or {}
    full = _number(details.get("fullBathroomCount"))
    half = _number(details.get("halfBathroomCount"))
    bathrooms = (
        (full or 0) + (half or 0) * 0.5
        if full is not None or half is not None
        else _number(details.get("bathroomCount"))
    )
    row = {
        **canonical,
        "url": url,
        "listing_id": listing_id,
        "listing_type": "rental",
        "building_slug": building.get("slug") or None,
        "unit_label": _clean(address.get("displayUnit")) or None,
        "bedrooms": _number(details.get("bedroomCount")),
        "bathrooms": bathrooms,
        "square_feet": _number(details.get("livingAreaSize")),
        "room_count": _number(details.get("roomCount")),
        "source_created_at": listing.get("createdAt") or listing.get("created_at"),
        "source_updated_at": listing.get("updatedAt") or listing.get("updated_at"),
        "features_json": _json(
            (details.get("features") or {}).get("list") or details.get("features")
        ),
        "amenities_json": _json(
            (details.get("amenities") or {}).get("list") or details.get("amenities")
        ),
        "pricing_json": _json(
            listing.get("pricing")
            if listing.get("pricing") is not None
            else {
                k: listing.get(k)
                for k in ("price", "pricePerSquareFoot", "fee", "taxes")
                if k in listing
            }
        ),
        "raw_listing_json": _json(listing),
        "parse_status": "partial" if errors else "ok",
        "error": "; ".join(errors) or None,
    }
    events = []
    for episode_index, episode in enumerate(history):
        if not isinstance(episode, dict):
            row["parse_status"], row["error"] = "partial", "invalid history episode"
            continue
        episode_id = episode.get("listingId") or episode.get("id")
        event_listing_id = str(episode_id) if episode_id is not None else listing_id
        source_events = episode.get("rentalEventsOfInterest")
        if source_events is None:
            continue
        if not isinstance(source_events, list):
            row["parse_status"] = "partial"
            row["error"] = "unresolved rentalEventsOfInterest"
            continue
        for event_index, event in enumerate(source_events):
            if not isinstance(event, dict):
                row["parse_status"], row["error"] = "partial", "invalid history event"
                continue
            key = _event_key(
                listing_id,
                event_listing_id,
                "rental",
                episode_index,
                event_index,
                event,
            )
            events.append(
                {
                    "episode_index": episode_index,
                    "event_index": event_index,
                    "listing_id": listing_id,
                    "event_listing_id": event_listing_id,
                    "event_category": "rental",
                    "event_date": event.get("date"),
                    "price": _number(event.get("price")),
                    "status": event.get("status"),
                    "percent_change": _number(event.get("pricePercentChange")),
                    "event_json": _json(event),
                    "event_key": key,
                    "occurrence_key": _occurrence_key(key, episode_index, event_index),
                }
            )
    return row, events


def parse_capture(body, url):
    """Parse a listing capture with the parser for its kind of body.

    granular_parse.parse_listing is looked up on each call, so parse_once's memo and test
    patches of it still apply to page captures.
    """
    doc = api_document(body)
    if doc is not None:
        return _parse(doc, url)
    return granular_parse.parse_listing(body, url)
