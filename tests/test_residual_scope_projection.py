from copy import deepcopy
import hashlib

import pytest

from apartments import residual_scope_projection as q
from apartments.corrections import canonical

CLOCK = '2026-09-20T00:00:00Z'
SENTINEL = 'scope-excluded'


def add_scope_row(rows):
    """Add before constructing ancestor fixtures, so every ancestor binds it."""
    result = deepcopy(rows)
    result.append({**deepcopy(rows[-1]), 'audit_id': SENTINEL, 'unit_id': 'scope-excluded-unit',
        'source_listing_id': 'scope-excluded-ad', 'capture_ids': ['scope-excluded-capture'],
        'capture_id': None, 'period': '2018-01-01',
        'analysis_price_basis': 'historical_initial_own_advertisement_ask'})
    return result


def decision_for(row, captures, action='quarantine_nonresidential'):
    text = 'Commercial office space.\u2028This is not a residential apartment.'
    evidence = [{**deepcopy(c), 'source_path': '/description', 'description': text,
        'description_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'spans': [{'start': 0, 'end': 24, 'literal': text[:24]}]} for c in captures]
    d = {**{k: row[k] for k in q.IDENTITIES}, 'action': action,
        'reason': 'Own advertisement offers commercial office space', 'reviewer': 'test reviewer',
        'reviewed_at': CLOCK, 'source_row_sha256': q.sha(row),
        'source_captures': deepcopy(captures), 'evidence': evidence}
    d['decision_id'] = q.sha(d)
    return d


def bundle(parent, rows, decisions):
    by_id = {q.decision_sort_key(d): d for d in decisions}
    kept, changes = [], []
    for index, row in enumerate(rows):
        decision = by_id.get(q.decision_sort_key(row))
        if decision is None:
            kept.append(deepcopy(row))
        else:
            changes.append({'source_index': index, 'observation': deepcopy(row), 'decision': deepcopy(decision)})
    dm = {'version': q.DECISION_VERSION, 'reviewed_at': CLOCK,
        'source_manifest_sha256': q.records_hash([parent]),
        'source_observations_sha256': parent['files']['observations.jsonl'],
        'files': {'decisions.jsonl': q.records_hash(sorted(decisions, key=q.decision_sort_key))}}
    manifest = {'version': q.VERSION, 'source_manifest': deepcopy(parent),
        'source_manifest_sha256': q.records_hash([parent]), 'source_rows': len(rows),
        'reviewed_at': CLOCK, 'decisions_manifest': dm, 'decisions_manifest_sha256': q.records_hash([dm]),
        'decision_ids': sorted(d['decision_id'] for d in decisions),
        'files': {q.SIDECAR: q.records_hash(changes), 'observations.jsonl': q.records_hash(kept)}}
    return manifest, kept, changes


def extend(parent, rows, expanded_changes):
    matches = [(row, change) for row, change in zip(rows, expanded_changes, strict=True)
               if row['audit_id'] == SENTINEL]
    assert len(matches) == 1
    row, change = matches[0]
    return bundle(parent, rows, [decision_for(row, change['original_change']['captures'])])


def fixture():
    rows, decisions = [], []
    for i in range(4):
        row = {'audit_id': i if i == 0 else str(i), 'unit_id': 'same-unit', 'source_listing_id': str(100+i),
            'capture_ids': [i, str(i)], 'known_at': '2026-09-18T00:00:00Z', 'asking_rent': 3000+i,
            'analysis_price_basis': 'current_capture_gross_ask' if i == 0 else 'historical_initial_own_advertisement_ask'}
        captures = [{**{k: row[k] for k in q.IDENTITIES}, 'capture_id': cid,
            'source_collected_at': row['known_at'], 'known_at': row['known_at'],
            'source_path': '/propertyDetails/address/displayUnit', 'literal': '3D', 'candidate_floor': 3,
            'raw_listing_sha256': 'a'*64, 'body_sha256': 'b'*64} for cid in row['capture_ids']]
        for field in ('floor_label_provenance', 'expanded_floor_provenance'):
            row[field] = {'source_capture_evidence_sha256': q.records_hash(captures),
                'source_known_at': row['known_at'], 'interpreted_at': '2026-09-19T23:00:00Z'}
        rows.append(row)
        if i in (0, 2):
            decisions.append(decision_for(row, captures, list(sorted(q.ACTIONS))[i//2]))
    parent = {'version': q.PARENT, 'interpreted_at': '2026-09-19T23:00:00Z',
        'files': {'observations.jsonl': q.records_hash(rows)}}
    return rows, decisions, bundle(parent, rows, decisions)


def rehash_decision(d):
    d['decision_id'] = q.sha({k: v for k, v in d.items() if k != 'decision_id'})


def test_inverse_exact_order_and_immutability_current_and_historical():
    rows, _, (m, kept, changes) = fixture()
    before = deepcopy((m, kept, changes))
    assert kept == [rows[1], rows[3]]
    assert q.parent_rows(m, kept, changes) == (m['source_manifest'], rows)
    assert (m, kept, changes) == before
    assert q.SIDECAR != 'quarantined.jsonl'


@pytest.mark.parametrize('fault', ['floor', 'order', 'missing', 'duplicate_kept', 'position', 'bool_position',
    'duplicate_position', 'count', 'bool_count', 'parent_version', 'nested', 'parent_hash', 'decision_version',
    'decision_source', 'decision_observations', 'decision_file', 'decision_coverage', 'observations_hash',
    'sidecar_hash', 'review_clock', 'sidecar_footprint', 'empty_sidecar', 'sidecar_row', 'parent_clock'])
def test_inverse_rejects_tampering_even_with_rehashed_mutable_files(fault):
    _, _, (m, kept, changes) = fixture()
    if fault == 'floor': kept[0]['listed_floor'] = 90
    elif fault == 'order': kept.reverse()
    elif fault == 'missing': kept.pop()
    elif fault == 'duplicate_kept': kept[1] = deepcopy(kept[0])
    elif fault == 'position': changes[0]['source_index'] = 1
    elif fault == 'bool_position': changes[0]['source_index'] = False
    elif fault == 'duplicate_position': changes[1]['source_index'] = 0
    elif fault == 'count': m['source_rows'] += 1
    elif fault == 'bool_count': m['source_rows'] = True
    elif fault == 'parent_version': m['source_manifest']['version'] = 'old-source'
    elif fault == 'nested': m['source_manifest']['version'] = q.VERSION
    elif fault == 'parent_hash': m['source_manifest_sha256'] = 'c'*64
    elif fault == 'decision_version': m['decisions_manifest']['version'] = 'old-decisions'
    elif fault == 'decision_source': m['decisions_manifest']['source_manifest_sha256'] = 'c'*64
    elif fault == 'decision_observations': m['decisions_manifest']['source_observations_sha256'] = 'c'*64
    elif fault == 'decision_file': m['decisions_manifest']['files']['decisions.jsonl'] = 'c'*64
    elif fault == 'decision_coverage': m['decision_ids'].pop()
    elif fault == 'review_clock': m['reviewed_at'] = '2020-01-01'
    elif fault == 'sidecar_footprint': changes[0]['extra'] = 1
    elif fault == 'empty_sidecar': changes.clear()
    elif fault == 'sidecar_row': changes[0]['observation']['asking_rent'] += 1
    elif fault == 'parent_clock': m['source_manifest']['interpreted_at'] = '2027-01-01'
    m['decisions_manifest_sha256'] = q.records_hash([m['decisions_manifest']])
    m['files'][q.SIDECAR] = q.records_hash(changes)
    m['files']['observations.jsonl'] = q.records_hash(kept)
    if fault == 'observations_hash': m['files']['observations.jsonl'] = 'c'*64
    if fault == 'sidecar_hash': m['files'][q.SIDECAR] = 'c'*64
    with pytest.raises(ValueError): q.parent_rows(m, kept, changes)


@pytest.mark.parametrize('fault', ['typed_audit', 'bool_id', 'typed_capture', 'duplicate_capture', 'missing_capture',
    'duplicate_source', 'source_hash', 'source_clock', 'evidence_clock', 'future_capture', 'collection_clock',
    'row_hash', 'decision_hash', 'description_hash', 'raw_hash', 'body_hash', 'path', 'source_path', 'span',
    'bool_span', 'empty_spans', 'duplicate_span', 'reviewer', 'reason', 'action', 'early_review',
    'provenance', 'provenance_clock', 'known_clock', 'typed_evidence_ad', 'raw_witness', 'raw_nonobject'])
def test_decision_rejects_unbound_or_inexact_evidence(fault):
    rows, decisions, _ = fixture()
    row, d = rows[0], decisions[0]
    c, s = d['evidence'][0], d['source_captures'][0]
    if fault == 'typed_audit': d['audit_id'] = '0'
    elif fault == 'bool_id': d['audit_id'] = False
    elif fault == 'typed_capture': c['capture_id'] = '0'
    elif fault == 'duplicate_capture': d['evidence'].append(deepcopy(c))
    elif fault == 'missing_capture': d['evidence'].pop()
    elif fault == 'duplicate_source': d['source_captures'].append(deepcopy(s))
    elif fault == 'source_hash': s['raw_listing_sha256'] = 'c'*64
    elif fault == 'source_clock': s['known_at'] = '2026-09-17'
    elif fault == 'evidence_clock': c['known_at'] = '2026-09-17'
    elif fault == 'future_capture': c['known_at'] = s['known_at'] = '2027-01-01'
    elif fault == 'collection_clock': c['source_collected_at'] = s['source_collected_at'] = CLOCK
    elif fault == 'row_hash': d['source_row_sha256'] = 'c'*64
    elif fault == 'description_hash': c['description'] += '!'
    elif fault == 'raw_hash': c['raw_listing_sha256'] = 'c'*64
    elif fault == 'body_hash': c['body_sha256'] = 'c'*64
    elif fault == 'path': c['source_path'] = '/other/description'
    elif fault == 'source_path': s['source_path'] = '/other/displayUnit'
    elif fault == 'span': c['spans'][0]['end'] -= 1
    elif fault == 'bool_span': c['spans'][0]['start'] = False
    elif fault == 'empty_spans': c['spans'] = []
    elif fault == 'duplicate_span': c['spans'].append(deepcopy(c['spans'][0]))
    elif fault in ('reviewer', 'reason'): d[fault] = ''
    elif fault == 'action': d['action'] = 'quarantine_explicit_short_term_offer'
    elif fault == 'early_review': d['reviewed_at'] = '2020-01-01'
    elif fault == 'provenance': row['expanded_floor_provenance']['source_capture_evidence_sha256'] = 'c'*64; d['source_row_sha256'] = q.sha(row)
    elif fault == 'provenance_clock': row['floor_label_provenance']['interpreted_at'] = '2027-01-01'; d['source_row_sha256'] = q.sha(row)
    elif fault == 'known_clock': row['floor_label_provenance']['source_known_at'] = CLOCK; d['source_row_sha256'] = q.sha(row)
    elif fault == 'typed_evidence_ad': c['source_listing_id'] = 100
    elif fault == 'raw_witness': c['raw_listing_json'] = '{}'
    elif fault == 'raw_nonobject': c['raw_listing_json'] = '[]'
    rehash_decision(d)
    if fault == 'decision_hash': d['decision_id'] = 'c'*64
    with pytest.raises(ValueError): q.validate_decision(row, d, CLOCK)


def test_add_and_extend_full_expanded_fixture():
    from tests.test_expanded_floor_projection import example, extend as expand
    from apartments import floor_label_projection as old
    parent, row, change, _ = example()
    # Build the additional row into the complete old projection before expansion.
    base = deepcopy(row)
    for key in old.FIELDS: base.pop(key)
    base.pop('listed_floor', None)
    source_rows = add_scope_row([base])
    captures = deepcopy(change['captures'])
    added_caps = [{**captures[0], **{k: source_rows[-1][k] for k in q.IDENTITIES},
        'capture_id': 'scope-excluded-capture'}]
    second = old.project_row(source_rows[-1], added_caps, [], parent['building_floor_evidence']['b'], parent['interpreted_at'])
    second_change = {**change, 'source_index': 1, 'source_row_sha256': q.sha(source_rows[-1]), 'captures': added_caps}
    parent['source_rows'] = 2
    parent['source_manifest']['files']['observations.jsonl'] = q.records_hash(source_rows)
    parent['source_manifest_sha256'] = q.records_hash([parent['source_manifest']])
    parent['files']['observations.jsonl'] = q.records_hash([row, second])
    parent['files'][old.SIDECAR] = q.records_hash([change, second_change])
    ep, rows, changes = expand(parent, [row, second], [change, second_change])
    m, kept, excluded = extend(ep, rows, changes)
    restored_parent, restored = q.parent_rows(m, kept, excluded)
    assert restored_parent == ep and restored == rows and kept == rows[:1]


@pytest.mark.parametrize('raw,valid', [('{"description":"Office space"}', True),
    ('[]', False), ('not JSON', False), ('{"description":}', False)])
def test_optional_exact_raw_json_witness(raw, valid):
    rows, decisions, _ = fixture()
    row, d = rows[0], decisions[0]
    d['source_captures'][0]['raw_listing_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    d['evidence'][0]['raw_listing_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    d['evidence'][0]['raw_listing_json'] = raw
    for field in ('floor_label_provenance', 'expanded_floor_provenance'):
        row[field]['source_capture_evidence_sha256'] = q.records_hash(d['source_captures'])
    d['source_row_sha256'] = q.sha(row)
    rehash_decision(d)
    if valid:
        q.validate_decision(row, d, CLOCK)
    else:
        with pytest.raises(ValueError): q.validate_decision(row, d, CLOCK)


@pytest.mark.parametrize('field', ['policy_sha256', 'source_review_manifest_sha256'])
def test_embedded_decision_manifest_binds_optional_review_metadata(field):
    _, _, (m, kept, changes) = fixture()
    m['decisions_manifest'][field] = 'd'*64
    m['decisions_manifest_sha256'] = q.records_hash([m['decisions_manifest']])
    with pytest.raises(ValueError, match='policy or review'):
        q.parent_rows(m, kept, changes)
