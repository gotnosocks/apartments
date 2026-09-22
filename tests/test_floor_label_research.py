import pytest

from models.floor_label_research import infer_label, summarize


@pytest.mark.parametrize('label,value', [('3D', 3), ('# 14b', 14), (' 2A ', 2), ('99Z', 99)])
def test_prefix_hypothesis_retains_original_label(label, value):
    result = infer_label(label)
    assert result['literal'] == label
    assert result['candidate_floor'] == value
    assert result['status'] == 'inferred_candidate'


@pytest.mark.parametrize('label', ['301', '3', '03D', 'PH3', '3A/4A', '3AB', '3-D', '100A', '0A', 'B3', 'GROUND', '', '３D'])
def test_unresolved_numbering_is_not_silently_a_floor(label):
    assert infer_label(label)['candidate_floor'] is None
    assert infer_label(label)['status'] == 'unresolved_label'


def test_missing_and_invalid_source_types():
    assert infer_label(None)['status'] == 'missing'
    with pytest.raises(ValueError):
        infer_label(3)


def record(audit, label, explicit, unit='unit-a'):
    return {'audit_id': audit, 'unit_id': unit, 'building': 'building-a',
            'explicit_floor': explicit, **infer_label(label)}


def test_repeated_captures_are_not_independent_agreement_units():
    observations, summary = summarize([record('a', '3D', 3)] * 4 + [record('b', '3D', 2)])
    assert summary['reference_observations'] == 2
    assert summary['reference_units'] == 1
    assert summary['reference_unit_comparisons'] == {'any_disagreement': 1}
    assert summary['reference_comparisons'] == {'agrees': 1, 'disagrees': 1}
    assert len(observations) == 2


def test_capture_conflicts_and_unknowns_never_become_agreement():
    observations, summary = summarize([record('a', '3D', 3), record('a', '4D', 3),
                                       record('b', None, 2), record('c', '5A', None)])
    assert summary['reference_observations'] == 0
    assert summary['capture_label_conflict_observations'] == 1
    assert observations[0]['candidate_floor'] is None
    assert summary['candidate_observations'] == 1


def test_inconsistent_reference_or_identity_rejected():
    with pytest.raises(ValueError, match='Conflicting analytical'):
        summarize([record('a', '3D', 3), record('a', '3D', 4)])


@pytest.fixture
def source_fixture(tmp_path):
    import hashlib
    import pyarrow as pa
    import pyarrow.parquet as pq
    from apartments.corrections import canonical
    from apartments.research_pipeline import digest, publish_bundle

    archive = tmp_path / 'archive'
    shard = archive / 'listing_observations/part.parquet'
    shard.parent.mkdir(parents=True)
    raw = canonical({'id': 'ad-a', 'propertyDetails': {'address': {'displayUnit': '#3D'}},
                     'latestListing': {'propertyDetails': {'address': {'displayUnit': '#9Z'}}}})
    pq.write_table(pa.table({'snapshot_id': [1], 'raw_listing_json': [raw]}), shard)
    historical = tmp_path / 'historical'
    hm = publish_bundle(historical, {'source-files.json': canonical({'listing_observations/part.parquet': digest(shard)})}, {'version': 'test-history'})
    dataset = tmp_path / 'dataset'
    row = {'audit_id': 'a', 'unit_id': 'u', 'building': 'b', 'capture_ids': [1],
           'analysis_price_basis': 'historical_initial_own_advertisement_ask',
           'source_listing_id': 'ad-a', 'listed_floor': None, 'advertised_floor': 3}
    publish_bundle(dataset, {'observations.jsonl': canonical(row) + '\n'}, {'version': 'test-source'})
    descriptions = tmp_path / 'descriptions'
    e = {**row, 'capture_id': 1, 'body_sha256': 'a' * 64,
         'raw_listing_sha256': hashlib.sha256(raw.encode()).hexdigest()}
    publish_bundle(descriptions, {'evidence.jsonl': canonical(e) + '\n'},
                   {'version': 'test-descriptions', 'historical_manifest': hm})
    return {'dataset': dataset, 'descriptions': descriptions, 'archive': archive,
            'historical': historical, 'refresh': tmp_path / 'refresh', 'output': tmp_path / 'output'}


def test_verified_source_audit_uses_own_label_and_replays(source_fixture):
    import json
    from models.floor_label_research import run

    first = run(**source_fixture)
    assert first['summary']['reference_comparisons'] == {'agrees': 1}
    capture = json.loads((source_fixture['output'] / 'captures.jsonl').read_text())
    assert capture['literal'] == '#3D'
    assert capture['source_path'] == '/propertyDetails/address/displayUnit'
    assert run(**source_fixture) == first


def test_modified_source_shard_is_rejected(source_fixture):
    from models.floor_label_research import run

    shard = source_fixture['archive'] / 'listing_observations/part.parquet'
    shard.write_bytes(shard.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='Historical shard differs'):
        run(**source_fixture)
