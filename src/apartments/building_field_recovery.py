"""Recover selected building fields from exact archived Flight records, offline.

This returns literal source data, not inferred elevator status. Missing and null
amenities must never be interpreted as a claim that a building has no elevator.
"""
import hashlib
import json
import re

from streeteasy_archive.extract import _scripts, _selector, flight_text
from streeteasy_archive.flight import FlightText, decode_records

VERSION = 'bounded-building-field-recovery-v1'
FIELDS = ('amenities', 'additionalDetails', 'nyc')
REFERENCE = re.compile(r'\$([0-9a-f]+)\Z')


def recover_records(records, original):
    """Bind the complete original building object before resolving selected fields."""
    def walk(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    if not isinstance(original, dict) or not original.get('id') or not original.get('slug'):
        raise ValueError('Missing building identity')
    if not any(value == original for record in records.values() for value in walk(record)):
        raise ValueError('Exact original building object absent from body')
    used, budget = set(), [100000]

    def resolve(value, stack=(), depth=0):
        budget[0] -= 1
        if budget[0] < 0 or depth > 64:
            raise ValueError('Building field resolution limit exceeded')
        if isinstance(value, FlightText):
            return str(value)
        match = REFERENCE.fullmatch(value) if isinstance(value, str) else None
        if match:
            key = match.group(1)
            if key in stack or key not in records:
                raise ValueError('Cyclic or missing building field reference')
            used.add(key)
            return resolve(records[key], stack+(key,), depth+1)
        if isinstance(value, list):
            return [resolve(child, stack, depth+1) for child in value]
        if isinstance(value, dict):
            return {key: resolve(child, stack, depth+1) for key, child in value.items()}
        return value

    fields = {name: {'present': name in original, 'original': original.get(name),
                     'resolved': resolve(original.get(name))} for name in FIELDS}
    return {'building_id': original['id'], 'building_slug': original['slug'],
            'fields': fields, 'resolved_record_ids': sorted(used), 'version': VERSION}


def recover(body, raw_building_json, *, body_sha256, raw_building_sha256):
    if hashlib.sha256(body).hexdigest() != body_sha256:
        raise ValueError('Archived building body hash differs')
    if hashlib.sha256(raw_building_json.encode()).hexdigest() != raw_building_sha256:
        raise ValueError('Archived building payload hash differs')
    records = decode_records(flight_text(_scripts(_selector(body))))
    return recover_records(records, json.loads(raw_building_json))
