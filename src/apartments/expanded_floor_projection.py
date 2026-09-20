"""Reversible own-capture label expansion with separately reviewed floor masks.

Label proxies describe advertised numbering, never physical height. The parent
projection, captures, original values and correction witness remain recoverable.
"""
from copy import deepcopy
import hashlib
import re

from . import floor_label_projection as original
from .corrections import instant
from .reviewed_cohort_quarantine import records_hash, sha

VERSION = 'source-bound-expanded-label-floor-projection-v1'
PARENT = original.VERSION
SIDECAR = 'expanded-floor-projection.jsonl'
FIELD = 'expanded_floor_provenance'
FLOOR_FIELDS = ('listed_floor', 'advertised_floor')


def candidate(label):
    """Return a named, deliberately bounded numbering hypothesis and its floor."""
    if label is None:
        return None, None
    if not isinstance(label, str):
        raise ValueError('Display unit must be literal text or null')
    value = label.strip().removeprefix('#').strip().upper()
    old = original.candidate(label)
    if old is not None:
        return original.RULE, old
    if re.fullmatch(r'[1-9][0-9]{2,3}', value):
        return 'numeric_hundreds', int(value)//100
    for rule, pattern in (
        ('north_south_wing_prefix', r'[NS]([1-9][0-9]?)[A-Z]'),
        ('front_rear_suffix', r'([1-9][0-9]?)(?:FE|FW|RE|RW|FR|RR|FF|RF)'),
        ('explicit_ordinal_label', r'([1-9][0-9]?)(?:ST|ND|RD|TH)(?:FL|FLOOR)'),
    ):
        match = re.fullmatch(pattern, value)
        if match:
            return rule, int(match[1])
    return None, None


def _identity(value):
    if type(value) not in (str, int):
        raise ValueError('Source identities must be literal strings or integers')
    return type(value).__name__, value


def _verified_original(row, change, policy):
    # This temporary replay only replaces/removes top-level fields. Borrowed
    # nested values are read-only and never returned to callers.
    before = dict(row)
    for key in original.FIELDS:
        if key not in before:
            raise ValueError('Missing original floor projection provenance')
        before.pop(key)
    if type(change.get('listed_floor_was_present')) is not bool:
        raise ValueError('Original floor presence flag differs')
    if change['listed_floor_was_present']:
        before['listed_floor'] = change['before_listed_floor']
    else:
        before.pop('listed_floor', None)
    captures = change['captures']
    if not isinstance(captures, list) or not captures:
        raise ValueError('Original capture evidence is missing')
    for capture in captures:
        _identity(capture['capture_id'])
        if any(_identity(capture[k]) != _identity(row[k])
               for k in ('audit_id', 'unit_id', 'source_listing_id')):
            raise ValueError('Original typed source identity differs')
        value = capture['candidate_floor']
        if value is not None and type(value) is not int:
            raise ValueError('Original floor candidate must be integer or null')
    for ident in row.get('capture_ids', []) + ([row['capture_id']] if row.get('capture_id') is not None else []):
        _identity(ident)
    replay = original._project_row_view(before, captures, policy['excluded_buildings'],
        policy['building_floor_evidence'].get(row['building'], []), policy['parent_interpreted_at'])
    if sha(before) != change['source_row_sha256'] or sha(replay) != sha(row):
        raise ValueError('Original projection is not the exact bound forward transform')
    return captures


def _mask(row, captures, policy, as_of):
    matches = [mask for mask in policy.get('floor_masks', [])
               if _identity(mask['audit_id']) == _identity(row['audit_id'])]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError('Repeated floor mask identity')
    mask = matches[0]
    if (mask.get('source_row_sha256') != sha(row)
            or type(mask.get('before_advertised_floor')) is not int
            or mask['before_advertised_floor'] != 3
            or type(row.get('advertised_floor')) not in (int, float)
            or row['advertised_floor'] != mask['before_advertised_floor']
            or row.get('listed_floor') is not None
            or not isinstance(mask.get('reason'), str) or not mask['reason'].strip()
            or not instant(row['known_at']) <= instant(mask['reviewed_at']) <= instant(as_of)):
        raise ValueError('Floor mask source, scope or review clock differs')
    record = mask.get('correction_record', {})
    target = {'source': 'streeteasy', 'source_listing_id': row['source_listing_id'], 'version_id': sha(row)}
    patch = [{'op': 'test', 'path': '/advertised_floor', 'value': 3},
             {'op': 'replace', 'path': '/advertised_floor', 'value': None}]
    if (record.get('action') != 'edit' or record.get('schema_version') != 1
            or not isinstance(record.get('id'), str) or not record['id'].strip()
            or sha(record.get('target')) != sha(target)
            or sha(record.get('patch')) != sha(patch)
            or record.get('validity') != {'all_time': True}
            or not instant(mask['reviewed_at']) <= instant(record['recorded_at']) <= instant(as_of)
            or record.get('hash') != sha({k: v for k, v in record.items() if k != 'hash'})):
        raise ValueError('Floor mask correction witness differs')
    claims = mask.get('captures', [])
    expected = {_identity(c['capture_id']): c for c in captures}
    actual = {_identity(c['capture_id']): c for c in claims}
    if set(expected) != set(actual) or len(actual) != len(claims):
        raise ValueError('Floor mask must bind every exact own capture')
    for key, claim in actual.items():
        cap = expected[key]
        text = claim.get('description')
        if (any(sha(claim.get(k)) != sha(cap[k]) for k in
                ('audit_id', 'unit_id', 'source_listing_id', 'body_sha256',
                 'raw_listing_sha256', 'known_at', 'source_collected_at'))
                or claim.get('source_path') != '/description'
                or not isinstance(text, str)
                or hashlib.sha256(text.encode()).hexdigest() != claim.get('description_sha256')
                or not instant(claim['known_at']) <= instant(mask['reviewed_at'])
                or not claim.get('spans')):
            raise ValueError('Floor mask capture source, description or clock differs')
        for span in claim['spans']:
            start, end = span.get('start'), span.get('end')
            if (type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(text)
                    or text[start:end] != span.get('literal')
                    or span['literal'] != 'Photos are of the same unit on the 3rd floor.'):
                raise ValueError('Floor mask requires the exact reviewed full photo disclaimer')
    return mask


def project_row(row, original_change, policy, as_of):
    return deepcopy(_project_row_view(row, original_change, policy, as_of))


def _project_row_view(row, original_change, policy, as_of):
    """Borrow nested values only for internal read-only forward verification."""
    if FIELD in row:
        raise ValueError('Expanded floor projection already applied')
    if instant(as_of) < instant(policy['parent_interpreted_at']) or instant(as_of) < instant(row['known_at']):
        raise ValueError('Floor interpretation must follow source and parent knowledge')
    captures = _verified_original(row, original_change, policy)
    mask = _mask(row, captures, policy, as_of)
    result = dict(row)
    if mask is not None:
        result['advertised_floor'] = None
    hypotheses = [candidate(c['literal']) for c in captures]
    unanimous = len(set(hypotheses)) == 1
    rule, value = hypotheses[0] if unanimous else (None, None)
    evidence = policy['building_floor_evidence'].get(row['building'], [])
    limit = min(c['floor_count'] for c in evidence) if evidence else None
    known = result.get('listed_floor') is not None or result.get('advertised_floor') is not None
    status = ('existing_floor_preserved' if known else
        'reviewed_building_numbering_excluded' if row['building'] in policy['excluded_buildings'] else
        'reviewed_unit_numbering_excluded' if row['unit_id'] in policy.get('excluded_units', []) else
        'conflicting_capture_labels' if not unanimous else
        'missing_capture_label' if all(c['literal'] is None or not c['literal'].strip() for c in captures) else
        'unsupported_label_syntax' if value is None else
        'missing_building_floor_count' if limit is None else
        'above_captured_building_floor_count' if value > limit else 'label_proxy')
    if status == 'label_proxy':
        result['listed_floor'] = value
    result[FIELD] = {'rule': rule, 'candidate_floor': value, 'status': status,
        'measurement': 'advertised_unit_label_proxy_not_physical_floor',
        'source_known_at': row['known_at'], 'interpreted_at': as_of,
        'building_floor_count_limit': limit, 'building_evidence_sha256': records_hash(evidence),
        'source_capture_evidence_sha256': records_hash(captures),
        'floor_mask_sha256': sha(mask) if mask is not None else None,
        'correction_id': mask['correction_record']['id'] if mask is not None else None}
    return result


def make_change(index, row, original_change):
    return {'source_index': index, 'source_row_sha256': sha(row),
        'before': {key: {'present': key in row, 'value': deepcopy(row.get(key))} for key in FLOOR_FIELDS},
        'original_change': deepcopy(original_change)}


def parent_rows(manifest, rows, changes):
    parent = manifest.get('source_manifest')
    policy = manifest.get('policy')
    if (manifest.get('version') != VERSION or not isinstance(parent, dict) or parent.get('version') != PARENT
            or records_hash([parent]) != manifest.get('source_manifest_sha256')
            or not isinstance(policy, dict) or sha(policy) != manifest.get('policy_sha256')
            or type(manifest.get('source_rows')) is not int or len(rows) != manifest['source_rows']
            or not isinstance(changes, list) or len(rows) != len(changes)
            or records_hash(changes) != manifest.get('files', {}).get(SIDECAR)
            or records_hash(rows) != manifest.get('files', {}).get('observations.jsonl')):
        raise ValueError('Expanded floor parent, policy, observations or sidecar differs')
    for policy_key, parent_key in (('excluded_buildings', 'excluded_buildings'),
            ('building_floor_evidence', 'building_floor_evidence'), ('parent_interpreted_at', 'interpreted_at')):
        if sha(policy.get(policy_key)) != sha(parent.get(parent_key)):
            raise ValueError('Expanded floor policy changed original interpretation context')
    restored, original_changes = [], []
    for index, (row, change) in enumerate(zip(rows, changes, strict=True)):
        if type(change.get('source_index')) is not int or change['source_index'] != index or FIELD not in row:
            raise ValueError('Expanded floor projection order or provenance differs')
        before = deepcopy(row)
        before.pop(FIELD)
        if set(change.get('before', {})) != set(FLOOR_FIELDS):
            raise ValueError('Expanded floor original field footprint differs')
        for key in FLOOR_FIELDS:
            saved = change['before'][key]
            if set(saved) != {'present', 'value'} or type(saved['present']) is not bool:
                raise ValueError('Expanded floor original presence flag differs')
            if saved['present']:
                before[key] = saved['value']
            else:
                if saved['value'] is not None:
                    raise ValueError('Absent floor field has a nonnull saved value')
                before.pop(key, None)
        if (sha(before) != change['source_row_sha256']
                or sha(row) != sha(_project_row_view(before, change['original_change'], policy, manifest['interpreted_at']))):
            raise ValueError('Expanded floor differs from exact bounded forward transform')
        restored.append(before)
        original_changes.append(change['original_change'])
    if (records_hash(restored) != parent['files']['observations.jsonl']
            or records_hash(original_changes) != parent['files'][original.SIDECAR]):
        raise ValueError('Expanded floor does not restore exact ordered parent and original sidecar')
    mask_ids = [_identity(m['audit_id']) for m in policy.get('floor_masks', [])]
    if len(mask_ids) != len(set(mask_ids)) or not set(mask_ids) <= {_identity(r['audit_id']) for r in restored}:
        raise ValueError('Floor mask policy contains duplicate or unattached reviews')
    original.parent_rows(parent, restored, original_changes)
    return parent, restored
