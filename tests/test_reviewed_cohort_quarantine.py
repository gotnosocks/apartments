from copy import deepcopy
import hashlib
import json

import pytest

from apartments import reviewed_cohort_quarantine as q
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from docs.analysis.scripts.prepare_reviewed_listing_quarantines import initial_price_evidence
from models import reviewed_cohort_projection as projection

CLOCK = '2026-09-19T06:53:10Z'


def add_excluded_row(rows):
    result = deepcopy(rows)
    result.append({**deepcopy(rows[-1]), 'audit_id': 'excluded', 'source_listing_id': '99999',
                   'period': '2018-01-01', 'capture_ids': ['excluded-capture'],
                   'analysis_price_basis': 'historical_initial_own_advertisement_ask'})
    return result


def quarantine_last(parent, rows):
    row = rows[-1]
    text = 'AVAILABLE ON A SHORT-TERM BASIS\u2028Literal evidence preserved.'
    evidence = [{**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
        'capture_id': cid, 'body_sha256': 'a'*64, 'raw_listing_sha256': 'b'*64,
        'description': text, 'description_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'source_collected_at': row['known_at'], 'known_at': row['known_at'],
        'spans': [{'start': 0, 'end': 30, 'literal': text[:30]}]} for cid in row['capture_ids']]
    decision = {**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
        'source_row_sha256': q.sha(row), 'reviewed_at': CLOCK, 'reviewer': 'reviewer',
        'reason': 'Explicit short-term offer', 'action': 'quarantine_explicit_short_term_offer', 'evidence': evidence}
    decision['decision_id'] = q.sha(decision)
    dm = {'version': q.DECISION_VERSION, 'reviewed_at': CLOCK,
          'source_manifest_sha256': q.records_hash([parent]),
          'source_observations_sha256': parent['files']['observations.jsonl'],
          'files': {'decisions.jsonl': q.records_hash([decision])}}
    kept, sidecar = projection.project(rows, [decision], CLOCK)
    manifest = {'version': q.VERSION, 'source_manifest': parent,
        'source_manifest_sha256': q.records_hash([parent]), 'source_rows': len(rows),
        'reviewed_at': CLOCK, 'decisions_manifest': dm, 'decisions_manifest_sha256': q.records_hash([dm]),
        'decision_ids': [decision['decision_id']],
        'files': {q.SIDECAR: q.records_hash(sidecar), 'observations.jsonl': q.records_hash(kept)}}
    return manifest, kept, sidecar


def fixture():
    source = [{'audit_id': str(i), 'unit_id': 'same-unit', 'building': 'building',
               'source_listing_id': str(100+i), 'capture_ids': [i, str(i)],
               'known_at': '2026-09-18T00:00:00Z', 'asking_rent': 3000+i,
               'analysis_price_basis': 'historical_initial_own_advertisement_ask'}
              for i in range(4)]
    source[3]['analysis_price_basis'] = 'current_capture_gross_ask'
    parent = {'version': q.PARENT, 'files': {'observations.jsonl': q.records_hash(source)}}
    decisions = []
    for row in (source[0], source[2]):
        text = 'AVAILABLE ON A SHORT-TERM BASIS'
        evidence = [{**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
            'capture_id': cid, 'body_sha256': 'a'*64, 'raw_listing_sha256': 'b'*64,
            'description': text, 'description_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'source_collected_at': row['known_at'], 'known_at': row['known_at'],
            'spans': [{'start': 0, 'end': len(text), 'literal': text}]} for cid in row['capture_ids']]
        decision = {**{k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id')},
            'source_row_sha256': q.sha(row), 'reviewed_at': CLOCK, 'reviewer': 'reviewer',
            'reason': 'Explicit short-term offer', 'action': 'quarantine_explicit_short_term_offer',
            'evidence': evidence}
        decision['decision_id'] = q.sha(decision)
        decisions.append(decision)
    dm = {'version': q.DECISION_VERSION, 'reviewed_at': CLOCK,
          'source_manifest_sha256': q.records_hash([parent]),
          'source_observations_sha256': parent['files']['observations.jsonl'],
          'files': {'decisions.jsonl': q.records_hash(decisions)}}
    kept, sidecar = projection.project(source, decisions, CLOCK)
    manifest = {'version': q.VERSION, 'source_manifest': parent,
        'source_manifest_sha256': q.records_hash([parent]), 'source_rows': len(source),
        'reviewed_at': CLOCK, 'decisions_manifest': dm, 'decisions_manifest_sha256': q.records_hash([dm]),
        'decision_ids': sorted(d['decision_id'] for d in decisions),
        'files': {q.SIDECAR: q.records_hash(sidecar)}}
    return source, decisions, kept, sidecar, manifest


def test_exact_inverse_retains_other_ads_and_current_row_without_mutation():
    source, _, kept, sidecar, manifest = fixture()
    before = deepcopy((kept, sidecar, manifest))
    assert kept == [source[1], source[3]]
    assert q.parent_rows(manifest, kept, sidecar) == (manifest['source_manifest'], source)
    assert (kept, sidecar, manifest) == before


@pytest.mark.parametrize('fault', ['price', 'order', 'retained_missing', 'sidecar_missing',
    'position', 'duplicate_position', 'source_count', 'duplicate_kept', 'decision_manifest',
    'decision_file', 'source_hash', 'decision_coverage', 'sidecar_hash'])
def test_inverse_rejects_changed_source_membership_and_bindings(fault):
    _, _, kept, sidecar, m = fixture()
    if fault == 'price': kept[0]['asking_rent'] += 1
    elif fault == 'order': kept.reverse()
    elif fault == 'retained_missing': kept.pop()
    elif fault == 'sidecar_missing': sidecar.pop()
    elif fault == 'position': sidecar[0]['source_index'] = 1
    elif fault == 'duplicate_position': sidecar[1]['source_index'] = 0
    elif fault == 'source_count': m['source_rows'] += 1
    elif fault == 'duplicate_kept': kept[1] = deepcopy(kept[0])
    elif fault == 'decision_manifest': m['decisions_manifest']['version'] = 'other'
    elif fault == 'decision_file': m['decisions_manifest']['files']['decisions.jsonl'] = 'c'*64
    elif fault == 'source_hash': m['source_manifest_sha256'] = 'c'*64
    elif fault == 'decision_coverage': m['decision_ids'].pop()
    # Rehash editable artifacts: source/decision bindings must still protect them.
    m['decisions_manifest_sha256'] = q.records_hash([m['decisions_manifest']])
    m['files'][q.SIDECAR] = q.records_hash(sidecar)
    if fault == 'sidecar_hash': m['files'][q.SIDECAR] = 'c'*64
    with pytest.raises(ValueError): q.parent_rows(m, kept, sidecar)


@pytest.mark.parametrize('fault', ['missing_capture', 'duplicate_capture', 'typed_capture', 'foreign_ad',
    'span', 'description', 'future_capture', 'capture_before_collection', 'early_review', 'action',
    'row_hash', 'decision_hash', 'current', 'reviewer'])
def test_decisions_require_exact_evidence_and_review_scope(fault):
    source, decisions, *_ = fixture()
    row, d = source[0], decisions[0]
    c = d['evidence'][0]
    if fault == 'missing_capture': d['evidence'].pop()
    elif fault == 'duplicate_capture': d['evidence'].append(deepcopy(c))
    elif fault == 'typed_capture': c['capture_id'] = str(c['capture_id'])
    elif fault == 'foreign_ad': c['source_listing_id'] = 'foreign'
    elif fault == 'span': c['spans'][0]['end'] -= 1
    elif fault == 'description': c['description'] += '!'
    elif fault == 'future_capture': c['known_at'] = '2027-01-01T00:00:00Z'
    elif fault == 'capture_before_collection': c['source_collected_at'] = CLOCK
    elif fault == 'early_review': d['reviewed_at'] = '2020-01-01T00:00:00Z'
    elif fault == 'action': d['action'] = 'replace_price'
    elif fault == 'row_hash': d['source_row_sha256'] = 'c'*64
    elif fault == 'current': row['analysis_price_basis'] = 'current_capture_gross_ask'; d['source_row_sha256'] = q.sha(row)
    elif fault == 'reviewer': d['reviewer'] = ''
    d['decision_id'] = q.sha({k: v for k, v in d.items() if k != 'decision_id'})
    if fault == 'decision_hash': d['decision_id'] = 'c'*64
    with pytest.raises(ValueError): q.validate_decision(row, d, CLOCK)


def test_publication_is_idempotent_and_preserves_source_evidence(tmp_path):
    source, decisions, *_ = fixture()
    parent, decision_path, output = [tmp_path/n for n in ('parent', 'decisions', 'output')]
    publish_bundle(parent, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in source),
                           'current-source-evidence.jsonl': '{}\n'}, {'version': q.PARENT})
    pm = json.loads((parent/'complete.json').read_text())
    publish_bundle(decision_path, {'decisions.jsonl': ''.join(canonical(d)+'\n' for d in decisions)},
        {'version': q.DECISION_VERSION, 'reviewed_at': CLOCK,
         'source_manifest_sha256': digest(parent/'complete.json'),
         'source_observations_sha256': pm['files']['observations.jsonl']})
    first = projection.run(parent, decision_path, output)
    checksum = digest(output/'complete.json')
    assert projection.run(parent, decision_path, output) == first
    assert digest(output/'complete.json') == checksum
    assert first['rows'] == 2 and first['current_rows'] == 1 and first['units'] == 1
    assert (output/'current-source-evidence.jsonl').read_bytes() == b'{}\n'


def test_initial_event_date_is_not_price_change_utc_date():
    row = {'source_listing_id': '2675026', 'asking_rent': 2878, 'price_at': '2019-03-12T00:00:00+00:00'}
    prices = {'priceChanges': [{'price': 2878, 'changedAt': '2019-03-12T20:56:30-04:00'},
                              {'price': 3100, 'changedAt': '2019-03-25T11:00:06-04:00'}]}
    events = [{'event_listing_id': '2675026', 'event_category': 'rental', 'status': 'ACTIVE',
               'price': 2878, 'event_date': '2019-03-12'}]
    assert initial_price_evidence(row, prices, events) == events
    for key, value in [('price_at', '2019-03-13'), ('asking_rent', 3100), ('source_listing_id', 'other')]:
        with pytest.raises(ValueError): initial_price_evidence({**row, key: value}, prices, events)
