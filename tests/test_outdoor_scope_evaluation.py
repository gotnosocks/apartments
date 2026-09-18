import hashlib
import json

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import outdoor_scope_evaluation, outdoor_scope_evaluation_v2


@pytest.mark.parametrize('module', [outdoor_scope_evaluation,outdoor_scope_evaluation_v2])
def test_evaluation_counts_disagreements_and_unlabeled_claims_without_hiding_them(tmp_path,module):
    text = 'No balcony. Private patio.'
    label = {'start':3,'end':10,'text':'balcony','scope':'private_explicit'}
    case = {'case_id':1,'audit_id':'a','source_listing_id':'1','capture_id':1,
            'description':text,'description_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'annotations':[label]}
    review=tmp_path/'review'
    publish_bundle(review, {'review.json':canonical({'cases':[case]})+'\n'}, {'version':'fixture'})
    output=tmp_path/'evaluation'
    actual=module.run(review,output)
    summary=actual['summary']
    assert summary['exact_scope_matches']==0
    assert summary['confusion']==[{'label':'private_explicit','prediction':'negative','count':1}]
    assert summary['unlabeled_unit_positive_claims']==1
    assert summary['matched_unit_positive_claims']==0
    assert module.run(review,output)==actual
    rows=[json.loads(s) for s in (output/'comparisons.jsonl').read_text().split('\n') if s]
    assert rows[0]['label']==label


@pytest.mark.parametrize('mutation,match', [('hash','hash mismatch'),('offset','offsets')])
def test_evaluation_rejects_labels_not_bound_to_source_text(tmp_path,mutation,match):
    text='Private balcony.'
    case={'description':text,'description_sha256':hashlib.sha256(text.encode()).hexdigest(),
          'annotations':[{'start':8,'end':15,'text':'balcony','scope':'private_explicit'}]}
    if mutation=='hash':case['description_sha256']='wrong'
    else:case['annotations'][0]['start']=7
    review=tmp_path/'review'
    publish_bundle(review, {'review.json':canonical({'cases':[case]})+'\n'}, {'version':'fixture'})
    with pytest.raises(ValueError,match=match):
        outdoor_scope_evaluation_v2.run(review,tmp_path/'evaluation')
