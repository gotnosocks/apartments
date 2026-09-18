import copy
import hashlib
import json

import pytest

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle


def fixtures(*, cleaned=False):
    original={'dataset_version':'historical-plus-current-capture-analysis-v1',
              'files':{'observations.jsonl':'original-exact-cohort-hash'}}
    reported={'version':'reported-bathroom-counts-projection-v1','dataset_manifest':original}
    reviewed={'version':'reviewed-bathroom-counts-projection-v1','projection_manifest':reported}
    manifest=reviewed
    if cleaned:
        manifest={'version':'reviewed-scope-composition-projection-v2','source_manifest':reviewed,
                  'source_manifest_sha256':hashlib.sha256((canonical(reviewed)+'\n').encode()).hexdigest()}
    rows=[{'audit_id':'kept','source_listing_id':'123','unit_id':'u1','capture_ids':[12,13],
           'known_at':'2026-09-18T12:00:00+00:00'},
          {'audit_id':'no-text','source_listing_id':'124','unit_id':'u2','capture_id':14,
           'known_at':'2026-09-18T12:00:00+00:00'}]
    literal='Literal <script>alert(1)</script> en-suite.\u2028Second line'
    captures=[{'audit_id':'kept','source_listing_id':'123','unit_id':'u1','capture_id':12,
               'description':literal,'description_sha256':hashlib.sha256(literal.encode()).hexdigest(),
               'source_collected_at':'2026-09-10T10:00:00+00:00','known_at':'2026-09-18T10:00:00+00:00',
               'description_interpreted_at':'2026-09-17T10:00:00+00:00',
               'body_sha256':'body-hash','raw_listing_sha256':'raw-hash',
               'extraction':{'inferred_ensuite_count':9}},
              {'audit_id':'quarantined','source_listing_id':'999','unit_id':'removed','capture_id':99,
               'description':'Excluded ad; never joined by unit or ad alone.'}]
    evidence={'version':'fitted-description-archive-v1','dataset_manifest':original}
    return manifest,rows,evidence,captures


def publish(tmp_path,parts):
    manifest,rows,evidence,captures=parts
    dataset=tmp_path/'dataset';archive=tmp_path/'archive'
    publish_bundle(dataset,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},manifest)
    publish_bundle(archive,{'evidence.jsonl':''.join(canonical(r)+'\n' for r in captures)},evidence)
    return dataset,archive


@pytest.mark.parametrize('cleaned',[False,True])
def test_exact_lineage_survivors_and_literal_text_only(tmp_path,cleaned):
    parts=fixtures(cleaned=cleaned)
    mapping=load_evidence(*publish(tmp_path,parts))
    assert set(mapping)=={'kept','no-text'}
    assert mapping['no-text']==[]
    assert mapping['kept'][0]['description']==parts[3][0]['description']
    assert mapping['kept'][0]['source_path']=='/description'
    assert mapping['kept'][0]['body_sha256']=='body-hash'
    assert 'extraction' not in mapping['kept'][0]
    assert 'inferred_ensuite_count' not in mapping['kept'][0]


@pytest.mark.parametrize('field,value',[
    ('source_listing_id','999'),('unit_id','u2'),('capture_id',14),('capture_id','12'),
    ('capture_id',True),('source_collected_at','2026-09-19'),
    ('known_at','2026-09-19'),('known_at','2026-09-09'),
    ('description_interpreted_at','2026-09-19'),('description_interpreted_at','2026-09-09'),
    ('description_sha256','bad'),('description',{'not':'literal'})])
def test_surviving_identity_clock_or_literal_mismatch_rejected(tmp_path,field,value):
    parts=fixtures();parts[3][0][field]=value
    with pytest.raises(ValueError):load_evidence(*publish(tmp_path,parts))


def test_recovery_cannot_postdate_capture_knowledge_even_before_row_cutoff(tmp_path):
    parts=fixtures();parts[3][0]['description_interpreted_at']='2026-09-18T11:00:00+00:00'
    with pytest.raises(ValueError,match='clock'):load_evidence(*publish(tmp_path,parts))


def test_duplicate_capture_and_duplicate_observation_rejected(tmp_path):
    parts=fixtures();parts[3].append(copy.deepcopy(parts[3][0]))
    with pytest.raises(ValueError,match='duplicated'):load_evidence(*publish(tmp_path,parts))
    parts=fixtures();parts[1].append(copy.deepcopy(parts[1][0]))
    with pytest.raises(ValueError,match='duplicate observation'):
        load_evidence(*publish(tmp_path/'second',parts))


@pytest.mark.parametrize('fault',['wrong_original','unrelated_nested_match','parent_hash','wrong_parent_version','decision_conflict'])
def test_lineage_is_explicit_not_an_arbitrary_nested_manifest_match(tmp_path,fault):
    parts=fixtures(cleaned=True);manifest=parts[0]
    if fault=='wrong_original':parts[2]['dataset_manifest']= {'dataset_version':'historical-plus-current-capture-analysis-v1','files':{}}
    if fault=='unrelated_nested_match':
        manifest['source_manifest']['projection_manifest']['dataset_manifest']={'dataset_version':'wrong'}
        manifest['unrelated_dataset_manifest']=parts[2]['dataset_manifest']
    if fault=='parent_hash':manifest['source_manifest_sha256']='bad'
    if fault=='wrong_parent_version':manifest['source_manifest']['version']='unrelated-projection'
    if fault=='decision_conflict':manifest['source_manifest']['decision_manifest']={'projection_manifest':{}}
    if fault!='parent_hash':
        manifest['source_manifest_sha256']=hashlib.sha256((canonical(manifest['source_manifest'])+'\n').encode()).hexdigest()
    with pytest.raises(ValueError):load_evidence(*publish(tmp_path,parts))


def test_property_details_literal_precedence_and_missing_text(tmp_path):
    parts=fixtures();capture=parts[3][0]
    literal='Nested <b>private bath</b>'
    capture['property_details']={'description':literal}
    capture['description_sha256']=hashlib.sha256(literal.encode()).hexdigest()
    missing=copy.deepcopy(capture);missing.update(capture_id=13,description=None,description_sha256=None)
    del missing['property_details']
    parts[3].append(missing)
    result=load_evidence(*publish(tmp_path,parts))['kept']
    assert result[0]['description']==literal and result[0]['source_path']=='/propertyDetails/description'
    assert result[1]['description'] is None


def test_bundle_tampering_rejected_before_attachment(tmp_path):
    dataset,archive=publish(tmp_path,fixtures())
    (archive/'evidence.jsonl').write_text('{}\n')
    with pytest.raises(ValueError,match='integrity'):load_evidence(dataset,archive)


def test_fitted_archive_requires_capture_knowledge_clock(tmp_path):
    parts=fixtures();del parts[3][0]['known_at']
    with pytest.raises(ValueError,match='knowledge clock'):load_evidence(*publish(tmp_path,parts))
