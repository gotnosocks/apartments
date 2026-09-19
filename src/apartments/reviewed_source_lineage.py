"""Verify bounded feature corrections back to their exact refreshed source.

Reconstruction verifies every row, its ordering and all unchanged fields against
the parent observations hash. It never treats a nested manifest alone as proof
that a derived dataset preserves the description archive's source identities.
"""
from copy import deepcopy
import hashlib
import math

from .corrections import canonical, instant
from . import laundry_floor_split, reviewed_cohort_quarantine, elevator_corrections

REFRESHED = 'reviewed-capture-refreshed-analysis-v1'
LAUNDRY = 'reviewed-laundry-negation-projection-v1'
FLOOR = 'reviewed-floor-conflict-projection-v1'
VERSIONS = {LAUNDRY, FLOOR, laundry_floor_split.VERSION, reviewed_cohort_quarantine.VERSION, elevator_corrections.VERSION}
_PARENTS = {FLOOR: LAUNDRY, LAUNDRY: REFRESHED}
_FIELDS = {FLOOR: 'advertised_floor', LAUNDRY: 'laundry_type'}


def manifest_hash(value):
    return hashlib.sha256((canonical(value)+'\n').encode()).hexdigest()


def source_lineage(manifest, rows, *, quarantined=None, elevator_changes=None):
    """Return the refreshed ancestor after verifying every bounded inverse patch.

    Existing reviewed history is preserved. Only the final appended history
    entry and the named masked feature may differ at each projection stage.
    """
    if manifest.get('version') not in VERSIONS | {REFRESHED}:
        raise ValueError('Unsupported reviewed source lineage')
    current = deepcopy(rows)
    if manifest['version'] == elevator_corrections.VERSION:
        manifest, current = elevator_corrections.parent_rows(manifest, current, elevator_changes)
    elif elevator_changes is not None:
        raise ValueError('Unexpected elevator correction sidecar for this source version')
    if manifest['version'] == reviewed_cohort_quarantine.VERSION:
        manifest, current = reviewed_cohort_quarantine.parent_rows(manifest, current, quarantined)
    elif quarantined is not None:
        raise ValueError('Unexpected quarantine sidecar for this source version')
    if manifest['version'] == laundry_floor_split.VERSION:
        manifest, current = laundry_floor_split.parent_rows(manifest, current)
    while manifest['version'] in _PARENTS:
        version = manifest['version']
        parent = manifest.get('source_manifest')
        if (not isinstance(parent, dict) or parent.get('version') != _PARENTS[version]
                or manifest_hash(parent) != manifest.get('source_manifest_sha256')):
            raise ValueError('Reviewed correction parent lineage or hash differs')
        active = manifest.get('overlay', {}).get('active_ids', [])
        if not active or len(active) != len(set(active)):
            raise ValueError('Distinct active correction IDs required')
        remaining = set(active)
        field = _FIELDS[version]
        checksum = hashlib.sha256()
        for row in current:
            history = row.get('attribute_review_history', [])
            matches = [i for i, change in enumerate(history) if change.get('id') in active]
            if matches:
                if matches != [len(history)-1]:
                    raise ValueError('Correction must be the final appended review entry')
                change = history[-1]
                before = change.get('before_'+field)
                valid_before = (before == 'in_building' if version == LAUNDRY else
                    type(before) in (int, float) and math.isfinite(before) and before > 0)
                expected_patch = [{'op': 'test', 'path': '/'+field, 'value': before},
                                  {'op': 'replace', 'path': '/'+field, 'value': None}]
                expected_target = {'source': 'streeteasy', 'source_listing_id': row['source_listing_id'],
                                   'version_id': change.get('source_row_sha256')}
                if (change['id'] not in remaining or not valid_before or field not in row
                        or row[field] is not None or change.get('after_'+field) is not None
                        or 'after_'+field not in change or change.get('patch') != expected_patch
                        or change.get('changes') != expected_patch[1:]
                        or change.get('target') != expected_target
                        or change.get('validity') != {'all_time': True}
                        or any(change.get(k) != row[k] for k in ('audit_id', 'unit_id'))
                        or instant(change['recorded_at']) < instant(row['known_at'])
                        or instant(change['recorded_at']) > instant(manifest['overlay']['corrections_as_of'])):
                    raise ValueError('Correction scope, identity, masked value or clock differs')
                remaining.remove(change['id'])
                row[field] = before
                history.pop()
                if not history:
                    del row['attribute_review_history']
                expected = change['source_row_sha256']
                if hashlib.sha256(canonical(row).encode()).hexdigest() != expected:
                    # setdefault preserves an explicitly present empty parent
                    # history. Both possible representations are hash-checked.
                    if not history:
                        row['attribute_review_history'] = []
                    if hashlib.sha256(canonical(row).encode()).hexdigest() != expected:
                        raise ValueError('Reconstructed reviewed source row differs')
            checksum.update((canonical(row)+'\n').encode())
        if remaining or checksum.hexdigest() != parent.get('files', {}).get('observations.jsonl'):
            raise ValueError('Reconstructed parent observations or correction coverage differs')
        manifest = parent
    return manifest
