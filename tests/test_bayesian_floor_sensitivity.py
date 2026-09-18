from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from models import bayesian_floor_sensitivity as m


def protocols(increment_reference=False):
    a={'version':m.V3,'chains':4,'draws':1000,'tune':500,'seed':1,
       'implementation_sha256':{'math.py':'same'},'source_observations_sha256':'same',
       'graph_configuration':{'residual_scale':'shared'},'prior_multiplier':1.,'building_prior_scale':.35,
       'unit_prior_scale':.25,'versions':{'numpy':'test'}}
    b={**deepcopy(a),'version':m.V4,'seed':2,'feature_design_version':m.floor.VERSION,
       'floor_increment_prior_scale':.15,'floor_levels':[1,3,8],'floor_thresholds':[1,3],
       'floor_policy':'same policy','implementation_sha256':{**a['implementation_sha256'],**{n:'same-floor' for n in m.FLOOR_CODE}}}
    if increment_reference:a=deepcopy(b);a['floor_increment_prior_scale']=.05
    return a,b


@pytest.mark.parametrize('increment_reference',[False,True])
def test_only_floor_basis_or_increment_prior_may_change(increment_reference):
    a,b=protocols(increment_reference);m.check_protocols(a,b)


@pytest.mark.parametrize('change',[{'source_observations_sha256':'changed'},{'building_prior_scale':.7},
    {'prior_multiplier':.5},{'graph_configuration':{'residual_scale':'bedroom'}},{'versions':{'numpy':'changed'}}])
def test_conflated_source_prior_noise_or_environment_rejected(change):
    a,b=protocols();b.update(change)
    with pytest.raises(ValueError):m.check_protocols(a,b)


def test_shared_code_and_floor_code_changes_rejected():
    a,b=protocols();b['implementation_sha256']['math.py']='changed'
    with pytest.raises(ValueError,match='implementation changed'):m.check_protocols(a,b)
    a,b=protocols(True);b['implementation_sha256']['bayesian_floor_increment_design.py']='changed'
    with pytest.raises(ValueError,match='Floor implementation changed'):m.check_protocols(a,b)


def test_floor_directions_use_observed_gaps_and_correct_standardized_linear_scale():
    a=SimpleNamespace(features=['listed_floor','listed_floor.unknown'],numeric={'listed_floor':{'scale':4.}})
    b=SimpleNamespace(features=['listed_floor_gt_1','listed_floor_gt_3','listed_floor.unknown'],floor_thresholds=[1,3])
    pairs,x=m.directions(a,[1,3,8]);_,y=m.directions(b,[1,3,8])
    assert pairs==[(1,3),(3,8),(1,8)]
    np.testing.assert_array_equal(x,[[.5,0],[1.25,0],[1.75,0]])
    np.testing.assert_array_equal(y,[[1,0,0],[0,1,0],[1,1,0]])


def test_nonfloor_check_aligns_names_and_preserves_missingness_prior():
    a=SimpleNamespace(features=['listed_floor','listed_floor.unknown','bedrooms_gt_0'],means=np.array([0,.2,.5]),
        prior_scales=np.array([.15,.2,.25]),matrix=lambda d:np.array([[1,2,3],[4,5,6]]))
    b=SimpleNamespace(features=['bedrooms_gt_0','listed_floor_gt_1','listed_floor.unknown'],means=np.array([.5,0,.2]),
        prior_scales=np.array([.25,.15,.2]),matrix=lambda d:np.array([[3,1,2],[6,4,5]]))
    assert m.verify_other_columns(a,b,None)==['listed_floor.unknown','bedrooms_gt_0']
    b.prior_scales[2]=.1
    with pytest.raises(ValueError,match='Nonfloor'):m.verify_other_columns(a,b,None)


def posterior(tmp_path):
    rng=np.random.default_rng(93);shape=(4,1000)
    common=rng.normal(0,.2,shape);noise=rng.normal(0,.005,shape)
    beta=np.stack([common+.02,-common+.03+noise],axis=-1)
    names=['listed_floor_gt_1','listed_floor_gt_3']
    tree=xr.DataTree.from_dict({'posterior':xr.Dataset({'beta':(('chain','draw','feature'),beta)},coords={'feature':names}),
        'sample_stats':xr.Dataset({'energy':(('chain','draw'),rng.normal(size=shape)),
            'diverging':(('chain','draw'),np.zeros(shape,dtype=bool)),
            'maxdepth_reached':(('chain','draw'),np.zeros(shape,dtype=bool))})})
    (tmp_path/'fit').mkdir();tree.to_netcdf(tmp_path/'fit/posterior.nc',engine='h5netcdf')
    design=SimpleNamespace(features=names,floor_thresholds=[1,3],prior_scales=np.array([.15,.15]))
    return design,{'chains':4,'draws':1000,'prior_multiplier':1.},beta


def test_joint_floor_comparison_preserves_covariance_and_all_draws(tmp_path):
    design,protocol,beta=posterior(tmp_path)
    result=m.joint_floor_contrasts(tmp_path,protocol,design,[1,3,8])
    assert result['draws']==4000 and result['diagnostics']['acceptable']
    interval=result['contrasts'][-1]['log_effect']
    expected=np.quantile(beta.sum(axis=-1),[.025,.5,.975])
    np.testing.assert_allclose([interval[k] for k in ('lower_95','median','upper_95')],expected)
    assert result['contrasts'][-1]['prior_log_sd']==pytest.approx(.15*np.sqrt(2))
    assert result['contrasts'][-1]['posterior_log_sd']<.006


def test_failed_joint_contrast_gate_withholds_comparison(tmp_path,monkeypatch):
    design,protocol,_=posterior(tmp_path)
    monkeypatch.setattr(m.base,'diagnostics',lambda *a:({'acceptable':False},None))
    with pytest.raises(ValueError,match='convergence'):m.joint_floor_contrasts(tmp_path,protocol,design,[1,3,8])


def test_residual_slices_use_alias_and_same_advertisements():
    data=pd.DataFrame([{'audit_id':'a','unit_id':'u','building':'b','advertised_floor':3},
                       {'audit_id':'c','unit_id':'v','building':'b','advertised_floor':None}])
    a=[{'audit_id':'a','residual_log':.1,'fitted_rent':4000},{'audit_id':'c','residual_log':-.2,'fitted_rent':5000}]
    b=[{'audit_id':'a','residual_log':.05,'fitted_rent':4200},{'audit_id':'c','residual_log':-.15,'fitted_rent':5100}]
    rows=m.floor_residual_slices(data,a,b)
    assert rows[0]['slice']=='known listed floor' and rows[0]['rows']==1
    assert rows[0]['median_absolute_fitted_rent_change']==200
    assert rows[1]['slice']=='unknown listed floor'
    with pytest.raises(ValueError,match='cohort'):m.floor_residual_slices(data,a,b[:1])
