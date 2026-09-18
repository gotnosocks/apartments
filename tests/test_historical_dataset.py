from copy import deepcopy
import json

import pytest

from apartments import corrections, historical_dataset as historical


def capture(listing='old', snapshot=1, beds=0, when='2026-09-01T00:00:00+00:00'):
    return {'snapshot_id': snapshot, 'listing_id': listing, 'listing_type': 'rental',
            'canonical_unit_url': 'https://streeteasy.com/building/test/1d',
            'building_slug': 'test', 'unit_label': '#1D', 'bedrooms': beds,
            'bathrooms': 1, 'square_feet': 500, 'collected_at': when, 'parsed_at': when,
            'features_json': '[]', 'amenities_json': '[]',
            'raw_listing_json': json.dumps({'id': listing, 'pricing': {}, 'propertyDetails': {}})}


def membership(listing='old'):
    return {'listing_id': listing, 'unit_id': 'unit:1',
            'canonical_unit_url': 'https://streeteasy.com/building/test/1d',
            'status': 'associated', 'rule': 'canonical-url-v1'}


def event(listing='old', snapshot=1, date='2015-01-01', price=2500):
    return {'snapshot_id': snapshot, 'event_listing_id': listing,
            'event_category': 'rental', 'status': 'ACTIVE', 'event_date': date, 'price': price}


@pytest.fixture(autouse=True)
def extraction(monkeypatch):
    monkeypatch.setattr(historical, '_extract', lambda raw: {'attributes': {}, 'evidence': [], 'conflicts': {}})


def project(captures=None, events=None, memberships=None, **kwargs):
    return historical.project_advertisement(captures or [capture()], memberships or [membership()],
                                            events if events is not None else [event()],
                                            as_of='2026-09-18', **kwargs)


def test_retrospective_clock_and_own_advertisement_only():
    row, audit = project(events=[event(), event('another', date='2010-01-01', price=900)])
    assert row['observed_at'] == row['price_at'] == '2015-01-01T00:00:00+00:00'
    assert row['known_at'] == row['collected_at'] == '2026-09-01T00:00:00+00:00'
    assert row['rent'] == 2500
    assert row['bedrooms'] == 0
    assert row['attribute_assumption'] == 'retrospective_same_advertisement'
    assert row['audit_id'] == audit['audit_id']
    assert 'archive_listing' not in audit['captures'][0]['raw_values']


@pytest.mark.parametrize('events,reason', [
    ([event(price=2500), event(price=3000)], 'conflicting_or_missing_initial_prices'),
    ([event(price=None), event(price=3000)], 'conflicting_or_missing_initial_prices'),
    ([event('another')], 'no_dated_own_active_event'),
    ([event(date='bad')], 'invalid_own_active_event_date'),
    ([event(price=100)], 'invalid_or_extreme_initial_ask'),
    ([event(date='2027-01-01')], 'future_own_active_event'),
])
def test_unsafe_targets_quarantined(events, reason):
    row, audit = project(events=events)
    assert row is None
    assert reason in audit['reasons']


def test_conflicting_layout_never_arbitrarily_minimized():
    row, audit = project(captures=[capture(), capture(snapshot=2, beds=1)])
    assert row is None
    assert 'conflicting_layout_within_advertisement' in audit['reasons']


def test_membership_ambiguity_and_capture_mismatch():
    alternate = {**membership(), 'unit_id': 'unit:2'}
    assert project(memberships=[membership(), alternate])[0] is None
    bad = {**capture(), 'canonical_unit_url': 'https://streeteasy.com/building/test/2d'}
    assert 'unresolved_or_conflicting_canonical_url' in project(captures=[bad])[1]['reasons']


def test_effective_correction_and_raw_preservation(tmp_path, monkeypatch):
    ledger = tmp_path / 'corrections.jsonl'
    monkeypatch.setattr(corrections, 'now', lambda: corrections.instant('2026-09-15'))
    record = corrections.append(ledger, author='reviewer', reason='2015 studio mislabeled', edit={
        'target': {'source': 'streeteasy', 'source_listing_id': 'old'},
        'validity': {'from': '2014-01-01', 'until': '2016-01-01'},
        'patch': [{'op': 'replace', 'path': '/attributes/bedrooms', 'value': 1}]})
    overlay = corrections.Overlay(ledger, as_of='2026-09-18')
    row, audit = project(overlay=overlay)
    assert row['bedrooms'] == 1
    assert row['known_at'] == '2026-09-15T00:00:00+00:00'
    assert audit['captures'][0]['raw_values']['attributes']['bedrooms'] == 0
    assert audit['captures'][0]['projections'][0]['corrections'][0]['id'] == record['id']
    assert project(events=[event(date='2016-01-01')], overlay=overlay)[0]['bedrooms'] == 0
    assert project(overlay=corrections.Overlay(ledger, as_of='2026-09-14'))[0]['bedrooms'] == 0


def test_correction_can_resolve_conflicting_initial_prices(tmp_path, monkeypatch):
    ledger = tmp_path / 'corrections.jsonl'
    monkeypatch.setattr(corrections, 'now', lambda: corrections.instant('2026-09-15'))
    corrections.append(ledger, author='reviewer', reason='verified initial ask', edit={
        'target': {'source': 'streeteasy', 'source_listing_id': 'old'},
        'validity': {'all_time': True},
        'patch': [{'op': 'replace', 'path': '/asking_rent', 'value': 2800}]})
    row, audit = project(events=[event(price=2500), event(price=3000)], overlay=corrections.Overlay(ledger, as_of='2026-09-18'))
    assert row['rent'] == 2800
    assert {p['raw_initial_ask'] for p in audit['captures'][0]['projections']} == {2500, 3000}


@pytest.mark.parametrize('pricing,feature,reason', [
    ({'monthsFree': 1}, [], 'excluded_concession'),
    ({'leaseTermMonths': 3}, [], 'excluded_short_term'),
    ({}, ['FURNISHED'], 'excluded_furnished'),
])
def test_nonstandard_rent_quarantine(pricing, feature, reason):
    c = capture()
    c['raw_listing_json'] = json.dumps({'pricing': pricing})
    c['features_json'] = json.dumps(feature)
    assert reason in project(captures=[c])[1]['reasons']


def test_knowledge_cutoff_and_date_window():
    assert project(captures=[capture(when='2026-09-20T00:00:00+00:00')])[0] is None
    assert 'outside_date_window' in project(end='2014-12-31')[1]['reasons']
    assert project(end='2015-01-01')[0]


def test_deterministic_capture_order():
    captures = [capture(snapshot=1), capture(snapshot=2)]
    assert project(captures=captures) == project(captures=list(reversed(captures)))


def test_bundle_real_parquet_hashes_idempotence_and_rejected_month(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from apartments.research_pipeline import read_bundle
    dataset = tmp_path / 'source'
    dataset.mkdir()
    (dataset / 'complete.json').write_text(json.dumps({'unit_association_rule': 'canonical-url-v1', 'finished_at': corrections.instant('2026-09-17').timestamp(), 'counts': {'listing_observations': 2, 'rental_unit_memberships': 2, 'event_mentions': 2}}))
    captures = [capture(), capture('new', snapshot=2, beds=1)]
    for c in captures:
        c['collected_at'] = corrections.instant(c['collected_at']).timestamp()
        c['parsed_at'] = c['collected_at']
    events = [event(), event('new', snapshot=2, date='2015-01-20')]
    for i, e in enumerate(events):
        e['event_index'] = i
    records = {'listing_observations': captures, 'rental_unit_memberships': [membership(), membership('new')],
               'event_mentions': events}
    for name, records in records.items():
        (dataset / name).mkdir()
        pq.write_table(pa.Table.from_pylist(records), dataset / name / 'part-00000.parquet')
    output = tmp_path / 'output'
    with pytest.raises(ValueError, match='predates'):
        historical.build_historical_dataset(dataset, output, as_of='2026-09-16')
    first = historical.build_historical_dataset(dataset, output, as_of='2026-09-18')
    assert first == historical.build_historical_dataset(dataset, output, as_of='2026-09-18')
    assert read_bundle(output) == first
    assert first['coverage']['accepted'] == 0
    assert first['coverage']['exclusion_reasons'] == {'conflicting_layout_same_unit_month': 2}
    assert len(json.loads((output / 'source-files.json').read_text())) == 4
    (output / 'observations.jsonl').write_text('tampered')
    with pytest.raises(ValueError, match='integrity'):
        read_bundle(output)


def recovered_source(tmp_path):
    import hashlib
    import pyarrow as pa
    import pyarrow.parquet as pq
    from apartments.research_pipeline import digest, publish_bundle
    dataset = tmp_path / 'source'
    dataset.mkdir()
    c = capture()
    c['raw_listing_json'] = json.dumps({'id': 'old', 'description': '$d', 'pricing': {}})
    c['collected_at'] = corrections.instant(c['collected_at']).timestamp()
    c['parsed_at'] = c['collected_at']
    e = {**event(), 'event_index': 0}
    tables = {'listing_observations': [c], 'rental_unit_memberships': [membership()],
              'event_mentions': [e], 'snapshots': [{'snapshot_id': 1, 'body_hash': 'body-digest',
              'url': c['canonical_unit_url'], 'observed_at': c['collected_at']}]}
    counts = {name: len(values) for name, values in tables.items()}
    (dataset / 'complete.json').write_text(json.dumps({'unit_association_rule': 'canonical-url-v1',
        'finished_at': corrections.instant('2026-09-17').timestamp(), 'counts': counts}))
    for name, records in tables.items():
        (dataset / name).mkdir()
        pq.write_table(pa.Table.from_pylist(records), dataset / name / 'part.parquet')
    member_digest = digest(dataset / 'rental_unit_memberships' / 'part.parquet')
    (dataset / 'canonical-units.json').write_text(json.dumps({'counts': counts,
        'output_sha256': {'rental_unit_memberships': member_digest}}))
    source_files = {str(path.relative_to(dataset)): digest(path) for path in dataset.glob('*/*.parquet')}
    source_files['complete.json'] = digest(dataset / 'complete.json')
    recovered = {'snapshot_id': 1, 'listing_id': 'old', 'source_body_sha256': 'body-digest',
        'original_raw_listing_sha256': hashlib.sha256(c['raw_listing_json'].encode()).hexdigest(),
        'original_description_reference': '$d', 'resolved_description': 'This home has central air.',
        'interpreted_at': '2026-09-18T03:00:00+00:00', 'parser_version': 7,
        'recovery_version': 'description-recovery-v1'}
    recovered['description_sha256'] = hashlib.sha256(recovered['resolved_description'].encode()).hexdigest()
    def recovery_bundle(path, record=None):
        return publish_bundle(path, {
            'accepted.jsonl': corrections.canonical(record or recovered) + '\n',
            'source-files.json': corrections.canonical(source_files) + '\n',
        }, {'source_manifest_sha256': historical._hash(source_files),
            'parser_version': 7, 'recovery_version': 'description-recovery-v1', 'coverage': {'accepted': 1}})
    return dataset, recovered, recovery_bundle


def test_recovery_preserves_original_then_corrects_and_adds_knowledge_clock(tmp_path, monkeypatch):
    from apartments.research_pipeline import read_jsonl
    dataset, recovered, bundle = recovered_source(tmp_path)
    bundle(tmp_path / 'recovery')
    monkeypatch.setattr(historical, '_extract', lambda raw: {
        'attributes': {'hvac_type': 'central_ac' if raw.get('description', '').startswith('This') else None},
        'evidence': [], 'conflicts': {}})
    ledger = tmp_path / 'corrections.jsonl'
    monkeypatch.setattr(corrections, 'now', lambda: corrections.instant('2026-09-18T04:00:00+00:00'))
    corrections.append(ledger, author='reviewer', reason='window AC verified', edit={
        'target': {'source': 'streeteasy', 'source_listing_id': 'old'},
        'validity': {'all_time': True},
        'patch': [{'op': 'test', 'path': '/attributes/hvac_type', 'value': 'central_ac'},
                  {'op': 'replace', 'path': '/attributes/hvac_type', 'value': 'window_ac'}]})
    historical.build_historical_dataset(dataset, tmp_path / 'output', as_of='2026-09-18T23:59:59+00:00',
        ledger=ledger, description_recovery=tmp_path / 'recovery')
    row = next(read_jsonl(tmp_path / 'output' / 'observations.jsonl'))
    audit = next(read_jsonl(tmp_path / 'output' / 'audit.jsonl'))['captures'][0]
    assert row['hvac_type'] == 'window_ac'
    assert row['known_at'] == '2026-09-18T04:00:00+00:00'
    assert audit['original_description'] == '$d'
    assert audit['raw_values']['attributes'].get('hvac_type') is None
    assert audit['interpreted_attributes']['hvac_type'] == 'central_ac'
    assert audit['parser_interpretation'] == recovered
    historical.build_historical_dataset(dataset, tmp_path / 'earlier', as_of='2026-09-18T02:00:00+00:00',
        description_recovery=tmp_path / 'recovery')
    row = next(read_jsonl(tmp_path / 'earlier' / 'observations.jsonl'))
    assert row['hvac_type'] is None
    assert row['known_at'] == '2026-09-17T00:00:00+00:00'


@pytest.mark.parametrize('field,value,message', [
    ('snapshot_id', 999, 'missing source snapshot'),
    ('listing_id', 'other', 'listing identity'),
    ('source_body_sha256', 'wrong', 'source body'),
    ('original_raw_listing_sha256', 'wrong', 'original listing hash'),
    ('original_description_reference', '$other', 'description reference'),
    ('description_sha256', 'wrong', 'description hash'),
])
def test_recovery_rejects_provenance_mismatch(tmp_path, field, value, message):
    dataset, recovered, bundle = recovered_source(tmp_path)
    bundle(tmp_path / 'recovery', {**recovered, field: value})
    with pytest.raises(ValueError, match=message):
        historical.build_historical_dataset(dataset, tmp_path / 'output', as_of='2026-09-19',
            description_recovery=tmp_path / 'recovery')


def test_source_manifest_count_and_membership_digest_fail_closed(tmp_path):
    dataset, recovered, bundle = recovered_source(tmp_path)
    marker = dataset / 'complete.json'
    original = json.loads(marker.read_text())
    wrong = deepcopy(original)
    wrong['counts']['event_mentions'] += 1
    marker.write_text(json.dumps(wrong))
    with pytest.raises(ValueError, match='row count mismatch for event_mentions'):
        historical.build_historical_dataset(dataset, tmp_path / 'output', as_of='2026-09-19')
    marker.write_text(json.dumps(original))
    canonical = dataset / 'canonical-units.json'
    altered = json.loads(canonical.read_text())
    altered['output_sha256']['rental_unit_memberships'] = 'wrong'
    canonical.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match='membership artifact digest'):
        historical.build_historical_dataset(dataset, tmp_path / 'output', as_of='2026-09-19')


@pytest.mark.parametrize('description,excluded', [
    ('An unfurnished apartment with large windows.', False),
    ('This is not a furnished apartment.', False),
    ('The home is not fully furnished.', False),
    ('This fully-furnished apartment is ready.', True),
    ('A furnished apartment with a great view.', True),
])
def test_furnished_description_requires_positive_phrase(description, excluded):
    c = capture()
    c['raw_listing_json'] = json.dumps({'description': description, 'pricing': {}})
    row, audit = project(captures=[c])
    assert ('excluded_furnished' in audit['reasons']) is excluded
    assert (row is None) is excluded


def test_recovery_jsonl_unicode_line_separator_is_not_a_record_boundary(tmp_path):
    import hashlib
    from apartments.research_pipeline import publish_bundle
    dataset, record, bundle = recovered_source(tmp_path)
    bundle(tmp_path / 'original')
    record['resolved_description'] = 'Central air.\u2028Bright apartment.'
    record['description_sha256'] = hashlib.sha256(record['resolved_description'].encode()).hexdigest()
    manifest = json.loads((tmp_path / 'original' / 'complete.json').read_text())
    publish_bundle(tmp_path / 'unicode', {
        'accepted.jsonl': json.dumps(record, ensure_ascii=False) + '\n',
        'source-files.json': (tmp_path / 'original' / 'source-files.json').read_text(),
    }, {k:v for k,v in manifest.items() if k != 'files'})
    result = historical.build_historical_dataset(dataset, tmp_path / 'output', as_of='2026-09-19',
        description_recovery=tmp_path / 'unicode')
    assert result['coverage']['description_recovery_captures_used'] == 1
