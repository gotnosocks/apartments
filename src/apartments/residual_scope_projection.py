"""Reversible, reviewed scope exclusions against one expanded-floor base.

This contract establishes source/evidence integrity, not the semantic truth of
an analyst's scope judgment. Readers must also replay the expanded parent using
its retained ancestor sidecars. Later decisions accumulate against that base.
"""
from copy import deepcopy
import hashlib
import json
import re

from . import expanded_floor_projection as expanded
from .corrections import canonical, instant
from .reviewed_cohort_quarantine import records_hash, sha

VERSION = 'reviewed-residual-scope-projection-v1'
DECISION_VERSION = 'reviewed-residual-scope-decisions-v1'
PARENT = expanded.VERSION
SIDECAR = 'residual-scope-quarantine.jsonl'
ACTIONS = {'quarantine_nonresidential', 'quarantine_location_conflict', 'quarantine_price_anomaly', 'quarantine_product_scope'}
IDENTITIES = ('audit_id', 'unit_id', 'source_listing_id')


def _identity(value):
    if type(value) not in (str, int) or (type(value) is str and not value.strip()):
        raise ValueError('Scope identities must be nonempty strings or integers')
    return type(value).__name__, value


def decision_sort_key(decision):
    """Canonical typed audit ordering for the bound decisions.jsonl file."""
    return canonical(_identity(decision['audit_id']))


def _capture_ids(row):
    values = row.get('capture_ids', [])
    if not isinstance(values, list):
        raise ValueError('Scope capture IDs must be a list')
    identities = [_identity(value) for value in values]
    if len(set(identities)) != len(identities):
        raise ValueError('Repeated source capture identity')
    if row.get('capture_id') is not None:
        identities.append(_identity(row['capture_id']))
    if not identities:
        raise ValueError('Scope decision needs attached source captures')
    return set(identities)


def _capture_map(captures):
    if not isinstance(captures, list) or not captures or not all(isinstance(c, dict) for c in captures):
        raise ValueError('Scope capture evidence must be a nonempty list')
    result = {_identity(c['capture_id']): c for c in captures}
    if len(result) != len(captures):
        raise ValueError('Repeated scope capture evidence')
    return result


def _same_ids(left, right):
    return all(_identity(left[key]) == _identity(right[key]) for key in IDENTITIES)


def validate_decision(row, decision, reviewed_at):
    """Validate an exact row decision with every own capture and literal witness."""
    try:
        _validate_decision(row, decision, reviewed_at)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Malformed scope decision or evidence') from exc


def _validate_decision(row, decision, reviewed_at):
    if (decision.get('action') not in ACTIONS
            or any(not isinstance(decision.get(key), str) or not decision[key].strip()
                   for key in ('reason', 'reviewer'))
            or decision.get('reviewed_at') != reviewed_at
            or instant(row['known_at']) > instant(reviewed_at)
            or decision.get('source_row_sha256') != sha(row)
            or decision.get('decision_id') != sha({k: v for k, v in decision.items() if k != 'decision_id'})
            or not _same_ids(decision, row)):
        raise ValueError('Scope action, identity, clock or source row binding differs')
    captures = decision.get('source_captures')
    source = _capture_map(captures)
    evidence = _capture_map(decision.get('evidence'))
    if set(source) != _capture_ids(row) or set(evidence) != set(source):
        raise ValueError('Scope needs every exact attached capture')
    if decision.get('action') != 'quarantine_price_anomaly':
        for field in ('floor_label_provenance', expanded.FIELD):
            provenance = row[field]
            if (provenance.get('source_capture_evidence_sha256') != records_hash(captures)
                    or provenance.get('source_known_at') != row['known_at']
                    or instant(provenance['interpreted_at']) > instant(reviewed_at)):
                raise ValueError('Scope source capture provenance differs')
    source_path = '/pricing/price' if decision.get('action') == 'quarantine_price_anomaly' else '/propertyDetails/address/displayUnit'
    for key, capture in evidence.items():
        original = source[key]
        text = capture.get('description')
        if (not _same_ids(original, row) or not _same_ids(capture, row)
                or original.get('source_path') != source_path
                or capture.get('source_path') != '/description'
                or any(sha(capture.get(k)) != sha(original[k]) for k in
                       ('raw_listing_sha256', 'body_sha256', 'source_collected_at', 'known_at'))
                or not instant(original['source_collected_at']) <= instant(original['known_at'])
                       <= instant(row['known_at']) <= instant(reviewed_at)
                or not isinstance(text, str)
                or hashlib.sha256(text.encode()).hexdigest() != capture.get('description_sha256')):
            raise ValueError('Scope capture identity, source, description or clock differs')
        for hash_key in ('raw_listing_sha256', 'body_sha256'):
            if not isinstance(capture.get(hash_key), str) or not re.fullmatch('[0-9a-f]{64}', capture[hash_key]):
                raise ValueError('Scope capture source hash is invalid')
        if 'raw_listing_json' in capture:
            raw = capture['raw_listing_json']
            if (not isinstance(raw, str)
                    or hashlib.sha256(raw.encode()).hexdigest() != capture['raw_listing_sha256']
                    or not isinstance(json.loads(raw), dict)):
                raise ValueError('Scope raw listing witness differs')
        spans = capture.get('spans')
        if not isinstance(spans, list) or not spans:
            raise ValueError('Scope capture requires literal review spans')
        seen = set()
        for span in spans:
            a, b = span.get('start'), span.get('end')
            if (type(a) is not int or type(b) is not int or not 0 <= a < b <= len(text)
                    or text[a:b] != span.get('literal') or (a, b) in seen):
                raise ValueError('Scope literal span differs or is repeated')
            seen.add((a, b))


def parent_rows(manifest, kept, quarantined):
    """Restore unchanged excluded rows at original positions and verify the base."""
    try:
        return _parent_rows(manifest, kept, quarantined)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Malformed scope projection lineage') from exc


def _parent_rows(manifest, kept, quarantined):
    parent, dm = manifest.get('source_manifest'), manifest.get('decisions_manifest')
    if (manifest.get('version') != VERSION or not isinstance(parent, dict)
            or parent.get('version') != PARENT
            or records_hash([parent]) != manifest.get('source_manifest_sha256')
            or not isinstance(dm, dict) or dm.get('version') != DECISION_VERSION
            or records_hash([dm]) != manifest.get('decisions_manifest_sha256')
            or dm.get('source_manifest_sha256') != manifest.get('source_manifest_sha256')
            or dm.get('source_observations_sha256') != parent.get('files', {}).get('observations.jsonl')
            or dm.get('reviewed_at') != manifest.get('reviewed_at')
            or not isinstance(kept, list) or not isinstance(quarantined, list) or not quarantined
            or records_hash(quarantined) != manifest.get('files', {}).get(SIDECAR)
            or records_hash(kept) != manifest.get('files', {}).get('observations.jsonl')
            or instant(parent['interpreted_at']) > instant(manifest['reviewed_at'])):
        raise ValueError('Scope parent lineage, observations or sidecar binding differs')
    total = manifest.get('source_rows')
    if type(total) is not int or total != len(kept) + len(quarantined):
        raise ValueError('Scope source row count differs')
    positions, audit_ids, decision_ids = {}, set(), set()
    for item in quarantined:
        if set(item) != {'source_index', 'observation', 'decision'}:
            raise ValueError('Scope sidecar footprint differs')
        index, row, decision = item['source_index'], item['observation'], item['decision']
        if type(index) is not int or not 0 <= index < total or index in positions:
            raise ValueError('Scope original position is invalid or repeated')
        validate_decision(row, decision, manifest['reviewed_at'])
        for key in ('policy_sha256', 'source_review_manifest_sha256'):
            if key in dm and decision.get(key) != dm[key]:
                raise ValueError('Scope decision policy or review manifest binding differs')
        identity = _identity(row['audit_id'])
        if identity in audit_ids or decision['decision_id'] in decision_ids:
            raise ValueError('Repeated scope observation or decision')
        positions[index] = row
        audit_ids.add(identity)
        decision_ids.add(decision['decision_id'])
    kept_ids = [_identity(row['audit_id']) for row in kept]
    for row in kept:
        for field in IDENTITIES:
            _identity(row[field])
        _capture_ids(row)
    if (len(set(kept_ids)) != len(kept_ids) or audit_ids & set(kept_ids)
            or sorted(decision_ids) != manifest.get('decision_ids')
            or records_hash(sorted((item['decision'] for item in quarantined), key=decision_sort_key))
               != dm.get('files', {}).get('decisions.jsonl')):
        raise ValueError('Scope membership or decision coverage differs')
    retained = iter(kept)
    restored = [deepcopy(positions[i] if i in positions else next(retained)) for i in range(total)]
    if records_hash(restored) != parent['files']['observations.jsonl']:
        raise ValueError('Reconstructed scope parent observations differ')
    return parent, restored
