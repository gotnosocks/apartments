"""Each API record's attributes and rental flags, as the current chain reads them, with the
elevator and the pet policy its description states.

The current chain parses each stored answer with `apartments.graphql_listing` into a capture,
and `apartments.historical_dataset.project_advertisement` then reads each capture of an ad. For
a record of the export, `project` repeats both steps:

1. It drops `__typename` keys and turns integral floats into ints, as `graphql_listing.normalize`
   does, and it reads the bedroom, bathroom and size counts as `graphql_listing` reads them.
   The page parser retires with the move to API records, so this module keeps its own copy of
   those few lines instead of importing them.
2. It calls `attribute_evidence.extract_attribute_evidence` on the record, adds the evidence's
   attributes to the three counts and blanks the attributes with conflicting evidence, as
   `project_advertisement` does.
3. It calls `analytical.attributes` and `analytical._rental_flags`, and it marks the ad
   furnished when the flag is unknown and `historical_dataset._description_furnished` finds a
   furnished phrase in the description.
4. It reads the description with `steps.adtext`, as the chain's rules `elevator-from-ad-v1` and
   `pets-from-ad-v2` read a row's description, into `elevator_text` and `pet_policy_text`.
   `ads.attributes` merges these readings over an ad's records and fills an unknown elevator
   or pet policy from them, as those rules fill a row's.

The projection depends on the record alone. The ask comes from the ad's events. For API
records the chain runs no description recovery, and its ledger of corrections is empty.
`project` returns each known value as canonical JSON and each unknown one as None.
`project_advertisement` compares an ad's captures in canonical JSON as well.

The chain gives a record a capture without values when its `propertyDetails` is not an object
or its `id` differs from the requested ad. `project` also returns the record's `id`. With it,
`ads.attributes` leaves out records of other ads.
"""

import json
import re

from apartments import analytical
from apartments.attribute_evidence import extract_attribute_evidence
from apartments.corrections import canonical
from apartments.historical_dataset import _description_furnished
from steps import adtext

FLAGS = ("furnished", "short_term", "concession")
TEXT = ("elevator_text", "pet_policy_text")
KEYS = analytical.ATTRIBUTE_KEYS + FLAGS + TEXT


def normalize(value):
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k != "__typename"}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def number(value):
    """A count as `granular_parse._number` reads it, with the first number of a string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        return float(match.group()) if match else None
    return None


def codes(details, key):
    value = (details.get(key) or {}).get("list") or details.get(key)
    return [] if value is None else value


def project(record):
    """The record's id and a dict of canonical-JSON values for KEYS, from its JSON text."""
    listing = normalize(json.loads(record))
    details = listing.get("propertyDetails")
    record_id = None if listing.get("id") is None else str(listing["id"])
    if not isinstance(details, dict):
        return record_id, None
    full = number(details.get("fullBathroomCount"))
    half = number(details.get("halfBathroomCount"))
    attrs = {
        "bedrooms": number(details.get("bedroomCount")),
        "bathrooms": (full or 0) + (half or 0) * 0.5
        if full is not None or half is not None
        else number(details.get("bathroomCount")),
        "square_feet": number(details.get("livingAreaSize")),
    }
    evidence = extract_attribute_evidence(listing)
    attrs.update(
        {
            k: v
            for k, v in evidence["attributes"].items()
            if v is not None and k not in attrs
        }
    )
    for key in evidence.get("conflicts", {}):
        attrs[key] = None
    raw = {
        "attributes": attrs,
        "home_features": codes(details, "features"),
        "building_amenities": codes(details, "amenities"),
        "archive_listing": listing,
    }
    values = analytical.attributes(raw)
    flags = analytical._rental_flags(raw)
    description = str(listing.get("description") or "").lower()
    if flags["furnished"] is None and _description_furnished(description):
        flags["furnished"] = True
    values.update(flags)
    values["elevator_text"] = adtext.elevator(description)
    values["pet_policy_text"] = adtext.pets(description)
    return record_id, {
        key: None if values[key] is None else canonical(values[key]) for key in KEYS
    }


def project_batch(records):
    """Rows of (record_sha256, id, parsed, *values) for (record_sha256, record) pairs."""
    rows = []
    for sha256, record in records:
        record_id, values = project(record)
        if values is None:
            rows.append((sha256, record_id, False, *(None for _ in KEYS)))
        else:
            rows.append((sha256, record_id, True, *(values[key] for key in KEYS)))
    return rows
