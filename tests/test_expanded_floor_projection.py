from copy import deepcopy
import hashlib

import pytest

from apartments import expanded_floor_projection as f
from apartments import floor_label_projection as old
from apartments.reviewed_cohort_quarantine import records_hash, sha

AS_OF = '2026-09-19T23:00:00Z'


def extend(parent, rows, original_changes):
    policy = {'excluded_buildings': deepcopy(parent['excluded_buildings']),
        'building_floor_evidence': deepcopy(parent['building_floor_evidence']),
        'parent_interpreted_at': parent['interpreted_at'], 'excluded_units': [], 'floor_masks': []}
    return bundle(parent, rows, original_changes, policy)


def bundle(parent, rows, original_changes, policy):
    projected = [f.project_row(row, change, policy, AS_OF) for row, change in zip(rows, original_changes, strict=True)]
    changes = [f.make_change(i, row, change) for i, (row, change) in enumerate(zip(rows, original_changes, strict=True))]
    manifest = {'version': f.VERSION, 'source_manifest': parent, 'source_manifest_sha256': records_hash([parent]),
        'policy': policy, 'policy_sha256': sha(policy), 'interpreted_at': AS_OF, 'source_rows': len(rows),
        'files': {f.SIDECAR: records_hash(changes), 'observations.jsonl': records_hash(projected)}}
    return manifest, projected, changes


def example(label='601', advertised=None, count=12, excluded=False):
    row = {'audit_id': 'a', 'unit_id': 'u', 'source_listing_id': '12', 'capture_ids': [1, 2],
           'building': 'b', 'known_at': '2026-09-18T00:00:00Z', 'advertised_floor': advertised}
    captures = [{**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'known_at')},
        'capture_id': cid, 'source_collected_at': row['known_at'], 'raw_listing_sha256': 'a'*64,
        'body_sha256': 'b'*64, 'literal': label, 'candidate_floor': old.candidate(label),
        'source_path': '/propertyDetails/address/displayUnit'} for cid in (1, 2)]
    building = [] if count is None else [{'floor_count': count, 'source_collected_at': row['known_at'],
        'source_path': '/floorCount', 'source_url': 'https://streeteasy.com/building/b',
        'body_sha256': 'c'*64, 'raw_building_sha256': 'd'*64}]
    as_of = '2026-09-19T12:00:00Z'
    policy = {'excluded_buildings': ['b'] if excluded else [], 'building_floor_evidence': {'b': building},
        'parent_interpreted_at': as_of, 'excluded_units': [], 'floor_masks': []}
    result = old.project_row(row, captures, policy['excluded_buildings'], building, as_of)
    change = {'source_index': 0, 'source_row_sha256': sha(row), 'listed_floor_was_present': False,
        'before_listed_floor': None, 'captures': captures}
    ancestor = {'version': old.PARENT, 'files': {'observations.jsonl': records_hash([row])}}
    parent = {'version': old.VERSION, 'source_manifest': ancestor,
        'source_manifest_sha256': records_hash([ancestor]), 'source_rows': 1, 'interpreted_at': as_of,
        'excluded_buildings': policy['excluded_buildings'], 'building_floor_evidence': policy['building_floor_evidence'],
        'files': {old.SIDECAR: records_hash([change]), 'observations.jsonl': records_hash([result])}}
    return parent, result, change, policy


def mask_for(row, change):
    text = 'Sunny apartment. Photos are of the same unit on the 3rd floor. Please contact us.'
    literal = 'Photos are of the same unit on the 3rd floor.'
    start = text.index(literal)
    record = {'schema_version': 1, 'action': 'edit', 'id': 'correction-1',
        'recorded_at': '2026-09-19T22:00:00Z', 'author': 'reviewer', 'reason': 'reference photo',
        'previous_hash': '0'*64, 'target': {'source': 'streeteasy', 'source_listing_id': row['source_listing_id'],
        'version_id': sha(row)}, 'validity': {'all_time': True},
        'patch': [{'op': 'test', 'path': '/advertised_floor', 'value': 3},
                  {'op': 'replace', 'path': '/advertised_floor', 'value': None}]}
    record['hash'] = sha(record)
    return {'audit_id': row['audit_id'], 'source_row_sha256': sha(row), 'reason': 'Reviewed reference photo',
        'reviewed_at': '2026-09-19T21:00:00Z', 'before_advertised_floor': 3, 'correction_record': record,
        'captures': [{**cap, 'source_path': '/description', 'description': text,
            'description_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'spans': [{'start': start, 'end': start+len(literal), 'literal': literal}]} for cap in change['captures']]}


def test_public_projection_and_inverse_remain_detached_with_readonly_replay():
    parent, row, change, policy = example()
    saved = deepcopy((parent, row, change, policy))
    view = f._project_row_view(row, change, policy, AS_OF)
    result = f.project_row(row, change, policy, AS_OF)
    assert result == view and (parent, row, change, policy) == saved
    result['capture_ids'].append(99)
    result['floor_label_provenance']['status'] = 'changed'
    assert (parent, row, change, policy) == saved
    manifest, rows, changes = bundle(parent, [row], [change], policy)
    frozen = deepcopy((manifest, rows, changes))
    _, restored = f.parent_rows(manifest, rows, changes)
    restored[0]['capture_ids'].append(99)
    restored[0]['floor_label_provenance']['status'] = 'changed'
    assert (manifest, rows, changes) == frozen


@pytest.mark.parametrize('label,rule,want', [
    ('601', 'numeric_hundreds', 6), ('1404', 'numeric_hundreds', 14), ('#906', 'numeric_hundreds', 9),
    ('S15K', 'north_south_wing_prefix', 15), ('N3D', 'north_south_wing_prefix', 3),
    ('4FE', 'front_rear_suffix', 4), ('3RW', 'front_rear_suffix', 3),
    ('11THFLOOR', 'explicit_ordinal_label', 11), ('2NDFL', 'explicit_ordinal_label', 2),
    (' #3d ', old.RULE, 3),
])
def test_named_rules(label, rule, want):
    assert f.candidate(label) == (rule, want)


@pytest.mark.parametrize('label', [None, '', '1BR', '1BEDS', 'PHD', '30', '01', '0301', '10001',
    'A3', 'E3D', 'S3', 'S03D', '3ABC', '0FE', '103FE', '3-4', '4R/5R', 'GROUND'])
def test_unsupported_labels_remain_unknown(label):
    assert f.candidate(label) == (None, None)


def test_new_candidate_and_inverse_exact_immutable_inputs():
    parent, row, change, policy = example()
    before = deepcopy((parent, row, change, policy))
    m, rows, changes = bundle(parent, [row], [change], policy)
    assert rows[0]['listed_floor'] == 6
    assert rows[0]['advertised_floor'] is None
    assert rows[0]['floor_label_provenance'] == row['floor_label_provenance']
    assert rows[0]['label_derived_floor'] == row['label_derived_floor']
    assert f.parent_rows(m, rows, changes) == (parent, [row])
    assert (parent, row, change, policy) == before
    assert bundle(parent, [row], [change], policy) == (m, rows, changes)


@pytest.mark.parametrize('label', ['601', 'S6D', '6FE', '6THFL'])
@pytest.mark.parametrize('count,status', [(None, 'missing_building_floor_count'),
    (5, 'above_captured_building_floor_count'), (6, 'label_proxy')])
def test_new_rules_require_building_compatibility(label, count, status):
    _, row, change, policy = example(label=label, count=count)
    result = f.project_row(row, change, policy, AS_OF)
    assert result[f.FIELD]['status'] == status
    assert result.get('listed_floor') == (6 if status == 'label_proxy' else None)


@pytest.mark.parametrize('advertised', [0, 2, 4])
def test_explicit_source_is_preserved_despite_conflicting_candidate(advertised):
    _, row, change, policy = example(label='1RE', advertised=advertised)
    result = f.project_row(row, change, policy, AS_OF)
    assert result[f.FIELD]['status'] == 'existing_floor_preserved'
    assert result['advertised_floor'] == advertised
    assert result.get('listed_floor') is None


def test_existing_proxy_preserved():
    _, row, change, policy = example(label='3D', count=None)
    result = f.project_row(row, change, policy, AS_OF)
    assert result['listed_floor'] == 3
    assert result[f.FIELD]['status'] == 'existing_floor_preserved'


@pytest.mark.parametrize('kind', ['building', 'unit'])
def test_reviewed_numbering_exclusions_remain_unknown(kind):
    _, row, change, policy = example(excluded=kind == 'building')
    if kind == 'unit':
        policy['excluded_units'] = ['u']
    result = f.project_row(row, change, policy, AS_OF)
    assert result.get('listed_floor') is None
    assert result[f.FIELD]['status'] == f'reviewed_{kind}_numbering_excluded'


def test_mask_clears_only_reviewed_photo_claim_and_recovers_label():
    parent, row, change, policy = example(advertised=3)
    policy['floor_masks'] = [mask_for(row, change)]
    m, rows, changes = bundle(parent, [row], [change], policy)
    assert rows[0]['advertised_floor'] is None and rows[0]['listed_floor'] == 6
    assert rows[0][f.FIELD]['correction_id'] == 'correction-1'
    assert f.parent_rows(m, rows, changes) == (parent, [row])


@pytest.mark.parametrize('mutation', ['source_hash', 'missing_capture', 'typed_capture', 'body_hash',
    'description_hash', 'span', 'partial_sentence', 'clock', 'correction_scope', 'correction_patch',
    'correction_clock', 'correction_hash', 'mask_value', 'duplicate_mask'])
def test_mask_requires_exact_review_and_ledger_witness(mutation):
    _, row, change, policy = example(advertised=3)
    mask = mask_for(row, change)
    policy['floor_masks'] = [mask]
    if mutation == 'source_hash': mask['source_row_sha256'] = 'a'*64
    elif mutation == 'missing_capture': mask['captures'].pop()
    elif mutation == 'typed_capture': mask['captures'][0]['capture_id'] = '1'
    elif mutation == 'body_hash': mask['captures'][0]['body_sha256'] = 'd'*64
    elif mutation == 'description_hash': mask['captures'][0]['description'] += '!'
    elif mutation == 'span': mask['captures'][0]['spans'][0]['start'] += 1
    elif mutation == 'partial_sentence':
        span = mask['captures'][0]['spans'][0]; span['start'] += 10; span['literal'] = span['literal'][10:]
    elif mutation == 'clock': mask['reviewed_at'] = '2026-09-17T00:00:00Z'
    elif mutation == 'correction_scope': mask['correction_record']['target']['source_listing_id'] = 'other'
    elif mutation == 'correction_patch': mask['correction_record']['patch'][1]['path'] = '/bedrooms'
    elif mutation == 'correction_clock': mask['correction_record']['recorded_at'] = '2026-09-20T00:00:00Z'
    elif mutation == 'correction_hash': mask['correction_record']['hash'] = 'a'*64
    elif mutation == 'mask_value': mask['before_advertised_floor'] = 4
    elif mutation == 'duplicate_mask': policy['floor_masks'].append(deepcopy(mask))
    with pytest.raises(ValueError): f.project_row(row, change, policy, AS_OF)


@pytest.mark.parametrize('mutation', ['row_value', 'capture_identity', 'capture_type', 'capture_literal',
    'capture_membership', 'candidate_type', 'old_provenance', 'original_hash', 'early_clock', 'repeat'])
def test_original_capture_and_projection_are_revalidated(mutation):
    _, row, change, policy = example()
    as_of = AS_OF
    if mutation == 'row_value': row['bedrooms'] = 10
    elif mutation == 'capture_identity': change['captures'][0]['source_listing_id'] = 12
    elif mutation == 'capture_type': change['captures'][0]['capture_id'] = True
    elif mutation == 'capture_literal': change['captures'][0]['literal'] = '602'
    elif mutation == 'capture_membership': change['captures'].pop()
    elif mutation == 'candidate_type': change['captures'][0]['candidate_floor'] = False
    elif mutation == 'old_provenance': row['floor_label_provenance']['status'] = 'label_proxy'
    elif mutation == 'original_hash': change['source_row_sha256'] = 'd'*64
    elif mutation == 'early_clock': as_of = '2026-09-19T00:00:00Z'
    elif mutation == 'repeat': row[f.FIELD] = {}
    with pytest.raises(ValueError): f.project_row(row, change, policy, as_of)


@pytest.mark.parametrize('mutation', ['new_row', 'sidecar', 'policy', 'parent_context', 'parent_hash',
    'order', 'before_presence', 'original_sidecar_hash', 'unattached_mask'])
def test_inverse_rejects_tampering_even_with_updated_artifact_hashes(mutation):
    parent, row, change, policy = example()
    m, rows, changes = bundle(parent, [row], [change], policy)
    if mutation == 'new_row': rows[0]['listed_floor'] = 7
    elif mutation == 'sidecar': changes[0]['source_row_sha256'] = 'a'*64
    elif mutation == 'policy': m['policy_sha256'] = 'a'*64
    elif mutation == 'parent_context':
        m['policy']['excluded_buildings'] = ['other']; m['policy_sha256'] = sha(m['policy'])
    elif mutation == 'parent_hash': m['source_manifest_sha256'] = 'a'*64
    elif mutation == 'order': changes[0]['source_index'] = True
    elif mutation == 'before_presence': changes[0]['before']['listed_floor']['present'] = 0
    elif mutation == 'original_sidecar_hash':
        m['source_manifest']['files'][old.SIDECAR] = 'a'*64
        m['source_manifest_sha256'] = records_hash([m['source_manifest']])
    elif mutation == 'unattached_mask':
        m['policy']['floor_masks'] = [{'audit_id': 'unattached'}]; m['policy_sha256'] = sha(m['policy'])
    m['files'][f.SIDECAR] = records_hash(changes)
    m['files']['observations.jsonl'] = records_hash(rows)
    with pytest.raises(ValueError): f.parent_rows(m, rows, changes)
