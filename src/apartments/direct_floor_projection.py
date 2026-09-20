"""Reversible additions of reviewed own-ad floor claims to a scope-reviewed source.

This contract permits two previously unknown advertised-floor fields to change.
Physical height, independent label proxies and all other fields remain intact.
"""
from copy import deepcopy
import hashlib

from .corrections import canonical, instant
from .reviewed_cohort_quarantine import records_hash, sha
from . import residual_scope_projection

VERSION = 'reviewed-direct-floor-projection-v1'
SIDECAR = 'direct-floor-changes.jsonl'
FIELD = 'direct_floor_provenance'
FIELDS = ('listed_floor', 'advertised_floor')


def _ids(values):
    if not isinstance(values, list) or not values:
        raise ValueError('Nonempty capture membership required')
    result = []
    for value in values:
        if type(value) not in (int, str) or not value:
            raise ValueError('Invalid capture identity')
        result.append((type(value).__name__, value))
    if len(set(result)) != len(result):
        raise ValueError('Duplicate capture identity')
    return set(result)


def validate_case(row, case, reviewed_at):
    """Check exact source row, unknown floor, capture membership and claim clocks."""
    try:
        floor = case['advertised_floor']
        if (type(floor) is not int or floor <= 0
                or case['action'] != 'add_explicit_advertised_floor'
                or case['proposed_fields'] != dict.fromkeys(FIELDS, floor)
                or case['source_row_sha256'] != sha(row)
                or any(type(case[k]) is not type(row[k]) or case[k] != row[k]
                       for k in ('audit_id', 'source_listing_id'))
                or FIELD in row or any(row.get(k) is not None for k in FIELDS)
                or row['expanded_floor_provenance']['status'] != 'unsupported_label_syntax'
                or instant(row['known_at']) > instant(reviewed_at)):
            raise ValueError('Direct floor decision scope, source, value or clock differs')
        witnesses = case['witnesses']
        if not isinstance(witnesses, list):
            raise ValueError('Capture witnesses must be a list')
        attached = row.get('capture_ids') or [row.get('capture_id')]
        if _ids([w['capture_id'] for w in witnesses]) != _ids(attached):
            raise ValueError('Direct floor requires every exact attached capture')
        for witness in witnesses:
            if instant(witness['source_collected_at']) > instant(row['known_at']):
                raise ValueError('Floor evidence is later than source knowledge')
            for key in ('raw_listing_sha256', 'description_sha256'):
                value = witness[key]
                if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                    raise ValueError('Invalid floor evidence hash')
            claims = witness['claims']
            if not isinstance(claims, list) or not claims:
                raise ValueError('Missing literal floor claims')
            for claim in claims:
                if (claim['attribute'] != 'advertised_floor' or type(claim['value']) is not int
                        or claim['value'] != floor or claim['source_path'] != '/description'
                        or claim['rule'] != 'explicit-dwelling-floor-offer-v1'
                        or type(claim['start']) is not int or type(claim['end']) is not int
                        or not 0 <= claim['start'] < claim['end']
                        or not isinstance(claim['literal'], str)
                        or len(claim['literal']) != claim['end'] - claim['start']):
                    raise ValueError('Floor literal claim differs')
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Malformed direct floor decision') from exc


def apply_case(row, case, reviewed_at, policy_sha256):
    validate_case(row, case, reviewed_at)
    result = deepcopy(row)
    result.update(case['proposed_fields'])
    result[FIELD] = {'source_row_sha256': case['source_row_sha256'],
        'policy_sha256': policy_sha256, 'reviewed_at': reviewed_at,
        'measurement': 'explicit_own_ad_advertised_floor_not_physical_height',
        'source_known_at': row['known_at'], 'witnesses_sha256': records_hash(case['witnesses'])}
    return result


def parent_rows(manifest, rows, changes):
    """Validate the complete forward replay and reconstruct the exact parent."""
    try:
        return _parent_rows(manifest, rows, changes)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError('Malformed direct floor projection') from exc


def _parent_rows(manifest, rows, changes):
    parent = manifest['source_manifest']
    policy = manifest['policy']
    if (manifest['version'] != VERSION or parent['version'] != residual_scope_projection.VERSION
            or records_hash([parent]) != manifest['source_manifest_sha256']
            or hashlib.sha256((canonical(policy)+'\n').encode()).hexdigest() != manifest['policy_sha256']
            or policy['version'] != 'prepared-direct-floor-additions-v1' or policy['applied'] is not False
            or policy['source_manifest_sha256'] != manifest['source_manifest_sha256']
            or not isinstance(rows, list) or not isinstance(changes, list)
            or records_hash(rows) != manifest['files']['observations.jsonl']
            or records_hash(changes) != manifest['files'][SIDECAR]
            or len(rows) != manifest['source_rows'] or len(changes) != len(policy['cases'])
            or not changes):
        raise ValueError('Direct floor manifest or file binding differs')
    cases = {c['audit_id']: c for c in policy['cases']}
    if len(cases) != len(changes):
        raise ValueError('Duplicate floor policy identity')
    restored = list(rows)
    indices, seen = set(), set()
    for change in changes:
        if set(change) != {'source_index', 'before', 'case'}:
            raise ValueError('Unexpected floor sidecar fields')
        index, before, case = change['source_index'], change['before'], change['case']
        if type(index) is not int or not 0 <= index < len(rows) or index in indices:
            raise ValueError('Invalid or repeated floor source index')
        ad = before['audit_id']
        if ad in seen or case != cases.get(ad):
            raise ValueError('Floor policy coverage differs')
        expected = apply_case(before, case, manifest['reviewed_at'], manifest['policy_sha256'])
        if canonical(rows[index]) != canonical(expected):
            raise ValueError('Floor forward replay changed nonfloor attributes or provenance')
        restored[index] = deepcopy(before)
        indices.add(index); seen.add(ad)
    if records_hash(restored) != parent['files']['observations.jsonl']:
        raise ValueError('Exact floor parent reconstruction failed')
    return deepcopy(parent), deepcopy(restored)
