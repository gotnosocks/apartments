from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from models import floor_spline_fit_comparison as m
from tests.test_bayesian_floor_increment_design import train
from tests.test_bayesian_floor_spline_design import spline_train
from tests.test_quarantine_fit_comparison import protocols as old_protocols


def protocols():
    a,_=old_protocols()
    a.update(version=m.shared.floors.V4,chains=4,tune=4000,draws=6000,seed=20260924,
        adaptation='diag',target_accept=.93,residual_scale='shared',maxdepth=14,
        floor_levels=[1.,2.,3.,5.,10.],floor_thresholds=[1.,2.,3.,5.],floor_increment_prior_scale=.15)
    a['implementation_sha256'].update({'bayesian_feature_experiment_v4.py':'v4','bayesian_floor_increment_design.py':'math'})
    b=deepcopy(a);b.update(version=m.experiment.VERSION,feature_design_version=m.spline.VERSION,
        floor_prior_scale=.1,floor_knots=[1.,5.,10.],floor_reference=2.,floor_policy=m.spline.policy(),maxdepth=10)
    b.pop('floor_increment_prior_scale');b.pop('floor_thresholds')
    b['implementation_sha256'].pop('bayesian_feature_experiment_v4.py')
    b['implementation_sha256'].update(dict.fromkeys(m.ADDED,'spline'))
    return a,b


@pytest.mark.parametrize('fault',[None,'source','rows','draws','group_prior','math','invented_code','depth','knots','seed'])
def test_only_floor_representation_prior_and_documented_execution_change(fault):
    a,b=protocols()
    if fault=='source':b['source_observations_sha256']='changed'
    if fault=='rows':b['rows']=999
    if fault=='draws':b['draws']=50
    if fault=='group_prior':b['unit_prior_scale']=9
    if fault=='math':b['implementation_sha256']['bayesian_floor_increment_design.py']='changed'
    if fault=='invented_code':b['implementation_sha256']['other.py']='changed'
    if fault=='depth':b['maxdepth']=12
    if fault=='knots':b['floor_knots']=[1,10]
    if fault=='seed':b['seed']=1
    if fault:
        with pytest.raises(ValueError):m.check_protocols(a,b)
    else:assert m.check_protocols(a,b)==[]


@pytest.mark.parametrize('fault',[None,'center','prior','matrix','unknown'])
def test_nonfloor_and_missingness_invariants(spline_train,fault):
    a=m.increment.FeatureDesign(spline_train);b=m.spline.FeatureDesign(spline_train)
    other=spline_train.copy();name=next(n for n in b.features if not m.is_floor(n));i=b.features.index(name)
    if fault=='center':b.means[i]+=.1
    if fault=='prior':b.prior_scales[i]+=.1
    if fault=='matrix':
        original=b.matrix
        def altered(data):
            values=original(data);values[0,i]+=.1;return values
        b.matrix=altered
    if fault=='unknown':b.prior_scales[b.features.index('listed_floor.unknown')]+=.1
    if fault:
        with pytest.raises(ValueError):m.check_design_arrays(a,b,spline_train,other)
    else:assert name in m.check_design_arrays(a,b,spline_train,other)


def test_joint_curve_preserves_covariance_and_prior(spline_train):
    design=m.spline.FeatureDesign(spline_train)
    rng=np.random.default_rng(54);beta=rng.normal(size=(4,1500,len(design.features)))
    i,j=[design.features.index(f'listed_floor_spline_{n}') for n in (0,1)]
    beta[:,:,j]=-.9*beta[:,:,i]+rng.normal(scale=.05,size=(4,1500))
    curve=m.curve_from_draws(design,beta,1.)
    row=next(r for r in curve['points'] if r['floor']==10)
    vector=design.contrast_vector(2.,10.);joint=np.einsum('cdf,f->cd',beta,vector).ravel()
    assert row['log_effect']['median']==pytest.approx(np.median(joint))
    assert row['log_effect']['lower_95']==pytest.approx(np.quantile(joint,.025))
    assert row['normal_prior_log_sd']==pytest.approx(np.linalg.norm(vector*design.prior_scales))
    anchor=next(r for r in curve['points'] if r['floor']==2)
    assert anchor['log_effect']['median']==anchor['normal_prior_log_sd']==0
    assert anchor['diagnostics']=={'deterministic':True}


def test_floor_vector_reverses_below_anchor_and_refuses_extrapolation():
    d=SimpleNamespace(floor_levels=[1.,2.,3.],floor_thresholds=[1.,2.],features=[m.increment._name(1.),m.increment._name(2.)])
    np.testing.assert_array_equal(m.curve_vector(d,1.),[-1,0])
    np.testing.assert_array_equal(m.curve_vector(d,3.),[0,1])
    with pytest.raises(ValueError):m.curve_vector(d,4.)


def test_unmixed_curves_withheld_and_render_is_deterministic(spline_train):
    d=m.spline.FeatureDesign(spline_train);rng=np.random.default_rng(51)
    beta=rng.normal(size=(4,600,len(d.features)));beta+=np.arange(4)[:,None,None]*10
    curve=m.curve_from_draws(d,beta,1.)
    assert curve['withheld_points']>0
    assert all(r['log_effect'] is None for r in curve['points'] if r['status']=='withheld_derived_diagnostics')
    result={'curves':[curve,curve]};a=m.render(result);b=m.render(result)
    assert a==b and a['floor-curves.png'].startswith(b'\x89PNG')


def test_floor_parameter_uncertainty_and_ess_are_bound(monkeypatch,tmp_path):
    import json
    contents={'parameter-diagnostics.csv':b'parameter,ess_bulk,ess_tail,r_hat,mcse_mean,mcse_sd\nbeta[listed_floor_spline_0],800,900,1.001,0.001,0.002\n',
        'coefficients.json':json.dumps([{'feature':'listed_floor_spline_0','median':.03,'lower_95':-.02,'upper_95':.08}]).encode()}
    monkeypatch.setattr(m.shared.common,'bound_bytes',lambda root,name,manifest:contents[name])
    fit={'root':tmp_path,'provenance':{'fit_manifest':{}},'protocol':{'prior_multiplier':1.},
        'design':SimpleNamespace(features=['listed_floor_spline_0'],prior_scales=np.array([.1]))}
    row=m.floor_parameter_diagnostics(fit)[0]
    assert row['diagnostics']['ess_bulk']==800 and row['prior_sd']==.1
    assert row['posterior']['lower_95']==-.02
