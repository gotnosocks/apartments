"""Staged centered hierarchy: equivalent posterior under an explicit Jacobian."""
from types import SimpleNamespace
import numpy as np
import pytest
import pandas as pd
from models import bayesian_feature_graph_v3 as graph
from models import bayesian_feature_model as feature
from models import bayesian_feature_graph as shared_reference

original=SimpleNamespace(build_model=lambda *a,**k:graph.build_model(*a,**k,residual_parameterization='noncentered'))
centered=SimpleNamespace(build_model=lambda *a,**k:graph.build_model(*a,**k,residual_parameterization='centered'))


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

def mapping(point):
    result={key:np.array(value,copy=True) for key,value in point.items() if key!='residual_bedroom_z_zerosum__'}
    tau=np.exp(point['residual_bedroom_scale_log__'])
    result['residual_bedroom_offset_zerosum__']=tau*point['residual_bedroom_z_zerosum__']
    return result,float(tau)


@pytest.mark.parametrize('bath_spec',feature.SPECS)
def test_shared_graph_untouched_density_gradient_priors(bath_spec):
    data=training();design=feature.FeatureDesign(data,bath_spec)
    a=shared_reference.build_model(data,design);b=centered.build_model(data,design)
    assert a.coords==b.coords and a.named_vars_to_dims==b.named_vars_to_dims
    assert [v.name for v in a.free_RVs]==[v.name for v in b.free_RVs]
    functions=[(m.compile_logp(mode='FAST_COMPILE'),m.compile_dlogp(mode='FAST_COMPILE'),
                m.compile_logp(vars=m.free_RVs,sum=False,mode='FAST_COMPILE')) for m in (a,b)]
    for point in points(a):
        for i in (0,1):np.testing.assert_array_equal(functions[0][i](point),functions[1][i](point))
        for x,y in zip(functions[0][2](point),functions[1][2](point)):np.testing.assert_array_equal(x,y)


def test_centered_density_mapping_jacobian_likelihood_scales_and_finite_gradients():
    data=training();design=feature.FeatureDesign(data)
    noncenter=original.build_model(data,design,residual_scale='bedroom')
    center=centered.build_model(data,design,residual_scale='bedroom')
    k=len(noncenter.coords['residual_bedroom']);d=k-1
    assert 'residual_bedroom_offset' in [v.name for v in center.free_RVs]
    assert 'residual_bedroom_z' not in [v.name for v in center.free_RVs]
    assert 'residual_bedroom_z' in [v.name for v in center.deterministics]
    output=[]
    for model in (noncenter,center):
        targets=model.replace_rvs_by_values([model['residual_bedroom_z'],model['sigma_by_bedroom'],model['log_rent'].owner.inputs[-2]])
        output.append((model.compile_logp(mode='FAST_COMPILE'),model.compile_dlogp(mode='FAST_COMPILE'),
                      model.compile_logp(vars=model.observed_RVs,sum=False,mode='FAST_COMPILE'),
                      model.compile_fn(targets,inputs=model.value_vars,on_unused_input='ignore',mode='FAST_COMPILE')))
    for tau in (.02,.15,1.):
        for point in points(noncenter):
            point['residual_bedroom_scale_log__']=np.array(np.log(tau))
            mapped,_=mapping(point)
            a,b=output[0][0](point),output[1][0](mapped)
            assert a==pytest.approx(b+d*np.log(tau),abs=1e-9,rel=1e-12)
            g0,g1=output[0][1](point),output[1][1](mapped)
            assert np.isfinite(g0).all() and np.isfinite(g1).all()
            def unpack(model,values,gradient):
                result={};start=0
                for variable in model.value_vars:
                    shape=np.shape(values[variable.name]);size=int(np.prod(shape)) if shape else 1
                    result[variable.name]=gradient[start:start+size].reshape(shape);start+=size
                assert start==len(gradient)
                return result
            ng,cg=unpack(noncenter,point,g0),unpack(center,mapped,g1)
            zkey='residual_bedroom_z_zerosum__';okey='residual_bedroom_offset_zerosum__';tkey='residual_bedroom_scale_log__'
            np.testing.assert_allclose(ng[zkey],tau*cg[okey],atol=1e-9,rtol=1e-11)
            np.testing.assert_allclose(ng[tkey],cg[tkey]+np.sum(cg[okey]*mapped[okey])+d,atol=1e-9,rtol=1e-11)
            for name in ng.keys()-{zkey,tkey}:
                np.testing.assert_allclose(ng[name],cg[name],atol=1e-9,rtol=1e-11)
            for x,y in zip(output[0][2](point),output[1][2](mapped)):
                np.testing.assert_allclose(x,y,atol=1e-12,rtol=1e-12)
            for x,y in zip(output[0][3](point),output[1][3](mapped)):
                np.testing.assert_allclose(x,y,atol=1e-12,rtol=1e-12)
            # Neither a missing Jacobian nor a K-dimensional Jacobian is valid.
            assert not np.isclose(a,b,atol=1e-8) if tau!=1 else np.isclose(a,b,atol=1e-9)
