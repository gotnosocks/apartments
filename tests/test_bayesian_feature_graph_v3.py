"""Residual-scale extensions preserve mean priors and default posterior exactly."""
import numpy as np
import pandas as pd
import pymc as pm
import pytest
from scipy.stats import t, halfnorm

from models import bayesian_feature_graph_v3 as graph
from models import bayesian_feature_graph as old_graph
from models import bayesian_feature_model as feature


def training():
    rng = np.random.default_rng(741)
    n=120
    full, half = rng.integers(1,6,n), rng.integers(0,3,n)
    return pd.DataFrame({'period':pd.date_range('2020-01-01',periods=36,freq='MS').take(np.arange(n)%36),
        'unit_id':['u'+str(i%60) for i in range(n)],'building':['b'+str(i%6) for i in range(n)],
        'bedrooms':rng.integers(0,6,n).astype(float),'bathrooms':full+.5*half,
        'reported_full_bathrooms':full,'reported_half_bathrooms':half,
        'bathroom_count_evidence':[{'flags':[]} for _ in range(n)],
        'square_feet':rng.uniform(400,2400,n),'asking_rent':rng.uniform(2000,15000,n),
        'laundry_type':rng.choice(['in_unit','in_building',None],n)})


def points(model):
    initial=model.initial_point();rng=np.random.default_rng(381)
    return [initial,*[{k:np.asarray(v)+rng.normal(0,scale,np.shape(v)) for k,v in initial.items()}
                      for scale in (.035,.17)]]


@pytest.mark.parametrize('spec',feature.SPECS)
def test_shared_defaults_match_existing_density_gradient_and_individual_priors(spec):
    data=training();design=feature.FeatureDesign(data,spec)
    old=old_graph.build_model(data,design,prior_multiplier=1.3)
    new=graph.build_model(data,design,prior_multiplier=1.3)
    assert old.coords == new.coords
    assert old.named_vars_to_dims == new.named_vars_to_dims
    assert [rv.name for rv in old.free_RVs] == [rv.name for rv in new.free_RVs]
    assert [v.name for v in old.value_vars] == [v.name for v in new.value_vars]
    for key,value in old.initial_point().items(): np.testing.assert_array_equal(value,new.initial_point()[key])
    functions = [(m.compile_logp(mode='FAST_COMPILE'),m.compile_dlogp(mode='FAST_COMPILE'),
                  m.compile_logp(vars=m.free_RVs,sum=False,mode='FAST_COMPILE')) for m in [old,new]]
    for point in points(old):
        np.testing.assert_array_equal(functions[0][0](point),functions[1][0](point))
        np.testing.assert_array_equal(functions[0][1](point),functions[1][1](point))
        for a,b in zip(functions[0][2](point),functions[1][2](point)):np.testing.assert_array_equal(a,b)
    assert new.graph_configuration['residual_bedroom_levels'] == []


def test_bedroom_scales_likelihood_and_gradients_match_explicit_formula():
    data=training();design=feature.FeatureDesign(data)
    model=graph.build_model(data,design,residual_scale='bedroom',residual_parameterization='noncentered')
    config=model.graph_configuration
    assert config == graph.graph_configuration(data,residual_scale='bedroom',residual_parameterization='noncentered')
    assert config['residual_bedroom_levels'] == list(range(6))
    assert config['residual_bedroom_counts'] == [int(data.bedrooms.eq(i).sum()) for i in range(6)]
    assert model.named_vars_to_dims['sigma_by_bedroom'] == ('residual_bedroom',)
    value_outputs=model.replace_rvs_by_values([model['sigma'],model['residual_bedroom_scale'],
                                              model['residual_bedroom_z'],model['sigma_by_bedroom'],
                                              model['log_rent'].owner.inputs[-2]])
    evaluated=model.compile_fn(value_outputs,inputs=model.value_vars,on_unused_input='ignore',mode='FAST_COMPILE')
    likelihood=model.compile_logp(vars=model.observed_RVs,mode='FAST_COMPILE')
    density=model.compile_logp(mode='FAST_COMPILE');gradient=model.compile_dlogp(mode='FAST_COMPILE')
    for point in points(model):
        sigma,scale,z,sigmas,mu=evaluated(point)
        assert abs(z.sum()) < 1e-14
        np.testing.assert_allclose(sigmas,sigma*np.exp(scale*z),rtol=1e-14)
        assert np.all(sigmas > 0)
        assert np.exp(np.log(sigmas).mean()) == pytest.approx(sigma,rel=1e-14)
        expected=t.logpdf(np.log(data.asking_rent),df=5,loc=mu,
                          scale=sigmas[graph.bedroom_index(data.bedrooms,config['residual_bedroom_levels'])]).sum()
        # PyMC folds distribution constants at framework precision; allow 1e-8
        # per observation against independent SciPy arithmetic, not a loose fit tolerance.
        assert float(likelihood(point)) == pytest.approx(expected,rel=1e-12,abs=len(data)*1e-8)
        assert np.isfinite(density(point)) and np.isfinite(gradient(point)).all()
    initial=model.initial_point()
    initial['residual_bedroom_z_zerosum__']=np.array([-.7,-.3,.1,.4,.9])
    assert np.ptp(evaluated(initial)[3]) > .01


def test_noise_alternative_does_not_change_mean_or_shared_priors():
    data=training();design=feature.FeatureDesign(data)
    shared=graph.build_model(data,design)
    bedroom=graph.build_model(data,design,residual_scale='bedroom')
    common=[rv.name for rv in shared.free_RVs]
    a=shared.compile_logp(vars=shared.free_RVs,sum=False,mode='FAST_COMPILE')
    b=bedroom.compile_logp(vars=[bedroom[n] for n in common],sum=False,mode='FAST_COMPILE')
    for point in points(shared):
        # Compile only common priors: new scale parameters have no influence.
        for left,right in zip(a(point),b(bedroom.initial_point() | point)):np.testing.assert_array_equal(left,right)
    for model in (shared,bedroom):
        output=model.replace_rvs_by_values([model['log_rent'].owner.inputs[-2]])
        fn=model.compile_fn(output,inputs=model.value_vars,on_unused_input='ignore',mode='FAST_COMPILE')
        point=model.initial_point()
        value=fn(point)[0]
        if model is shared:expected=value
        else:np.testing.assert_array_equal(value,expected)


@pytest.mark.parametrize('kwargs',[{'building_prior_scale':.7},{'unit_prior_scale':.5}])
def test_group_prior_alternative_changes_only_named_hyperprior(kwargs):
    data=training();design=feature.FeatureDesign(data)
    base=graph.build_model(data,design);changed=graph.build_model(data,design,**kwargs)
    name='sigma_building' if 'building_prior_scale' in kwargs else 'sigma_unit'
    original_scale=.35 if name=='sigma_building' else .25
    new_scale=next(iter(kwargs.values()))
    a=base.compile_logp(vars=base.free_RVs,sum=False,mode='FAST_COMPILE')
    b=changed.compile_logp(vars=changed.free_RVs,sum=False,mode='FAST_COMPILE')
    index=[rv.name for rv in base.free_RVs].index(name)
    point=base.initial_point()
    first,second=a(point),b(point)
    for i,(left,right) in enumerate(zip(first,second)):
        if i != index:np.testing.assert_array_equal(left,right)
    actual=float(np.exp(point[name+'_log__']))
    assert float(second[index]-first[index]) == pytest.approx(
        halfnorm.logpdf(actual,scale=new_scale)-halfnorm.logpdf(actual,scale=original_scale),abs=5e-9)


def test_bedroom_level_mapping_is_stable_and_unsupported_values_rejected():
    np.testing.assert_array_equal(graph.bedroom_index([3.,0.,1.,3.],[0,1,3]),[2,0,1,2])
    data=training()
    config=graph.graph_configuration(data,residual_scale='bedroom')
    assert graph.graph_configuration(data.sample(frac=1,random_state=8),residual_scale='bedroom') == config
    for values,levels in [([2],[0,1,3]),([np.nan],[0,1]),([1.5],[0,1]),([-1],[0,1]),
                          ([1],[1,0]),([1],[0,1,1]),([True],[0,1]),(['1'],[0,1])]:
        with pytest.raises(ValueError):graph.bedroom_index(values,levels)
    for values in [[0]*len(data),[np.nan]*len(data),[1.5]*len(data)]:
        invalid=data.assign(bedrooms=values)
        with pytest.raises(ValueError):graph.graph_configuration(invalid,residual_scale='bedroom')


@pytest.mark.parametrize('name',['prior_multiplier','building_prior_scale','unit_prior_scale'])
@pytest.mark.parametrize('value',[0,-.2,float('nan'),float('inf'),True])
def test_invalid_hyperprior_scales_fail_before_model_build(name,value):
    with pytest.raises(ValueError,match='finite positive'):
        graph.graph_configuration(training(),**{name:value})
