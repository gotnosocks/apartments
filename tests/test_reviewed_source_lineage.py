from copy import deepcopy
import hashlib

import pytest

from apartments.corrections import canonical
from apartments.reviewed_source_lineage import FLOOR, LAUNDRY, REFRESHED, manifest_hash, source_lineage


def row_hash(row):
    return hashlib.sha256(canonical(row).encode()).hexdigest()


def observations_hash(rows):
    return hashlib.sha256(''.join(canonical(r)+'\n' for r in rows).encode()).hexdigest()


def revise(parent, rows, version, field, identity, index=0):
    revised = deepcopy(rows)
    row = revised[index]
    before = row[field]
    patch = [{'op': 'test', 'path': '/'+field, 'value': before},
             {'op': 'replace', 'path': '/'+field, 'value': None}]
    change = {'id': identity, 'audit_id': row['audit_id'], 'unit_id': row['unit_id'],
              'source_row_sha256': row_hash(row), 'before_'+field: before, 'after_'+field: None,
              'patch': patch, 'changes': patch[1:], 'validity': {'all_time': True},
              'target': {'source': 'streeteasy', 'source_listing_id': row['source_listing_id'],
                         'version_id': row_hash(row)}, 'recorded_at': '2026-09-19T00:00:00Z'}
    row[field] = None
    row.setdefault('attribute_review_history', []).append(change)
    manifest = {'version': version, 'source_manifest': parent,
                'source_manifest_sha256': manifest_hash(parent),
                'files': {'observations.jsonl': observations_hash(revised)},
                'overlay': {'active_ids': [identity], 'corrections_as_of': '2026-09-19T01:00:00Z'}}
    return manifest, revised


def fixture():
    rows = [{'audit_id': 'a', 'unit_id': 'u', 'source_listing_id': '123',
             'known_at': '2026-09-18T00:00:00Z', 'asking_rent': 3000,
             'laundry_type': 'in_building', 'advertised_floor': 3},
            {'audit_id': 'b', 'unit_id': 'v', 'source_listing_id': '124',
             'known_at': '2026-09-18T00:00:00Z', 'asking_rent': 4000,
             'laundry_type': 'in_unit', 'advertised_floor': 5,
             'attribute_review_history': []}]
    original = {'version': REFRESHED, 'files': {'observations.jsonl': observations_hash(rows)}}
    laundry, lr = revise(original, rows, LAUNDRY, 'laundry_type', 'laundry')
    floor, fr = revise(laundry, lr, FLOOR, 'advertised_floor', 'floor', index=1)
    return original, floor, fr


def test_reconstructs_exact_parent_and_preserves_inputs_and_empty_history():
    original, manifest, rows = fixture()
    saved = deepcopy(rows)
    assert source_lineage(manifest, rows) == original
    assert rows == saved


@pytest.mark.parametrize('fault', ['price', 'clock', 'unit', 'order', 'before', 'missing_patch',
                                  'extra_change', 'parent_hash', 'lineage', 'duplicate_id',
                                  'recorded_before_source', 'recorded_after_cutoff'])
def test_lineage_rejects_unintended_changes_even_with_rehashed_output(fault):
    _, manifest, rows = fixture()
    change = rows[1]['attribute_review_history'][-1]
    if fault == 'price': rows[0]['asking_rent'] += 1
    elif fault == 'clock': rows[0]['known_at'] = '2026-09-17T00:00:00Z'
    elif fault == 'unit': rows[1]['unit_id'] = 'different'
    elif fault == 'order': rows.reverse()
    elif fault == 'before': change['before_advertised_floor'] = 4
    elif fault == 'missing_patch': rows[1]['attribute_review_history'] = []
    elif fault == 'extra_change': change['changes'].append({'op': 'replace', 'path': '/asking_rent', 'value': 1})
    elif fault == 'parent_hash': manifest['source_manifest_sha256'] = 'wrong'
    elif fault == 'lineage':
        manifest['source_manifest']['version'] = REFRESHED
        manifest['source_manifest_sha256'] = manifest_hash(manifest['source_manifest'])
    elif fault == 'duplicate_id': manifest['overlay']['active_ids'].append('floor')
    elif fault == 'recorded_before_source': change['recorded_at'] = '2026-09-17T00:00:00Z'
    elif fault == 'recorded_after_cutoff': change['recorded_at'] = '2026-09-20T00:00:00Z'
    manifest['files']['observations.jsonl'] = observations_hash(rows)
    with pytest.raises(ValueError):
        source_lineage(manifest, rows)


def test_unexpected_expanded_floor_sidecar_is_rejected_for_older_sources():
    original, manifest, rows = fixture()
    with pytest.raises(ValueError, match='Unexpected expanded floor sidecar'):
        source_lineage(manifest, rows, expanded_floor_changes=[])
