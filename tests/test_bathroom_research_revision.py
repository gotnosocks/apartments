from copy import deepcopy
import hashlib
import pytest
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle,digest
from models import bathroom_research_revision as revision


def fixture_case(action='mark_shared_composition_unknown'):
    text='Private studio with shared bathrooms.'
    row={'audit_id':'a','source_listing_id':'ad','unit_id':'u','canonical_unit_url':'url','rent':2000,'bathrooms':1.5,
         'reported_full_bathrooms':1,'reported_half_bathrooms':1,
         'bathroom_count_evidence':{'full_status':'consistent_explicit_count','half_status':'consistent_explicit_count',
             'flags':['keep_this_flag'],'capture_ids':[1]}}
    evidence={k:row[k] for k in revision.SOURCE_ID_FIELDS}|{'capture_id':1,'description':text,
        'description_sha256':hashlib.sha256(text.encode()).hexdigest(),'start':20,'end':36,'literal':text[20:36]}
    d={k:row[k] for k in revision.SOURCE_ID_FIELDS}|{'action':action,'source_projection_row_sha256':revision.sha(row),
        'interpreted_at':'2026-09-18T20:00:00+00:00','evidence':[evidence],'reason':'fixture'}
    d['decision_id']=revision.sha(d)
    return row,d


def rebind(row,decision):
    decision['source_projection_row_sha256']=revision.sha(row)
    decision.pop('decision_id',None)
    decision['decision_id']=revision.sha(decision)


def test_shared_access_preserves_all_reported_counts_and_original_analytical_fields():
    row,d=fixture_case();original=deepcopy(row);r=revision.apply_decision(row,d)
    assert row==original
    assert r['reported_full_bathrooms']==1 and r['reported_half_bathrooms']==1
    assert r['bathrooms']==1.5 and r['rent']==2000
    assert r['bathroom_count_evidence']['flags']==['keep_this_flag',revision.SHARED_FLAG]
    assert r['bathroom_count_evidence']['full_status']=='consistent_explicit_count'
    assert r['bathroom_count_evidence']['composition_status']=='reviewed_external_shared_access_composition_unknown'
    assert r['bathroom_count_before_review']=={k:row[k] for k in revision.REVIEW_FIELDS}


def test_acceptance_removes_only_generic_review_flag_and_keeps_counts():
    row,d=fixture_case('accept_corroborated_multiple_half')
    row['reported_half_bathrooms']=2;row['bathroom_count_evidence']['flags'].append(revision.MULTIPLE_FLAG);rebind(row,d)
    r=revision.apply_decision(row,d)
    assert r['reported_half_bathrooms']==2
    assert r['bathroom_count_evidence']['flags']==['keep_this_flag']
    assert revision.MULTIPLE_FLAG in r['bathroom_count_before_review']['bathroom_count_evidence']['flags']


def test_office_quarantine_does_not_change_source_row():
    row,d=fixture_case('quarantine_nonresidential');original=deepcopy(row)
    assert revision.apply_decision(row,d) is None
    assert row==original


@pytest.mark.parametrize('problem,expected',[
 ('row','source row hash'),('id','Decision ID'),('span','Evidence text span'),
 ('capture','capture membership'),('identity','Evidence identity')])
def test_tampered_source_binding_fails(problem,expected):
    row,d=fixture_case()
    if problem=='row':row['rent']=999
    elif problem=='id':d['decision_id']='wrong'
    else:
        if problem=='span':d['evidence'][0]['literal']='wrong'
        elif problem=='capture':d['evidence'][0]['capture_id']=2
        elif problem=='identity':d['evidence'][0]['unit_id']='wrong'
        rebind(row,d)
    with pytest.raises(ValueError,match=expected):revision.apply_decision(row,d)


def test_source_excerpt_refuses_changed_reviewed_wording_or_count():
    row,d=fixture_case()
    capture={**d['evidence'][0],'source_listing_id':'1945700','body_sha256':'b','raw_listing_sha256':'r',
             'source_collected_at':'2026-09-18T19:00:00Z','description_interpreted_at':None,'known_at':'2026-09-18T19:00:00Z',
             'bathroom_fields':{'fullBathroomCount':{'value':1},'halfBathroomCount':{'value':2}}}
    with pytest.raises(ValueError,match='Reviewed source wording missing'):revision.source_excerpt(capture,'accept_corroborated_multiple_half')
    capture['description']='Three baths: (1 Full, 2 Half Baths)'
    capture['description_sha256']=hashlib.sha256(capture['description'].encode()).hexdigest()
    assert revision.source_excerpt(capture,'accept_corroborated_multiple_half')['literal']=='(1 Full, 2 Half Baths)'
    capture['bathroom_fields']['halfBathroomCount']['value']=5
    with pytest.raises(ValueError,match='counts differ'):revision.source_excerpt(capture,'accept_corroborated_multiple_half')


def test_projection_replays_and_preserves_untargeted_rows(tmp_path):
    from pathlib import Path
    row,d=fixture_case()
    untouched={**deepcopy(row),'audit_id':'untouched','source_listing_id':'other'}
    projection=tmp_path/'projection'
    pm=publish_bundle(projection,{'observations.jsonl':canonical(row)+'\n'+canonical(untouched)+'\n'},{'version':'fixture'})
    decisions=tmp_path/'decisions'
    publish_bundle(decisions,{'decisions.jsonl':canonical(d)+'\n'},
      {'version':revision.DECISION_VERSION,'projection_manifest':pm,'summary':{'interpreted_at':d['interpreted_at']},
       'implementation_sha256':{Path(revision.__file__).name:digest(Path(revision.__file__))}})
    output=tmp_path/'output';result=revision.project(projection,decisions,output)
    assert result['summary']['after']['rows']==2
    assert result['summary']['after']['flagged_rows']==2
    assert revision.project(projection,decisions,output)==result
    import json
    r=[json.loads(x) for x in (output/'observations.jsonl').read_text().split('\n') if x]
    assert r[1]==untouched
