"""Verify a bounded reporting-detail split without changing source history."""
from copy import deepcopy
import hashlib
import re

from .corrections import canonical, instant

VERSION = 'reported-shared-laundry-floor-projection-v1'
PARENT = 'reviewed-floor-conflict-projection-v1'
FIELD = 'laundry_floor_split_evidence'


def hashed(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def manifest_hash(value):
    return hashlib.sha256((canonical(value)+'\n').encode()).hexdigest()


def capture_ids(row):
    values = row.get('capture_ids', []) + ([row['capture_id']] if row.get('capture_id') is not None else [])
    return {(type(v).__name__, v) for v in values}


def validate_evidence(row, evidence, measurement_hash, interpreted_at):
    if (not isinstance(measurement_hash, str) or not re.fullmatch('[0-9a-f]{64}', measurement_hash)
            or evidence.get('before') != 'in_building' or evidence.get('after') != 'on_floor'
            or evidence.get('measurement_manifest_sha256') != measurement_hash
            or evidence.get('interpreted_at') != interpreted_at
            or instant(interpreted_at) < instant(row['known_at'])):
        raise ValueError('Laundry split value, measurement or interpretation clock differs')
    captures = evidence.get('captures', [])
    ids = {(type(c['capture_id']).__name__, c['capture_id']) for c in captures}
    if not ids or ids != capture_ids(row) or len(ids) != len(captures):
        raise ValueError('Laundry split requires every exact attached capture')
    for capture in captures:
        for key in ('body_sha256', 'raw_listing_sha256', 'description_sha256'):
            if not isinstance(capture.get(key), str) or not re.fullmatch('[0-9a-f]{64}', capture[key]):
                raise ValueError('Laundry split capture provenance hash missing or invalid')
        if (any(capture.get(k) != row[k] for k in ('audit_id', 'unit_id', 'source_listing_id'))
                or instant(capture['source_collected_at']) > instant(capture['known_at'])
                or instant(capture['known_at']) > instant(interpreted_at)
                or capture.get('source_category') != 'on_floor'
                or not capture.get('same_floor_claims')):
            raise ValueError('Laundry split capture identity, scope or clock differs')
        for claim in capture['same_floor_claims']:
            if (claim.get('scope') != 'shared_same_floor' or claim.get('present') is not True
                    or claim.get('source_path') != '/description'
                    or type(claim.get('start')) is not int or type(claim.get('end')) is not int
                    or not 0 <= claim['start'] < claim['end']
                    or not isinstance(claim.get('literal'), str)
                    or len(claim['literal']) != claim['end']-claim['start']):
                raise ValueError('Laundry split requires literal positive same-floor claims')


def parent_rows(manifest, rows):
    parent = manifest.get('source_manifest')
    changed = manifest.get('changed_audit_ids', [])
    if (manifest.get('version') != VERSION or not isinstance(parent, dict)
            or parent.get('version') != PARENT
            or manifest_hash(parent) != manifest.get('source_manifest_sha256')
            or not changed or len(set(changed)) != len(changed)):
        raise ValueError('Laundry floor split parent lineage or coverage differs')
    current = deepcopy(rows)
    remaining = set(changed)
    checksum = hashlib.sha256()
    for row in current:
        evidence = row.get(FIELD)
        if evidence is not None:
            if row['audit_id'] not in remaining or row.get('laundry_type') != 'on_floor':
                raise ValueError('Unlisted or invalid laundry floor split')
            validate_evidence(row, evidence, manifest['measurement_manifest_sha256'], manifest['interpreted_at'])
            row['laundry_type'] = 'in_building'
            del row[FIELD]
            if hashed(row) != evidence.get('source_row_sha256'):
                raise ValueError('Reconstructed laundry split source row differs')
            remaining.remove(row['audit_id'])
        checksum.update((canonical(row)+'\n').encode())
    if remaining or checksum.hexdigest() != parent.get('files', {}).get('observations.jsonl'):
        raise ValueError('Reconstructed laundry split parent observations differ')
    return parent, current
