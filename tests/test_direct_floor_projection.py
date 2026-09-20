from copy import deepcopy

import pytest

from apartments import direct_floor_projection as projection
from apartments.reviewed_cohort_quarantine import records_hash, sha


def extend(parent, rows):
    """Append one direct-floor addition to a complete synthetic source lineage."""
    before = rows[2]
    floor = 2
    witnesses = [{'capture_id': cid, 'source_collected_at': before['known_at'],
        'raw_listing_sha256': 'b'*64, 'description_sha256': 'c'*64,
        'claims': [{'attribute': 'advertised_floor', 'value': floor,
            'source_path': '/description', 'rule': 'explicit-dwelling-floor-offer-v1',
            'start': 0, 'end': 5, 'literal': 'floor'}]} for cid in before['capture_ids']]
    case = {'audit_id': before['audit_id'], 'source_listing_id': before['source_listing_id'],
        'source_row_sha256': sha(before), 'action': 'add_explicit_advertised_floor',
        'advertised_floor': floor, 'proposed_fields': dict.fromkeys(projection.FIELDS, floor),
        'witnesses': witnesses}
    policy = {'version': 'prepared-direct-floor-additions-v1', 'applied': False,
        'source_manifest_sha256': records_hash([parent]), 'cases': [case]}
    clock = '2026-09-20T00:00:00Z'
    after = deepcopy(rows)
    after[2] = projection.apply_case(before, case, clock, records_hash([policy]))
    changes = [{'source_index': 2, 'before': deepcopy(before), 'case': case}]
    manifest = {'version': projection.VERSION, 'source_manifest': parent,
        'source_manifest_sha256': records_hash([parent]), 'policy': policy,
        'policy_sha256': records_hash([policy]), 'reviewed_at': clock, 'source_rows': len(rows),
        'files': {'observations.jsonl': records_hash(after), projection.SIDECAR: records_hash(changes)}}
    return manifest, after, changes


@pytest.fixture
def example():
    row = {'audit_id': 'a', 'source_listing_id': '123', 'unit_id': 'u',
        'known_at': '2026-09-18T00:00:00Z', 'capture_ids': [12],
        'listed_floor': None, 'advertised_floor': None, 'label_derived_floor': None,
        'physical_floor': None, 'asking_rent': 3000,
        'expanded_floor_provenance': {'status': 'unsupported_label_syntax'}}
    witness = {'capture_id': 12, 'source_collected_at': '2026-09-17T00:00:00Z',
        'raw_listing_sha256': 'a'*64, 'description_sha256': 'b'*64,
        'claims': [{'attribute': 'advertised_floor', 'value': 2, 'source_path': '/description',
                    'rule': 'explicit-dwelling-floor-offer-v1', 'start': 0, 'end': 5, 'literal': 'floor'}]}
    case = {'audit_id': 'a', 'source_listing_id': '123', 'source_row_sha256': sha(row),
        'action': 'add_explicit_advertised_floor', 'advertised_floor': 2,
        'proposed_fields': {'listed_floor': 2, 'advertised_floor': 2}, 'witnesses': [witness]}
    parent = {'version': projection.residual_scope_projection.VERSION,
              'files': {'observations.jsonl': records_hash([row])}}
    policy = {'version': 'prepared-direct-floor-additions-v1', 'applied': False,
              'source_manifest_sha256': records_hash([parent]), 'cases': [case]}
    clock = '2026-09-20T00:00:00Z'
    after = projection.apply_case(row, case, clock, records_hash([policy]))
    changes = [{'source_index': 0, 'before': row, 'case': case}]
    manifest = {'version': projection.VERSION, 'source_manifest': parent,
        'source_manifest_sha256': records_hash([parent]), 'policy': policy,
        'policy_sha256': records_hash([policy]), 'reviewed_at': clock, 'source_rows': 1,
        'files': {'observations.jsonl': records_hash([after]), projection.SIDECAR: records_hash(changes)}}
    return manifest, [after], changes


def test_roundtrip_and_no_mutation(example):
    m, rows, changes = example
    saved = deepcopy(example)
    parent, restored = projection.parent_rows(m, rows, changes)
    assert parent == m['source_manifest'] and restored == [changes[0]['before']]
    assert example == saved
    restored[0]['asking_rent'] = 1
    assert changes[0]['before']['asking_rent'] == 3000


@pytest.mark.parametrize('field,value', [('asking_rent', 1), ('physical_floor', 2),
    ('label_derived_floor', 2), ('listed_floor', 3), ('advertised_floor', None)])
def test_rehashed_nonpermitted_edit_rejected(example, field, value):
    m, rows, changes = example
    rows[0][field] = value
    m['files']['observations.jsonl'] = records_hash(rows)
    with pytest.raises(ValueError, match='forward replay'):
        projection.parent_rows(m, rows, changes)


@pytest.mark.parametrize('mutation', ['known_floor', 'masked', 'bool_floor', 'typed_capture',
    'duplicate_capture', 'missing_capture', 'future_capture', 'bad_claim'])
def test_decision_rejects_unsafe_additions(example, mutation):
    m, _, changes = example
    row, case = deepcopy(changes[0]['before']), deepcopy(changes[0]['case'])
    if mutation == 'known_floor': row['advertised_floor'] = 4
    if mutation == 'masked': row['expanded_floor_provenance']['status'] = 'reviewed_mask'
    if mutation == 'bool_floor': case['advertised_floor'] = True
    if mutation == 'typed_capture': case['witnesses'][0]['capture_id'] = '12'
    if mutation == 'duplicate_capture': case['witnesses'] *= 2
    if mutation == 'missing_capture': case['witnesses'] = []
    if mutation == 'future_capture': case['witnesses'][0]['source_collected_at'] = '2027-01-01T00:00:00Z'
    if mutation == 'bad_claim': case['witnesses'][0]['claims'][0]['value'] = 3
    case['source_row_sha256'] = sha(row)
    with pytest.raises(ValueError):
        projection.apply_case(row, case, m['reviewed_at'], m['policy_sha256'])


def test_rehashed_unchanged_row_tampering_rejected(example):
    m, rows, changes = example
    # A sibling edit must fail even if the outer artifact hash is recomputed.
    sibling = {'audit_id': 'sibling', 'asking_rent': 4500}
    m['source_manifest']['files']['observations.jsonl'] = records_hash([changes[0]['before'], sibling])
    m['source_manifest_sha256'] = records_hash([m['source_manifest']])
    m['policy']['source_manifest_sha256'] = m['source_manifest_sha256']
    m['policy_sha256'] = records_hash([m['policy']])
    rows[0] = projection.apply_case(changes[0]['before'], changes[0]['case'], m['reviewed_at'], m['policy_sha256'])
    rows.append({**sibling, 'asking_rent': 1})
    m['source_rows'] = 2
    m['files']['observations.jsonl'] = records_hash(rows)
    with pytest.raises(ValueError, match='parent reconstruction'):
        projection.parent_rows(m, rows, changes)
