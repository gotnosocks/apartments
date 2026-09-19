"""Reversible, source-bound unit-label proxies; never physical floor measurements."""
from copy import deepcopy
import re
import math
from urllib.parse import urlsplit
from .reviewed_cohort_quarantine import records_hash, sha
from .corrections import instant

VERSION = 'source-bound-label-floor-projection-v1'
SIDECAR = 'floor-label-projection.jsonl'
PARENT = 'reviewed-elevator-negation-projection-v1'
RULE = 'one-or-two-digit-positive-prefix-single-letter-v1'
FIELDS = ('source_listed_floor', 'label_derived_floor', 'floor_label_provenance')


def candidate(label):
    if label is None: return None
    if not isinstance(label, str): raise ValueError('Display unit must be literal text or null')
    match = re.fullmatch(r'([1-9][0-9]?)[A-Z]', label.strip().removeprefix('#').strip().upper())
    return int(match[1]) if match else None


def project_row(row, captures, excluded_buildings, building_evidence=None, as_of=None):
    if as_of is None or instant(as_of) < instant(row['known_at']):
        raise ValueError('Floor interpretation must follow source knowledge')
    if any(k in row for k in FIELDS): raise ValueError('Floor projection already applied')
    expected = {(type(c).__name__, c) for c in row.get('capture_ids', []) +
                ([row['capture_id']] if row.get('capture_id') is not None else [])}
    actual = {(type(c['capture_id']).__name__, c['capture_id']) for c in captures}
    if not expected or actual != expected or len(captures) != len(actual):
        raise ValueError('Floor label capture membership differs')
    for c in captures:
        if (any(c[k] != row[k] for k in ('audit_id', 'unit_id', 'source_listing_id'))
                or c['candidate_floor'] != candidate(c['literal'])
                or c['source_path'] != '/propertyDetails/address/displayUnit'
                or instant(c['source_collected_at']) > instant(c['known_at'])
                or instant(c['known_at']) > instant(row['known_at'])
                or any(not re.fullmatch('[0-9a-f]{64}', c[k]) for k in ('raw_listing_sha256', 'body_sha256'))):
            raise ValueError('Floor capture identity, literal, hash or knowledge clock differs')
    values = {c['candidate_floor'] for c in captures}
    value = next(iter(values)) if len(values) == 1 and None not in values else None
    explicit = row.get('listed_floor') if row.get('listed_floor') is not None else row.get('advertised_floor')
    counts = [c['floor_count'] for c in (building_evidence or [])]
    limit = min(counts) if counts else None
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in counts):
        raise ValueError('Invalid building floor count')
    for evidence in building_evidence or []:
        if (instant(evidence['source_collected_at']) > instant(as_of)
                or evidence['source_path'] != '/floorCount'
                or urlsplit(evidence['source_url']).hostname != 'streeteasy.com'
                or urlsplit(evidence['source_url']).path.rstrip('/') != '/building/'+row['building']
                or any(not re.fullmatch('[0-9a-f]{64}', evidence[k]) for k in ('raw_building_sha256', 'body_sha256'))):
            raise ValueError('Building floor evidence source, clock or hash differs')
    status = ('explicit_source_floor' if explicit is not None else
              'reviewed_building_numbering_excluded' if row['building'] in excluded_buildings else
              'unresolved_or_conflicting_capture_labels' if value is None else
              'above_captured_building_floor_count' if limit is not None and value > limit else
              'two_digit_label_without_building_count' if value >= 10 and limit is None else 'label_proxy')
    result = deepcopy(row)
    result['source_listed_floor'] = row.get('listed_floor')
    result['label_derived_floor'] = value
    result['floor_label_provenance'] = {'rule': RULE, 'status': status,
        'measurement': 'advertised_unit_label_proxy_not_physical_floor',
        'source_known_at': row['known_at'], 'interpreted_at': as_of,
        'building_floor_count_limit': limit, 'building_evidence_sha256': records_hash(building_evidence or []),
        'source_capture_evidence_sha256': records_hash(captures)}
    if status == 'label_proxy': result['listed_floor'] = value
    return result


def parent_rows(manifest, rows, changes):
    parent = manifest.get('source_manifest')
    if (manifest.get('version') != VERSION or not isinstance(parent, dict)
            or parent.get('version') != PARENT or records_hash([parent]) != manifest.get('source_manifest_sha256')
            or not isinstance(changes, list) or len(changes) != len(rows)
            or records_hash(changes) != manifest.get('files', {}).get(SIDECAR)
            or len(rows) != manifest.get('source_rows')):
        raise ValueError('Floor projection parent or sidecar differs')
    restored = []
    for index, (row, change) in enumerate(zip(rows, changes, strict=True)):
        if change.get('source_index') != index: raise ValueError('Floor projection order differs')
        before = deepcopy(row)
        for key in FIELDS: before.pop(key, None)
        if change['listed_floor_was_present']: before['listed_floor'] = change['before_listed_floor']
        else: before.pop('listed_floor', None)
        if (sha(before) != change['source_row_sha256']
                or row != project_row(before, change['captures'], manifest['excluded_buildings'],
                    manifest.get('building_floor_evidence', {}).get(before['building'], []), manifest.get('interpreted_at'))):
            raise ValueError('Floor projection differs from exact bounded forward transform')
        restored.append(before)
    if records_hash(restored) != parent['files']['observations.jsonl']:
        raise ValueError('Floor projection does not restore exact parent observations')
    return parent, restored
