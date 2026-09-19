"""Exact inverse for reviewed elevator extraction corrections after quarantine."""
from copy import deepcopy

from .corrections import instant
from .reviewed_cohort_quarantine import VERSION as PARENT, records_hash, sha

VERSION = 'reviewed-elevator-negation-projection-v1'
SIDECAR = 'elevator-corrections.jsonl'


def corrected_row(row, edit, as_of):
    after = edit['patch'][-1].get('value')
    expected_patch = [{'op': 'test', 'path': '/elevator', 'value': True},
                      {'op': 'replace', 'path': '/elevator', 'value': after}]
    target = {'source': 'streeteasy', 'source_listing_id': row['source_listing_id'], 'version_id': sha(row)}
    if (row.get('elevator') is not True or (after is not False and after is not None)
            or edit.get('action') != 'edit' or edit.get('patch') != expected_patch
            or edit.get('target') != target or edit.get('validity') != {'all_time': True}
            or not isinstance(edit.get('id'), str) or not edit['id']
            or instant(edit['recorded_at']) < instant(row['known_at'])
            or instant(edit['recorded_at']) > instant(as_of)
            or row.get('analysis_price_basis') != 'historical_initial_own_advertisement_ask'):
        raise ValueError('Elevator edit scope, source value, identity or clocks differ')
    result = deepcopy(row)
    result['elevator'] = after
    result.setdefault('attribute_review_history', []).append({
        **deepcopy(edit), 'audit_id': row['audit_id'], 'unit_id': row['unit_id'],
        'source_row_sha256': sha(row), 'before_elevator': True, 'after_elevator': after})
    return result


def parent_rows(manifest, rows, changes):
    parent = manifest.get('source_manifest')
    if (manifest.get('version') != VERSION or not isinstance(parent, dict)
            or parent.get('version') != PARENT or records_hash([parent]) != manifest.get('source_manifest_sha256')
            or not isinstance(changes, list) or not changes
            or records_hash(changes) != manifest.get('files', {}).get(SIDECAR)
            or len(rows) != manifest.get('source_rows')):
        raise ValueError('Elevator correction parent or sidecar binding differs')
    overlay = manifest.get('overlay', {})
    active = overlay.get('active_ids', [])
    if not active or len(set(active)) != len(active): raise ValueError('Distinct active edits required')
    restored = deepcopy(rows)
    seen, positions = set(), set()
    for change in changes:
        index, before, edit = change['source_index'], change['observation'], change['edit']
        if (type(index) is not int or not 0 <= index < len(rows) or index in positions
                or edit['id'] not in active or edit['id'] in seen
                or rows[index] != corrected_row(before, edit, overlay['corrections_as_of'])):
            raise ValueError('Elevator correction membership or exact row transformation differs')
        positions.add(index); seen.add(edit['id']); restored[index] = deepcopy(before)
    if seen != set(active) or records_hash(restored) != parent['files']['observations.jsonl']:
        raise ValueError('Elevator inverse does not restore every exact parent row in order')
    return parent, restored
