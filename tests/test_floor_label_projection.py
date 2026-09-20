from copy import deepcopy
import pytest
from apartments import floor_label_projection as f
from apartments.reviewed_cohort_quarantine import sha, records_hash


def project(*args, **kwargs):
    if len(args) < 5: kwargs.setdefault('as_of','2026-09-19T15:55:00Z')
    return f.project_row(*args, **kwargs)


def building(count):
    return {'floor_count':count,'source_collected_at':'2026-09-18T00:00:00Z',
        'source_path':'/floorCount','source_url':'https://streeteasy.com/building/b',
        'body_sha256':'a'*64,'raw_building_sha256':'b'*64}


def example():
    row = {'audit_id':'a', 'unit_id':'u', 'source_listing_id':'12', 'capture_ids':[1,2],
           'building':'b', 'known_at':'2026-09-18T00:00:00Z', 'advertised_floor':None}
    captures = [{'audit_id':'a','unit_id':'u','source_listing_id':'12','capture_id':c,
         'source_collected_at':row['known_at'], 'known_at':row['known_at'], 'raw_listing_sha256':'a'*64,'body_sha256':'b'*64,
         'literal':'#3D','candidate_floor':3,'source_path':'/propertyDetails/address/displayUnit'} for c in [1,2]]
    return row,captures


def test_public_projection_detaches_nested_values_after_readonly_replay():
    row, captures = example()
    row['nested'] = {'values': [1, {'label': 'original'}]}
    saved = deepcopy((row, captures))
    view = f._project_row_view(row, captures, [], as_of='2026-09-19T15:55:00Z')
    result = project(row, captures, [])
    assert view == result and (row, captures) == saved
    result['nested']['values'][1]['label'] = 'changed'
    result['capture_ids'].append(99)
    assert (row, captures) == saved


@pytest.mark.parametrize('label,want',[('3D',3),('#14b',14),(' 9A ',9),('PH',None),('301',None),('03D',None),('3AB',None),('A3',None),(None,None)])
def test_conservative_rule(label,want):
    assert f.candidate(label)==want


def test_explicit_claim_and_excluded_building_are_not_replaced():
    row,c=example(); row['advertised_floor']=4
    assert 'listed_floor' not in project(row,c,[])
    row['advertised_floor']=None
    result=project(row,c,['b'])
    assert result['label_derived_floor']==3 and 'listed_floor' not in result


def test_all_captures_must_resolve_and_agree():
    row,c=example(); c[1]['literal']='4D'; c[1]['candidate_floor']=4
    assert 'listed_floor' not in project(row,c,[])
    c[1]['literal']='PH'; c[1]['candidate_floor']=None
    assert 'listed_floor' not in project(row,c,[])
    with pytest.raises(ValueError): project(row,c[:1],[])


def test_inverse_exact_and_mutation_rejected():
    row,c=example(); after=project(row,c,[])
    parent={'version':f.PARENT, 'files':{'observations.jsonl':records_hash([row])}}
    change={'source_index':0,'source_row_sha256':sha(row),'listed_floor_was_present':False,
            'before_listed_floor':None,'captures':c}
    m={'version':f.VERSION,'source_manifest':parent,'source_manifest_sha256':records_hash([parent]),
       'source_rows':1,'excluded_buildings':[], 'interpreted_at':'2026-09-19T15:55:00Z', 'files':{f.SIDECAR:records_hash([change])}}
    assert after['listed_floor']==3
    assert f.parent_rows(m,[after],[change])==(parent,[row])
    for field,value in [('listed_floor',4),('bedrooms',7),('source_listed_floor',1)]:
        bad=deepcopy(after);bad[field]=value
        with pytest.raises(ValueError):f.parent_rows(m,[bad],[change])
    bad=deepcopy(change);bad['captures'][0]['literal']='4D'
    m['files'][f.SIDECAR]=records_hash([bad])
    with pytest.raises(ValueError):f.parent_rows(m,[after],[bad])


def extend(parent, rows):
    """Build a valid bounded projection on a synthetic elevator-parent fixture."""
    changes, projected = [], []
    as_of = '2026-09-19T12:00:00Z'
    for index, row in enumerate(rows):
        ids = row.get('capture_ids', []) + ([row['capture_id']] if row.get('capture_id') is not None else [])
        captures = [{**{k: row[k] for k in ('audit_id','unit_id','source_listing_id','known_at')},
            'source_collected_at':row['known_at'], 'capture_id': ident, 'literal':'3D','candidate_floor':3,
            'body_sha256':'a'*64,'raw_listing_sha256':'b'*64,
            'source_path':'/propertyDetails/address/displayUnit'} for ident in ids]
        projected.append(project(row,captures,[],[],as_of))
        changes.append({'source_index':index,'source_row_sha256':sha(row),
            'listed_floor_was_present':'listed_floor' in row,'before_listed_floor':row.get('listed_floor'),
            'captures':captures})
    manifest={'version':f.VERSION,'source_manifest':parent,'source_manifest_sha256':records_hash([parent]),
        'source_rows':len(rows),'excluded_buildings':[],'building_floor_evidence':{},'interpreted_at':as_of,
        'files':{f.SIDECAR:records_hash(changes),'observations.jsonl':records_hash(projected)}}
    return manifest,projected,changes


def test_building_count_is_compatibility_filter_not_floor_mapping():
    row,c=example()
    for cap in c: cap.update(literal='14B',candidate_floor=14)
    assert project(row,c,[])['floor_label_provenance']['status']=='two_digit_label_without_building_count'
    low=project(row,c,[],[building(13)])
    assert 'listed_floor' not in low and low['label_derived_floor']==14
    assert project(row,c,[],[building(14)])['listed_floor']==14
    assert 'listed_floor' not in project(row,c,[],[building(14),building(13)])


def test_interpretation_and_capture_clocks_are_validated():
    row,c=example()
    with pytest.raises(ValueError): project(row,c,[],as_of='2026-09-17T00:00:00Z')
    c[0]['source_collected_at']='2026-09-19T00:00:00Z'
    with pytest.raises(ValueError): project(row,c,[])
