"""Known-category contrasts preserve joint posterior covariance and source support."""
import numpy as np
import pandas as pd
import pytest

from models import bayesian_category_contrasts as m
from models.bayesian_feature_model import FeatureDesign


def training():
    rng=np.random.default_rng(126);n=240
    full=rng.integers(1,5,n);half=rng.integers(0,2,n)
    return pd.DataFrame({'period':pd.date_range('2020-01-01',periods=36,freq='MS').take(np.arange(n)%36),
        'unit_id':['u'+str(i%80) for i in range(n)],'building':['b'+str(i%8) for i in range(n)],
        'bedrooms':rng.integers(0,5,n),'bathrooms':full+.5*half,'reported_full_bathrooms':full,
        'reported_half_bathrooms':half,'bathroom_count_evidence':[{'flags':[]} for _ in range(n)],
        'square_feet':rng.uniform(400,2400,n),'asking_rent':rng.uniform(2000,15000,n),
        'laundry_type':rng.choice(['in_building','in_unit',None],n),
        'doorman_type':rng.choice(['full_time','part_time','none',None],n)})


def test_actual_design_delta_changes_only_category_and_preserves_knownness():
    data=training();design=FeatureDesign(data)
    v=m.contrast_vector(design,data,'laundry_type','in_building','in_unit')
    expected=np.zeros(len(design.features));expected[design.features.index('laundry_type.contrast_0')]=np.sqrt(2)
    np.testing.assert_allclose(v,expected,rtol=0,atol=1e-14)
    assert v[design.features.index('laundry_type.unknown')] == 0
    reverse=m.contrast_vector(design,data,'laundry_type','in_unit','in_building')
    np.testing.assert_array_equal(v,-reverse)
    with pytest.raises(ValueError,match='known category'):
        m.contrast_vector(design,data,'laundry_type','__unknown__','in_unit')


def test_complete_pairs_support_overlap_and_unknown_are_recomputed():
    data=training();design=FeatureDesign(data)
    categories,pairs,omitted=m.construct_contrasts(design,data)
    assert len(pairs)==4 and not omitted
    laundry=next(r for r in categories if r['field']=='laundry_type')
    assert laundry['unknown']['rows']==int(data.laundry_type.isna().sum())
    assert laundry['known']['rows']+laundry['unknown']['rows']==len(data)
    contrast=next(r for r in pairs if r['field']=='laundry_type')
    a=data.loc[data.laundry_type.eq('in_building')];b=data.loc[data.laundry_type.eq('in_unit')]
    assert contrast['support_before']==m.support(a)
    assert contrast['overlap']['buildings']==len(set(a.building)&set(b.building))
    assert contrast['overlap']['units']==len(set(a.unit_id)&set(b.unit_id))
    assert any(r['before']=='part_time' and r['after']=='full_time' and r['highlight'] for r in pairs)
    # Explicit no-doorman observations remain distinct from unknown reporting.
    doorman=next(r for r in categories if r['field']=='doorman_type')
    assert next(r for r in doorman['levels'] if r['category']=='none')['rows']==int(data.doorman_type.eq('none').sum())


def test_joint_contrast_uncertainty_preserves_strong_coefficient_covariance():
    rng=np.random.default_rng(631)
    common=rng.normal(size=(4,2000));difference=rng.normal(.1,.01,size=(4,2000))
    beta=np.stack([common+difference,common],axis=2)
    results,_=m.calculate(beta,[{'id':'example:a->b','design_vector':[1.,-1.]}])
    result=results[0]
    assert result['diagnostics']['acceptable']
    assert result['log_effect']['median']==pytest.approx(np.median(difference),abs=1e-12)
    assert result['log_effect']['upper_95']-result['log_effect']['lower_95']<.045
    assert result['percent_effect']['median']==pytest.approx(np.median(100*np.expm1(difference)),abs=1e-12)


def test_unmixed_derived_contrast_withholds_intervals():
    rng=np.random.default_rng(642);beta=rng.normal(size=(4,1000,1))
    beta[0,:,0]+=4
    result,_=m.calculate(beta,[{'id':'bad:a->b','design_vector':[1.]}])
    assert result[0]['status']=='withheld_derived_diagnostics'
    assert result[0]['log_effect'] is None and result[0]['percent_effect'] is None


def test_report_gate_refuses_unaccepted_fit_before_posterior_read(monkeypatch,tmp_path):
    def reject(*args,**kwargs):raise ValueError('Unacceptable derived diagnostics')
    monkeypatch.setattr(m.report,'build_report',reject)
    with pytest.raises(ValueError,match='derived diagnostics'):
        m.run(tmp_path/'fit',tmp_path/'data',tmp_path/'out')
    assert not (tmp_path/'out').exists()
