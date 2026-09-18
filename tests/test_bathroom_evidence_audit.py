import pytest
from models.bathroom_evidence_audit import consensus, reported_bathrooms, screen


def item(details):
    return {'bathroom_fields':reported_bathrooms({'propertyDetails':details})}


def test_counts_preserve_two_halves_instead_of_arithmetic_reconstruction():
    result=consensus([item({'fullBathroomCount':1,'halfBathroomCount':2,'bathroomCount':2})])
    assert result['reported_full_bathrooms']==1
    assert result['reported_half_bathrooms']==2


@pytest.mark.parametrize('details',[
    {'bathroomCount':2.5},{'fullBathroomCount':2},
    {'fullBathroomCount':2,'halfBathroomCount':None},
    {'fullBathroomCount':True,'halfBathroomCount':0},
    {'fullBathroomCount':2,'halfBathroomCount':-1},
    {'fullBathroomCount':2,'halfBathroomCount':0.5},
])
def test_no_inferred_zero_half_or_reconstruction(details):
    result=consensus([item(details)])
    assert result['status']=='incomplete_explicit_counts'
    assert result['reported_half_bathrooms'] is None


def test_conflicting_captures_not_silently_selected():
    result=consensus([item({'fullBathroomCount':2,'halfBathroomCount':0}),item({'fullBathroomCount':1,'halfBathroomCount':2})])
    assert result['status']=='conflicting_reported_counts'


def test_partial_capture_not_silently_ignored():
    assert consensus([item({'fullBathroomCount':2,'halfBathroomCount':0}),item({'bathroomCount':2})])['status']=='incomplete_explicit_counts'


def test_exact_spans_and_distinct_bath_access_marketing_candidates():
    text='Two full baths; powder room. En-suite laundry, Jack & Jill bathroom. A home office can be converted.\u2028A quiet railroad.'
    findings=screen(text)
    families={f['family'] for f in findings}
    assert {'full_bath','powder_room','ensuite','jack_and_jill','home_office','privacy_noise','railroad'}<=families
    for f in findings:
        assert text[f['start']:f['end']]==f['literal']
        assert text[f['context_start']:f['context_end']]==f['context']
    assert 'non_bath_ensuite_context' in next(f for f in findings if f['family']=='ensuite')['flags']


def test_no_description_is_unknown_not_a_negative_feature():
    assert screen(None)==[]
    assert screen('Beautiful apartment.')==[]


@pytest.fixture
def audit_fixture(tmp_path):
    import hashlib
    import duckdb
    import pandas as pd
    from apartments.corrections import canonical
    from apartments.research_pipeline import digest,publish_bundle
    def make(wrong_raw_hash=False):
        archive=tmp_path/'archive'; shard=archive/'listing_observations/part.parquet'
        shard.parent.mkdir(parents=True)
        raw=canonical({'propertyDetails':{'fullBathroomCount':1,'halfBathroomCount':2},'description':'One full and two half baths.\u2028Home office.'})
        with duckdb.connect() as db:
            db.from_df(pd.DataFrame([{'snapshot_id':1,'listing_id':'ad1','canonical_unit_url':'url1','raw_listing_json':raw}])).write_parquet(str(shard))
        historical=tmp_path/'history'; hm=publish_bundle(historical,{'source-files.json':canonical({'listing_observations/part.parquet':digest(shard)})},{'version':'fixture'})
        row={'audit_id':'a1','source_listing_id':'ad1','canonical_unit_url':'url1','unit_id':'u1','building':'b1','bedrooms':2,'bathrooms':2,'capture_ids':[1],'analysis_price_basis':'historical_initial_own_advertisement_ask'}
        dataset=tmp_path/'dataset';dm=publish_bundle(dataset,{'observations.jsonl':canonical(row)+'\n'},{'historical_manifest':hm})
        description='One full and two half baths.\u2028Home office.'
        evidence={**row,'capture_id':1,'raw_listing_sha256':'bad' if wrong_raw_hash else hashlib.sha256(raw.encode()).hexdigest(),'description':description,'description_sha256':hashlib.sha256(description.encode()).hexdigest()}
        descriptions=tmp_path/'descriptions';publish_bundle(descriptions,{'evidence.jsonl':canonical(evidence)+'\n'},{'dataset_manifest':dm,'historical_manifest':hm})
        return (dataset,descriptions,archive,historical,tmp_path/'refresh',tmp_path/'audit'),row
    return make


def test_source_bound_audit_and_projection_replay_preserve_cohort(audit_fixture,tmp_path):
    import json
    from models.bathroom_evidence_audit import run
    from models.bathroom_projection import run as project_run
    args,row=audit_fixture()
    result=run(*args)
    assert result['summary']['rows']==1
    assert result['summary']['scalar_disagreement_audit_ids']==[]
    assert run(*args)==result
    output=tmp_path/'projection'
    projection=project_run(args[0],args[-1],output)
    projected=json.loads((output/'observations.jsonl').read_text())
    assert all(projected[k]==v for k,v in row.items())
    assert projected['reported_full_bathrooms']==1
    assert projected['reported_half_bathrooms']==2
    assert project_run(args[0],args[-1],output)==projection


def test_raw_source_hash_mismatch_cannot_publish(audit_fixture):
    from models.bathroom_evidence_audit import run
    args,_=audit_fixture(wrong_raw_hash=True)
    with pytest.raises(ValueError,match='Raw source identity or hash mismatch'):run(*args)
    assert not (args[-1]/'complete.json').exists()


def test_changed_inventory_shard_rejected_before_replay(audit_fixture):
    from models.bathroom_evidence_audit import run
    args,_=audit_fixture();run(*args)
    shard=args[2]/'listing_observations/part.parquet'
    shard.write_bytes(shard.read_bytes()+b'tampered')
    with pytest.raises(ValueError,match='Source shard hash mismatch'):run(*args)
