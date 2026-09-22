
import pytest

from apartments.research_pipeline import publish_bundle
from models.cohort_spatial_features import check_listing, resolve_building, feature_summary, verified_manifest, bound_archived_building


def point():
    return {'status': 'source_bound', 'source_building_id': '12',
            'latitude': 40.7, 'longitude': -74., 'street_candidate': 'seventh avenue'}


def test_coordinate_and_street_conflicts_are_distinguished():
    a = point(); b = {**a, 'street_candidate': '7th avenue'}
    result = resolve_building('demo', [a, b], {'12'})
    assert result['status'] == 'source_bound'
    assert result['street_candidate'] is None
    assert result['street_status'] == 'missing_or_conflicting_street'
    b['latitude'] += .0001
    assert resolve_building('demo', [a, b], {'12'})['status'] == 'missing_or_conflicting_location'


@pytest.mark.parametrize('fault', ['missing', 'building_id', 'invalid_capture', 'multiple_ids'])
def test_all_capture_and_listing_id_evidence_must_agree(fault):
    captures, ids = [point()], {'12'}
    if fault == 'missing': captures = []
    elif fault == 'building_id': ids = {'13'}
    elif fault == 'invalid_capture': captures.append({'status': 'invalid_or_conflicting_coordinates'})
    elif fault == 'multiple_ids': ids.add('13')
    assert resolve_building('demo', captures, ids)['status'] == 'missing_or_conflicting_location'


def test_historical_coordinate_join_requires_own_raw_building_identity():
    row = {'capture_ids': [4], 'audit_id': 'a', 'source_listing_id': '10', 'building': 'demo',
           'canonical_unit_url': 'https://streeteasy.com/building/demo/3d'}
    record = (4, '10', row['canonical_unit_url'], 'demo', '12', '10')
    assert check_listing(row, record)['source_building_id'] == '12'
    for position, wrong in [(0, True), (0, '4'), (1, '11'), (2, 'https://streeteasy.com/building/other/3d'),
                            (3, 'other'), (4, None), (5, '99')]:
        bad = list(record); bad[position] = wrong
        with pytest.raises(ValueError): check_listing(row, bad)


def test_building_center_and_street_support_do_not_count_ads_as_buildings():
    a = {'building': 'a', **point()}
    b = {'building': 'b', **point(), 'source_building_id': '13', 'latitude': 40.8,
         'street_candidate': 'west 20th street'}
    c = {'building': 'c', 'status': 'missing_or_conflicting_location'}
    rows = [{'building': building, 'unit_id': 'u'+str(i), 'analysis_price_basis': basis}
            for i, (building, basis) in enumerate([('a', 'historical_initial_own_advertisement_ask')]*5+
                [('b', 'current_capture_gross_ask'), ('c', 'current_capture_gross_ask')])]
    summary = feature_summary([a, b, c], rows)
    assert summary['coordinate_center']['latitude'] == pytest.approx(40.75)
    assert summary['covered_rows'] == 6 and summary['covered_current_rows'] == 1
    assert summary['street_support'][0]['buildings'] == 1
    assert summary['street_support'][0]['rows'] == 5
    assert summary['maximum_within_building_feature_difference'] == 0
    assert summary['additional_rank_given_building_indicators'] == 0


def test_streamed_artifact_verification_rejects_changed_files(tmp_path):
    publish_bundle(tmp_path, {'example.txt': 'original'}, {'version': 'test'})
    assert verified_manifest(tmp_path)['version'] == 'test'
    (tmp_path/'example.txt').write_text('changed')
    with pytest.raises(ValueError, match='differs'): verified_manifest(tmp_path)


def flight_records():
    return {'1': {'id': '12', 'slug': 'demo', 'geoCenter': '$2', 'address': '$3',
                  'latitude': 40.7, 'longitude': -74},
            '2': {'latitude': 40.7, 'longitude': -74}, '3': {'street': '140 Seventh Avenue'}}


def test_building_page_spatial_references_are_resolved_with_source_paths():
    result = bound_archived_building('12', 'https://streeteasy.com/building/demo', flight_records())
    assert result['status'] == 'source_bound' and result['latitude'] == 40.7
    assert result['source_paths'] == ['/1/geoCenter']
    assert result['street_candidate'] == 'seventh avenue'
    assert {'source_path': '/1/geoCenter', 'reference': '$2', 'target_path': '/2'} in result['field_references']


@pytest.mark.parametrize('fault', ['missing', 'cycle', 'conflict', 'slug', 'literal_text'])
def test_reference_resolution_does_not_hide_bad_building_evidence(fault):
    from streeteasy_archive.flight import FlightText
    decoded = flight_records()
    if fault == 'missing': del decoded['2']
    elif fault == 'cycle': decoded['2'] = '$2'
    elif fault == 'conflict': decoded['2']['latitude'] = 40.8
    elif fault == 'slug': decoded['1']['slug'] = 'other'
    elif fault == 'literal_text': decoded['1']['geoCenter'] = FlightText('$2')
    assert bound_archived_building('12', 'https://streeteasy.com/building/demo', decoded)['status'] != 'source_bound'


@pytest.mark.parametrize('fault', [None, 'body_hash', 'snapshot_url', 'exported_coordinate'])
def test_complete_local_source_join_decodes_real_flight_and_is_replayable(tmp_path, fault):
    import gzip
    import hashlib
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq
    from apartments.corrections import canonical
    from apartments.research_pipeline import digest
    from models import cohort_spatial_features as m

    archive, bodies, history, dataset, current, output = [tmp_path/n for n in
        ('archive', 'bodies', 'history', 'dataset', 'current', 'output')]
    archive.mkdir()
    (archive/'complete.json').write_text('{}\n')
    decoded = flight_records()
    frames = ''.join(k+':'+json.dumps(v)+'\n' for k, v in decoded.items())
    body = ('<script>self.__next_f.push('+json.dumps([1, frames])+')</script>').encode()
    sha = hashlib.sha256(body).hexdigest()
    (bodies/sha[:2]).mkdir(parents=True)
    (bodies/sha[:2]/(sha+'.gz')).write_bytes(gzip.compress(body if fault != 'body_hash' else b'changed'))
    def parquet(name, rows):
        p = archive/name; p.parent.mkdir(exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), p)
    url = 'https://streeteasy.com/building/demo/3d'
    parquet('listing_observations/part.parquet', [{'snapshot_id': 1, 'listing_id': '10',
        'canonical_unit_url': url, 'building_slug': 'demo',
        'raw_listing_json': json.dumps({'id': '10', 'buildingId': '12'})}])
    parquet('snapshots/metadata.parquet', [{'snapshot_id': 2, 'body_hash': sha, 'kind': 'building',
        'observed_at': 1672531200., 'url': 'https://streeteasy.com/building/'+('other' if fault == 'snapshot_url' else 'demo')}])
    raw = decoded['1']
    parquet('building_observations/part.parquet', [{'snapshot_id': 2, 'building_slug': 'demo',
        'building_id': '12', 'latitude': 40.8 if fault == 'exported_coordinate' else 40.7,
        'longitude': -74., 'raw_building_json': json.dumps(raw)}])
    inventory = {name: digest(archive/name) for name in
        ('complete.json', 'listing_observations/part.parquet', 'snapshots/metadata.parquet')}
    row = {'audit_id': 'a', 'unit_id': 'u', 'source_listing_id': '10', 'capture_ids': [1],
        'canonical_unit_url': url, 'building': 'demo', 'price_at': '2020-01-01', 'rent': 3000}
    publish_bundle(history, {'observations.jsonl': canonical(row)+'\n',
        'source-files.json': canonical(inventory)+'\n'}, {'dataset_version': 'historical-own-advertisement-v1'})
    publish_bundle(dataset, {'observations.jsonl': canonical({**row, 'asking_rent': 3000,
        'analysis_price_basis': 'historical_initial_own_advertisement_ask'})+'\n'}, {'version': 'test'})
    publish_bundle(current, {'captures.jsonl': ''}, {'version': m.spatial.VERSION})
    arguments = dict(dataset=dataset, historical=history, archive=archive, bodies=bodies,
                     current_spatial=current, interpreted_at='2026-09-19T08:30:50Z', output=output)
    if fault:
        with pytest.raises(ValueError): m.run(**arguments)
        assert not (output/'complete.json').exists()
    else:
        result = m.run(**arguments)
        assert result['covered_rows'] == 1 and result['covered_buildings'] == 1
        assert result['historical_listing_captures'] == result['building_page_captures'] == 1
        first = digest(output/'complete.json')
        assert m.run(**arguments) == result
        assert digest(output/'complete.json') == first
