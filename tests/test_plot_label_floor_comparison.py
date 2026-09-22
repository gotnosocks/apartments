
import numpy as np
import pytest
import xarray as xr

from models import plot_label_floor_comparison as m
from tests.test_bayesian_floor_elevator_design import data


def fitted(tmp_path, *, elevated=False, unmixed=False):
    frame=data();frame.loc[frame.advertised_floor.isna(),'advertised_floor']=1.
    d=m.interaction.FeatureDesign(frame) if elevated else m.floor.FeatureDesign(frame)
    rng=np.random.default_rng(14);beta=rng.normal(0,.05,(4,1000,len(d.features)))
    if elevated:
        # Covariance yields a tight floor2->3 curve at known elevator=True.
        beta[:,:,d.features.index('listed_floor_gt_2')]=-.5*beta[:,:,-1]/np.sqrt(3)+rng.normal(.02,.001,(4,1000))
    if unmixed:beta[0,:,d.features.index('listed_floor_gt_2')]+=4
    target=tmp_path/'fit';target.mkdir()
    xr.Dataset({'beta':(('chain','draw','feature'),beta)},coords={'feature':d.features}).to_netcdf(target/'posterior.nc',group='posterior',engine='h5netcdf')
    return {'root':tmp_path,'data':frame,'design':d,'protocol':{'chains':4,'draws':1000,'prior_multiplier':1.}}


def test_curve_requires_supported_endpoints_and_handles_reverse_direction(tmp_path):
    f=fitted(tmp_path);d=f['design']
    reverse=m.vector(d,f['data'],1.)
    assert reverse[d.features.index('listed_floor_gt_1')]==-1
    assert np.count_nonzero(reverse)==1
    with pytest.raises(ValueError,match='extrapolation'):m.vector(d,f['data'],52.)
    result=m.curve(f)
    anchor=next(r for r in result['points'] if r['floor']==2)
    assert anchor['status']=='deterministic_reference' and 'ess_bulk' not in anchor['diagnostics']
    assert [r['floor'] for r in result['points']]==d.floor_levels


def test_elevator_curve_preserves_joint_covariance_and_reverse_floor(tmp_path):
    f=fitted(tmp_path,elevated=True)
    with pytest.raises(ValueError,match='explicit elevator'):m.vector(f['design'],f['data'],3.)
    curve=m.curve(f,True);point=next(r for r in curve['points'] if r['floor']==3.)
    assert point['diagnostics']['acceptable']
    assert point['percent_effect']['upper_95']-point['percent_effect']['lower_95']<.5
    assert m.vector(f['design'],f['data'],1.,False)[f['design'].features.index('listed_floor_gt_1')]==-1


def test_unmixed_cumulative_contrasts_are_withheld(tmp_path):
    f=fitted(tmp_path,unmixed=True);curve=m.curve(f)
    point=next(r for r in curve['points'] if r['floor']==3.)
    assert point['status']=='withheld_derived_diagnostics'
    assert point['percent_effect'] is None and curve['withheld_points']>0


def test_source_counts_preserve_explicit_proxy_and_missing():
    frame=data().iloc[:3].copy();frame['advertised_floor']=[2,2,None]
    frame['floor_label_provenance']=[{}, {'status':'label_proxy'},{}]
    result=m.source_counts(frame)
    assert result['missing_rows']==1
    assert result['levels'][0]['explicit_rows']==1 and result['levels'][0]['label_proxy_rows']==1


def test_scientific_plot_exports_deterministic_binary_artifacts(tmp_path):
    f=fitted(tmp_path);curve=m.curve(f);counts=m.source_counts(f['data'])
    result={'curves':dict.fromkeys(('explicit_source_baseline','expanded_label_floor','expanded_with_elevator','expanded_without_elevator'),curve),
            'source_counts':{'baseline':counts,'expanded':counts}}
    first=m.render(result);second=m.render(result)
    assert first==second
    assert first['floor-curves.png'].startswith(b'\x89PNG') and b'<svg' in first['floor-curves.svg']
    out=tmp_path/'published'
    manifest=m.publisher._publish(out,first,{'version':m.VERSION})
    assert m.publisher._publish(out,second,{'version':m.VERSION})==manifest


def test_empty_joint_floor_access_cell_withholds_display_but_keeps_diagnostics(tmp_path):
    f=fitted(tmp_path,elevated=True)
    f['data'].loc[f['data'].advertised_floor==8.,'elevator']=True
    result=m.curve(f,False)
    unsupported=next(r for r in result['points'] if r['floor']==8.)
    assert unsupported['diagnostics']['acceptable']
    assert unsupported['status']=='supported_converged'
    assert unsupported['source_support_status']=='withheld_missing_joint_floor_access_endpoint'
    assert unsupported['display_percent_effect'] is None
    assert unsupported['percent_effect'] is not None
    assert result['source_withheld_points']==1 and result['withheld_points']==0
    supported=next(r for r in result['points'] if r['floor']==3.)
    assert supported['display_percent_effect'] is not None
