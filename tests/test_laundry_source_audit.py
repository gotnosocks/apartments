from copy import deepcopy
import hashlib
import json

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models.laundry_source_audit import bind_candidate, inspect_capture, run, support


def case(*, structured=True):
    text = 'Washer/dryer hookups are available for tenant to install equipment.'
    payload = {'id': '123', 'description': '$resolvedLater', 'propertyDetails': {
        'features': {'list': ['WASHER_DRYER'] if structured else []}},
        'latestListing': {'propertyDetails': {'features': {'list': ['WASHER_DRYER', 'LAUNDRY']}}}}
    raw = canonical(payload)
    row = {'audit_id': 'a', 'unit_id': 'u', 'building': 'b', 'source_listing_id': '123',
        'capture_ids': [12], 'laundry_type': 'in_unit',
        'known_at': '2026-09-18T12:00:00+00:00',
        'analysis_price_basis': 'historical_initial_own_advertisement_ask'}
    evidence = {'audit_id': 'a', 'unit_id': 'u', 'source_listing_id': '123', 'capture_id': 12,
        'body_sha256': 'a'*64, 'raw_listing_sha256': hashlib.sha256(raw.encode()).hexdigest(),
        'description': text, 'description_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'source_collected_at': '2026-09-10T12:00:00+00:00',
        'description_interpreted_at': '2026-09-17T12:00:00+00:00',
        'known_at': '2026-09-18T11:00:00+00:00', 'source_path': '/description'}
    candidate = {**row, **evidence, 'findings': [{'kind': 'hookups', 'start': 0,
        'end': 20, 'literal': text[:20]}]}
    return candidate, row, evidence, raw


def test_recovered_description_and_structured_claim_are_kept_separate():
    args = case(); before = deepcopy(args)
    result = inspect_capture(*args)
    assert args == before
    assert result['structured_in_unit_claim'] is True
    assert result['structured_in_building_claim'] is False
    assert result['replayed_laundry_type'] == 'in_unit'
    assert len(result['laundry_assertions']) == 1
    assert result['laundry_assertions'][0]['source_path'] == '/propertyDetails/features/list/0'
    assert result['status'] == 'source_evidence_for_review_no_data_action'


def test_hookups_and_latest_listing_never_establish_installed_equipment():
    result = inspect_capture(*case(structured=False))
    assert result['replayed_laundry_type'] is None
    assert result['laundry_assertions'] == []
    assert result['laundry_type'] == 'in_unit'  # The audit does not silently patch it.


@pytest.mark.parametrize('field,value', [('capture_id', '12'), ('body_sha256', 'wrong'),
    ('source_listing_id', '456'), ('description', 'a different capture'),
    ('known_at', '2026-09-19'), ('laundry_type', 'in_building')])
def test_mismatched_candidate_cannot_be_attached(field, value):
    c, row, evidence, _ = case(); c[field] = value
    with pytest.raises(ValueError):
        bind_candidate(c, row, evidence)


def test_literal_offsets_and_raw_hash_are_verified():
    c, row, e, raw = case(); c['findings'][0]['start'] = 1
    with pytest.raises(ValueError, match='offsets'):
        inspect_capture(c, row, e, raw)
    c, row, e, raw = case()
    with pytest.raises(ValueError, match='hash'):
        inspect_capture(c, row, e, raw+' ')


def test_raw_advertisement_identity_is_independently_checked():
    c, row, e, raw = case(); payload = json.loads(raw); payload['id'] = '456'
    raw = canonical(payload); e['raw_listing_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    with pytest.raises(ValueError, match='advertisement'):
        inspect_capture(c, row, e, raw)


def test_repeated_captures_do_not_inflate_unit_support():
    result = inspect_capture(*case())
    counts = support([result, {**result, 'capture_id': 13}])
    assert counts['captures'] == 2
    assert counts['observations'] == counts['units'] == counts['buildings'] == 1


@pytest.fixture
def source_fixture(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    candidate, row, e, raw = case()
    original = {'dataset_version': 'historical-plus-current-capture-analysis-v1'}
    dataset = tmp_path/'dataset'
    publish_bundle(dataset, {'observations.jsonl': canonical(row)+'\n'}, {
        'version': 'reviewed-bathroom-counts-projection-v1', 'projection_manifest': {
            'version': 'reported-bathroom-counts-projection-v1', 'dataset_manifest': original}})
    archive = tmp_path/'archive'; shard = archive/'listing_observations/part.parquet'
    shard.parent.mkdir(parents=True)
    pq.write_table(pa.table({'snapshot_id': [12], 'raw_listing_json': [raw]}), shard)
    historical = tmp_path/'historical'
    hm = publish_bundle(historical, {'source-files.json': canonical({
        'listing_observations/part.parquet': digest(shard)})}, {'version': 'test-history'})
    descriptions = tmp_path/'descriptions'
    publish_bundle(descriptions, {'evidence.jsonl': canonical(e)+'\n'}, {
        'version': 'fitted-description-archive-v1', 'dataset_manifest': original, 'historical_manifest': hm})
    phrase = tmp_path/'phrase'
    publish_bundle(phrase, {'candidates.jsonl': canonical(candidate)+'\n', 'summary.json': canonical({
        'version': 'laundry-location-phrase-audit-v1',
        'source_manifest_sha256': digest(dataset/'complete.json'),
        'description_manifest_sha256': digest(descriptions/'complete.json')})}, {'version': 'test-phrase'})
    return dict(dataset=dataset, descriptions=descriptions, phrase_audit=phrase,
        archive=archive, historical=historical, refresh=tmp_path/'unused-refresh', output=tmp_path/'output')


def test_real_source_join_publication_and_idempotent_replay(source_fixture):
    first = run(**source_fixture)
    assert first['summary']['by_phrase']['hookups']['structured_in_unit_captures'] == 1
    assert run(**source_fixture) == first


def test_changed_raw_shard_rejected_before_publication(source_fixture):
    shard = source_fixture['archive']/'listing_observations/part.parquet'
    shard.write_bytes(shard.read_bytes()+b'changed')
    with pytest.raises(ValueError, match='shard differs'):
        run(**source_fixture)
    assert not source_fixture['output'].exists()
