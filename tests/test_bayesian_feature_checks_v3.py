"""Predictive checks must use the fitted joint bedroom-specific noise draws."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from models import bayesian_feature_checks_v3 as m


@pytest.fixture
def bedroom_case(tmp_path):
    data=pd.DataFrame({'bedrooms':[3.,0.,3.,0.]})
    config=m.graph.graph_configuration(data,residual_scale='bedroom')
    protocol={'version':m.V3_EXPERIMENT,'chains':2,'draws':4,'prior_multiplier':1.,
              'residual_scale':'bedroom','building_prior_scale':.35,'unit_prior_scale':.25,
              'graph_configuration':config,'residual_parameterization':'centered'}
    design=SimpleNamespace(features=['x'],time=SimpleNamespace(buildings=['a','b'],unit_ids=['u','v'],
                            time_matrix=np.zeros((3,2)),season_matrix=np.zeros((12,2))))
    coords={'chain':[1,3],'draw':[10,11,12,13],'feature':['x'],'building':['a','b'],'unit':['u','v'],
            'trend_basis':[0,1],'season_basis':[0,1],'residual_bedroom':[0,3]}
    rng=np.random.default_rng(527)
    variables={name:(('chain','draw',*dims),rng.normal(size=(2,4)+tuple(len(coords[d]) for d in dims)))
               for name,dims in m.common.VARIABLE_DIMS.items()}
    sigma=np.arange(8).reshape(2,4)*.02+.05
    z=np.stack([-np.arange(8).reshape(2,4)/5,np.arange(8).reshape(2,4)/5],axis=2)
    scale=np.arange(8).reshape(2,4)*.03+.2
    variables.update(sigma=(('chain','draw'),sigma),sigma_unit=(('chain','draw'),sigma*.5),
        residual_bedroom_z=(('chain','draw','residual_bedroom'),z),
        residual_bedroom_offset=(('chain','draw','residual_bedroom'),scale[:,:,None]*z),
        residual_bedroom_scale=(('chain','draw'),scale),
        sigma_by_bedroom=(('chain','draw','residual_bedroom'),sigma[:,:,None]*np.exp(scale[:,:,None]*z)))
    posterior=xr.Dataset(variables,coords=coords)
    path=tmp_path/'posterior.nc';posterior.to_netcdf(path,group='posterior',engine='h5netcdf')
    (tmp_path/'graph-configuration.json').write_text(json.dumps(config))
    return path,posterior,protocol,config,design,data


def test_verified_configuration_recomputed_against_exact_source_and_saved_graph(bedroom_case,tmp_path):
    _,_,protocol,config,_,data=bedroom_case
    assert m.verified_configuration(protocol,data,tmp_path) == config
    for field,value in [('residual_scale','shared'),('unit_prior_scale',.4),('prior_multiplier',.5)]:
        mutated={**protocol,field:value}
        with pytest.raises(ValueError,match='configuration differs'):
            m.verified_configuration(mutated,data,tmp_path)
    with pytest.raises(ValueError,match='configuration differs'):
        m.verified_configuration(protocol,pd.concat([data,data.iloc[:1]]),tmp_path)
    (tmp_path/'graph-configuration.json').write_text(json.dumps({**config,'student_t_nu':7.}))
    with pytest.raises(ValueError,match='configuration differs'):
        m.verified_configuration(protocol,data,tmp_path)
    with pytest.raises(ValueError,match='Unsupported posterior experiment'):
        m.verified_configuration({'version':'future'},data,tmp_path)


def test_v4_uses_same_explicit_noise_contract_and_requires_floor_code(bedroom_case,tmp_path):
    _,_,protocol,config,_,data=bedroom_case
    protocol={**protocol,'version':m.V4_EXPERIMENT}
    assert m.verified_configuration(protocol,data,tmp_path)==config
    protocol['implementation_sha256']={'bayesian_feature_graph_v3.py':'x','bayesian_feature_experiment_v3.py':'y'}
    with pytest.raises(ValueError,match='Missing v4'):
        m.verify_implementation(protocol)


def test_lazy_joint_noise_selection_and_replication_exactly_follow_bedroom_mapping(bedroom_case):
    path,posterior,protocol,config,design,data=bedroom_case
    samples,selected=m.load_draws(path,protocol,design,config,per_chain=2)
    assert [s['draw_index'] for s in selected] == [1,3,1,3]
    assert [s['chain_coordinate'] for s in selected] == [1,1,3,3]
    for name in m.BEDROOM_DIMS:
        expected=np.concatenate([posterior[name].isel(chain=c,draw=[1,3]).values for c in range(2)])
        np.testing.assert_array_equal(samples[name],expected)
    rows=m.row_scales(samples,config,data.bedrooms)
    np.testing.assert_array_equal(rows,samples['sigma_by_bedroom'][:,[1,0,1,0]])
    seed=817
    expected=np.random.default_rng(seed).standard_t(5,size=(4,4))*samples['sigma_by_bedroom'][:,[1,0,1,0]]
    np.testing.assert_array_equal(m.replicate_residuals(samples,config,data.bedrooms,seed),expected)
    # This would catch silently substituting the global geometric-mean sigma.
    wrong=np.random.default_rng(seed).standard_t(5,size=(4,4))*samples['sigma'][:,None]
    assert np.max(abs(expected-wrong)) > .02


@pytest.mark.parametrize('mutation',['missing','coordinate','scale_identity','zero_sum','negative','wrong_dimensions','offset_identity','offset_missing'])
def test_invalid_bedroom_posterior_is_refused_before_replication(bedroom_case,mutation):
    path,p,protocol,config,design,_=bedroom_case
    if mutation=='missing':p=p.drop_vars('sigma_by_bedroom')
    elif mutation=='offset_missing':p=p.drop_vars('residual_bedroom_offset')
    elif mutation=='offset_identity':p['residual_bedroom_offset'].values[0,1,0]+=.1
    elif mutation=='coordinate':p=p.assign_coords(residual_bedroom=[3,0])
    elif mutation=='scale_identity':p['sigma_by_bedroom'].values[0,1,0]*=1.1
    elif mutation=='zero_sum':p['residual_bedroom_z'].values[0,1,0]+=.1
    elif mutation=='negative':p['residual_bedroom_scale'].values[0,1]=-.2
    else:p['sigma_by_bedroom']=p['sigma_by_bedroom'].transpose('draw','chain','residual_bedroom')
    p.to_netcdf(path,group='posterior',engine='h5netcdf',mode='w')
    with pytest.raises(ValueError):m.load_draws(path,protocol,design,config,per_chain=2)


def test_bedroom_reconstruction_cannot_fall_back_or_accept_unseen_count(bedroom_case):
    path,_,protocol,config,design,data=bedroom_case
    samples,_=m.load_draws(path,protocol,design,config,per_chain=2)
    missing={k:v for k,v in samples.items() if k!='sigma_by_bedroom'}
    with pytest.raises(ValueError,match='required'):m.replicate_residuals(missing,config,data.bedrooms,1)
    with pytest.raises(ValueError,match='Unsupported bedroom'):m.replicate_residuals(samples,config,[2,0],1)
    with pytest.raises(ValueError,match='degrees of freedom'):
        m.replicate_residuals(samples,{**config,'student_t_nu':7.},data.bedrooms,1)


def test_shared_and_legacy_v2_use_exact_original_shared_replication(bedroom_case,tmp_path):
    path,p,protocol,_,design,data=bedroom_case
    shared=m.graph.graph_configuration(data)
    with pytest.raises(ValueError,match='Shared residual fit'):
        m.load_draws(path,protocol,design,shared,per_chain=2)
    p=p.drop_vars(list(m.BEDROOM_DIMS)).drop_dims('residual_bedroom')
    p.to_netcdf(path,group='posterior',engine='h5netcdf',mode='w')
    samples,_=m.load_draws(path,protocol,design,shared,per_chain=2)
    expected=np.random.default_rng(61).standard_t(5,size=(4,4))*samples['sigma'][:,None]
    np.testing.assert_array_equal(m.replicate_residuals(samples,shared,data.bedrooms,61),expected)
    legacy={'version':m.V2_EXPERIMENT,'prior_multiplier':1.}
    assert m.verified_configuration(legacy,data,tmp_path) == shared
    with pytest.raises(ValueError,match='cannot declare'):
        m.verified_configuration({**legacy,'residual_scale':'bedroom'},data,tmp_path)


def test_v3_implementation_and_report_gates_fail_closed(monkeypatch,tmp_path):
    with pytest.raises(ValueError,match='Missing v3 graph'):
        m.verify_implementation({'version':m.V3_EXPERIMENT,'implementation_sha256':{}})
    def reject(*args,**kwargs):raise ValueError('Unacceptable derived diagnostics')
    monkeypatch.setattr(m.report,'build_report',reject)
    monkeypatch.setattr(m,'load_draws',lambda *a,**k:pytest.fail('Read unaccepted posterior'))
    with pytest.raises(ValueError,match='derived diagnostics'):
        m.run(tmp_path/'fit',tmp_path/'source',tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_spline_uses_explicit_noise_contract_and_requires_its_producer(bedroom_case,tmp_path):
    _,_,protocol,config,_,data=bedroom_case
    protocol={**protocol,'version':m.SPLINE_EXPERIMENT}
    assert m.verified_configuration(protocol,data,tmp_path)==config
    protocol['implementation_sha256']={'bayesian_feature_graph_v3.py':'x','bayesian_feature_experiment_v3.py':'y'}
    with pytest.raises(ValueError,match='Missing spline'):
        m.verify_implementation(protocol)
