"""Conservative identity and full-detail evidence for explicit listing-ID routes."""

import json
import re
from urllib.parse import urlsplit

from .extract import canonical_url, flight_text


def listing_key(url):
    normalized = canonical_url(url)
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    if parsed.query:
        return None  # Unknown capture intent must stay independent.
    match = re.fullmatch(
        r"/(?:building/[^/]+/)?(rental|sale)/([1-9][0-9]*)", parsed.path
    )
    return ":".join((*match.groups(), "detail")) if match else None


def capture_evidence(data, url):
    """Return reuse evidence only for an identified detail with inline history.

    This checks the saved payload, not just HTTP success or rel=canonical. A
    missing/reference-only/partial history fails closed: fetch the other route.
    It does not claim to prove StreetEasy has exposed every historical event.
    """
    key = listing_key(url)
    if not key or not isinstance(data, dict):
        return None
    category, identifier, intent = key.split(":")
    event_key = category + "EventsOfInterest"
    candidates = []

    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k == "listing" and isinstance(v, dict):
                    candidates.append(v)
                else:
                    walk(v)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    scripts = data.get("scripts", [])
    for script in scripts:
        walk(script.get("json"))
    stream = flight_text(scripts)
    for match in re.finditer(r'"listing"\s*:', stream):
        try:
            value, _ = json.JSONDecoder().raw_decode(stream[match.end() :].lstrip())
        except ValueError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    identified = [x for x in candidates if isinstance(x.get("propertyDetails"), dict)]
    if not identified or any(str(x.get("id")) != identifier for x in identified):
        return None
    # Hydration also embeds compact copies of this same listing without history.
    # They do not invalidate the complete history-bearing representation.
    identified = [x for x in identified if "propertyHistory" in x]
    if not identified:
        return None
    for listing in identified:
        address = listing["propertyDetails"].get("address")
        history = listing.get("propertyHistory")
        if (
            not isinstance(address, dict)
            or not address.get("street")
            or not isinstance(history, list)
            or not history
        ):
            return None
        event_count = 0
        for episode in history:
            if (
                not isinstance(episode, dict)
                or not str(episode.get("listingId", "")).isdigit()
            ):
                return None
            events = episode.get(event_key)
            if not isinstance(events, list) or not events:
                return None
            if any(
                not isinstance(event, dict)
                or not re.match(r"^\d{4}-\d{2}-\d{2}", str(event.get("date", "")))
                or "price" not in event
                for event in events
            ):
                return None
            event_count += len(events)
    return {
        "listing_key": key,
        "history_episodes": len(history),
        "history_events": event_count,
        "validation": "inline-identified-listing-history-v1",
    }
