import json

import pytest

from apartments.outdoor_evidence import extract
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle,_verified_bundle
from models.outdoor_policy_projection import run


def test_corroboration_preserves_cohort_raw_categories_shared_and_replay(tmp_path):
    rows=[];captures=[]
    for key,types,text in [('1',['BALCONY','PATIO'],'This apartment has a private balcony.'),
                            ('2',['GARDEN'],'The building has a shared garden.'),
                            ('3',['BALCONY','ROOF_RIGHTS'],'This apartment has a private balcony.')]:
        rows.append({'audit_id':key,'source_listing_id':key,'unit_id':'u'+key,'capture_ids':[key],
            'asking_rent':3000,'private_outdoor_category':None if key=='3' else '+'.join(types),'shared_outdoor_category':'GARDEN'})
        details={'features':{'privateOutdoorSpaceTypes':types}}
        captures.append({'audit_id':key,'source_listing_id':key,'unit_id':'u'+key,'capture_id':key,
            'property_details':details,'description':text,'extraction':extract({'propertyDetails':details,'description':text})})
    evidence=tmp_path/'evidence'
    em=publish_bundle(evidence,{'evidence.jsonl':''.join(canonical(r)+'\n' for r in captures)}, {'version':'fixture'})
    structured=tmp_path/'structured'
    dm=publish_bundle(structured,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},
        {'dataset_version':'advertised-outdoor-types-v1','outdoor_audit_manifest':em,'rows':3})
    output=tmp_path/'out';manifest=run(structured,evidence,output)
    assert manifest['support']['known_private_rows']==2
    actual=[json.loads(s) for s in (output/'observations.jsonl').read_text().split('\n') if s]
    assert actual[0]['private_outdoor_category']=='BALCONY'
    assert actual[0]['structured_private_outdoor_category']=='BALCONY+PATIO'
    assert actual[1]['private_outdoor_category'] is None
    assert actual[2]['private_outdoor_category']=='BALCONY'  # Unknown roof rights do not invent an outdoor type.
    assert actual[2]['structured_private_outdoor_category'] is None
    assert all(r['shared_outdoor_category']=='GARDEN' and r['asking_rent']==3000 for r in actual)
    assert run(structured,evidence,output)==manifest
    other=tmp_path/'other'
    publish_bundle(other,{'evidence.jsonl':''},{'version':'different'})
    with pytest.raises(ValueError,match='do not bind'):
        run(structured,other,tmp_path/'wrong')
