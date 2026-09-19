"""Verify reviewed membership exclusions and reconstruct the exact parent order.

Excluded observations live in a hashed sidecar, not embedded recursively in
manifests. Retained values and every original excluded row remain unchanged.
"""
from copy import deepcopy
import hashlib
import re

from .corrections import canonical, instant

VERSION = 'reviewed-listing-scope-quarantine-projection-v1'
DECISION_VERSION = 'reviewed-listing-scope-quarantine-decisions-v1'
PARENT = 'reviewed-floor-conflict-projection-v1'
ACTIONS = {'quarantine_unresolved_gross_price_basis', 'quarantine_explicit_short_term_offer'}
SIDECAR = 'quarantined.jsonl'


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def records_hash(rows):
    checksum = hashlib.sha256()
    for row in rows: checksum.update((canonical(row)+'\n').encode())
    return checksum.hexdigest()


def validate_decision(row, decision, reviewed_at):
    if (decision.get('action') not in ACTIONS or not isinstance(decision.get('reason'), str)
            or not decision['reason'].strip() or decision.get('reviewed_at') != reviewed_at
            or not isinstance(decision.get('reviewer'), str) or not decision['reviewer'].strip()
            or instant(reviewed_at) < instant(row['known_at'])
            or decision.get('source_row_sha256') != sha(row)
            or decision.get('decision_id') != sha({k: v for k, v in decision.items() if k != 'decision_id'})
            or any(decision.get(k) != row[k] for k in ('audit_id', 'unit_id', 'source_listing_id'))
            or row.get('analysis_price_basis') != 'historical_initial_own_advertisement_ask'):
        raise ValueError('Quarantine action, identity, clock or source row binding differs')
    expected = {(type(v).__name__, v) for v in row.get('capture_ids', [])}
    if row.get('capture_id') is not None: expected.add((type(row['capture_id']).__name__, row['capture_id']))
    evidence = decision.get('evidence', [])
    identities = {(type(c['capture_id']).__name__, c['capture_id']) for c in evidence}
    if not expected or identities != expected or len(evidence) != len(identities):
        raise ValueError('Quarantine needs every exact attached capture')
    for capture in evidence:
        text = capture.get('description')
        for key in ('raw_listing_sha256', 'body_sha256'):
            if not isinstance(capture.get(key), str) or not re.fullmatch('[0-9a-f]{64}', capture[key]):
                raise ValueError('Quarantine source hash is invalid')
        if (not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != capture.get('description_sha256')
                or any(capture.get(k) != row[k] for k in ('audit_id', 'unit_id', 'source_listing_id'))
                or instant(capture['known_at']) > instant(reviewed_at)
                or instant(capture['source_collected_at']) > instant(capture['known_at'])
                or not capture.get('spans')):
            raise ValueError('Quarantine capture evidence or clock differs')
        for span in capture['spans']:
            a, b = span.get('start'), span.get('end')
            if (type(a) is not int or type(b) is not int or not 0 <= a < b <= len(text)
                    or text[a:b] != span.get('literal')):
                raise ValueError('Quarantine literal span differs')


def parent_rows(manifest, kept, quarantined):
    parent = manifest.get('source_manifest')
    decisions_manifest = manifest.get('decisions_manifest')
    if (manifest.get('version') != VERSION or not isinstance(parent, dict) or parent.get('version') != PARENT
            or records_hash([parent]) != manifest.get('source_manifest_sha256')
            or not isinstance(decisions_manifest, dict)
            or decisions_manifest.get('version') != DECISION_VERSION
            or records_hash([decisions_manifest]) != manifest.get('decisions_manifest_sha256')
            or decisions_manifest.get('source_manifest_sha256') != manifest.get('source_manifest_sha256')
            or decisions_manifest.get('source_observations_sha256') != parent.get('files', {}).get('observations.jsonl')
            or decisions_manifest.get('reviewed_at') != manifest.get('reviewed_at')
            or not isinstance(quarantined, list) or not quarantined
            or records_hash(quarantined) != manifest.get('files', {}).get(SIDECAR)):
        raise ValueError('Quarantine parent lineage or sidecar binding differs')
    total = manifest.get('source_rows')
    if type(total) is not int or total != len(kept)+len(quarantined):
        raise ValueError('Quarantine source row count differs')
    positions, identities, decisions = {}, set(), set()
    for item in quarantined:
        position, row, decision = item['source_index'], item['observation'], item['decision']
        if type(position) is not int or not 0 <= position < total or position in positions:
            raise ValueError('Quarantine original position is invalid or repeated')
        validate_decision(row, decision, manifest['reviewed_at'])
        if row['audit_id'] in identities or decision['decision_id'] in decisions:
            raise ValueError('Duplicate quarantined observation or decision')
        positions[position] = row; identities.add(row['audit_id']); decisions.add(decision['decision_id'])
    if (len({r['audit_id'] for r in kept}) != len(kept) or identities & {r['audit_id'] for r in kept}
            or sorted(decisions) != manifest.get('decision_ids')
            or records_hash(sorted((item['decision'] for item in quarantined), key=lambda d: d['audit_id']))
            != decisions_manifest.get('files', {}).get('decisions.jsonl')):
        raise ValueError('Quarantine membership or decision coverage differs')
    retained = iter(kept)
    restored = [deepcopy(positions[i] if i in positions else next(retained)) for i in range(total)]
    if records_hash(restored) != parent.get('files', {}).get('observations.jsonl'):
        raise ValueError('Reconstructed quarantine parent observations differ')
    return parent, restored
