from models.bathroom_evidence_audit import reported_bathrooms
from models.bathroom_projection import project


def cap(full,half):
    return {'capture_id':1,'bathroom_fields':reported_bathrooms({'propertyDetails':{'fullBathroomCount':full,'halfBathroomCount':half}})}


def test_missing_half_preserves_known_full_without_zero_imputation():
    source={'bathrooms':2,'retained':'exact'}
    r=project(source,[cap(2,None)])
    assert all(r[k]==v for k,v in source.items())
    assert r['reported_full_bathrooms']==2
    assert r['reported_half_bathrooms'] is None


def test_per_field_disagreement_leaves_only_that_count_unknown():
    r=project({'bathrooms':2},[cap(1,2),cap(2,2)])
    assert r['reported_full_bathrooms'] is None
    assert r['reported_half_bathrooms']==2
    assert r['bathroom_count_evidence']['full_status']=='conflicting_capture_values'


def test_unusual_pair_retained_and_flagged_never_repaired():
    r=project({'bathrooms':3.5},[cap(1,5)])
    assert r['reported_half_bathrooms']==5
    assert r['bathroom_count_evidence']['flags']==['multiple_reported_half_bathrooms_review_required']


def test_scalar_disagreement_explicit_not_overwritten():
    r=project({'bathrooms':3},[cap(2,0)])
    assert r['bathrooms']==3
    assert 'reported_counts_disagree_with_analytical_scalar' in r['bathroom_count_evidence']['flags']
