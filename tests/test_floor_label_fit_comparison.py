from copy import deepcopy

import numpy as np
import pytest

from models import floor_label_fit_comparison as m
from tests.test_bayesian_floor_elevator_design import data
from tests.test_bayesian_feature_report import publish_binary
from tests.test_quarantine_fit_comparison import protocols as prior_protocols


def protocols():
    _,a=prior_protocols()
    a.update(source_version=m.projection.PARENT,rows=100,floor_increment_prior_scale=.15,
             floor_policy='same',floor_thresholds=a['floor_levels'][:-1])
    a['implementation_sha256'].update({'pricing.py':'same','bayesian_floor_increment_design.py':'same'})
    b=deepcopy(a)
    b.update(source_version=m.projection.VERSION,source_directory='candidate',source_manifest_sha256='new',
             source_observations_sha256='new',floor_levels=sorted(a['floor_levels']+[9.]))
    b['floor_thresholds']=b['floor_levels'][:-1]
    b['implementation_sha256']['floor_label_projection.py']='new'
    for key in m.LOADER_CODE & b['implementation_sha256'].keys():b['implementation_sha256'][key]='revised'
    return a,b


@pytest.mark.parametrize('fault',[None,'math','added_code','lost_code','prior','noise','draws','population','thresholds','lost_floor','policy'])
def test_protocol_allows_only_floor_support_and_source_loaders(fault):
    a,b=protocols()
    if fault=='math':b['implementation_sha256']['bayesian_floor_increment_design.py']='changed'
    elif fault=='added_code':b['implementation_sha256']['other.py']='changed'
    elif fault=='lost_code':del b['implementation_sha256']['pricing.py']
    elif fault=='prior':b['floor_increment_prior_scale']=.9
    elif fault=='noise':b['residual_scale']='bedroom'
    elif fault=='draws':b['draws']=50
    elif fault=='population':b['rows']-=1
    elif fault=='thresholds':b['floor_thresholds']=[]
    elif fault=='lost_floor':b['floor_levels']=b['floor_levels'][1:];b['floor_thresholds']=b['floor_levels'][:-1]
    elif fault=='policy':b['floor_policy']='different'
    if fault:
        with pytest.raises(ValueError):m.check_protocols(a,b)
    else:assert set(m.check_protocols(a,b))==m.LOADER_CODE & a['implementation_sha256'].keys()


@pytest.fixture
def fits(tmp_path):
    a=data();b=a.copy();b.loc[b.advertised_floor.isna(),'advertised_floor']=7.
    fits=[]
    for name,frame in [('a',a),('b',b)]:
        design=m.floor.FeatureDesign(frame);target=tmp_path/name/'fit';design.save(target)
        fm=publish_binary(target,{p.name:p.read_bytes() for p in target.iterdir()}, {})
        fits.append({'root':target.parent,'data':frame,'design':design,'provenance':{'fit_manifest':fm},
                     'reconstruction':{'time_arrays':{'same':'same'}}})
    return fits


@pytest.mark.parametrize('fault',[None,'nonfloor_value','nonfloor_prior','nonfloor_center','nonfloor_order','time_arrays'])
def test_expanding_floors_and_missingness_cannot_hide_nonfloor_changes(fits,fault):
    a,b=fits
    index=next(i for i,n in enumerate(b['design'].features) if not m.is_floor(n))
    if fault=='nonfloor_value':b['data'].loc[0,'bedrooms']=4
    elif fault=='nonfloor_prior':b['design'].prior_scales[index]*=2
    elif fault=='nonfloor_center':b['design'].means[index]+=.1
    elif fault=='nonfloor_order':b['design'].features[index]='surprise'
    elif fault=='time_arrays':b['reconstruction']['time_arrays']['same']='changed'
    if fault:
        with pytest.raises(ValueError):m.check_designs(a,b)
    else:
        names=m.check_designs(a,b)
        assert not any(m.is_floor(n) for n in names)
        assert 7. in b['design'].floor_levels and 7. not in a['design'].floor_levels
        assert 'listed_floor.unknown' in a['design'].features and 'listed_floor.unknown' not in b['design'].features


def test_residual_slices_are_explicit_not_a_representative_benchmark():
    before=[{'audit_id':str(i),'unit_id':str(i),'building':'b','advertised_floor':v,
             'analysis_price_basis':'current_capture_gross_ask' if i==0 else 'historical'} for i,v in enumerate([None,3,None])]
    after=deepcopy(before);after[0]['listed_floor']=2
    movement=[{**r,'reference':{'residual_log':.1},'candidate':{'residual_log':.05},'fitted_rent_change':2.} for r in after]
    result=m.residual_slices(before,after,movement)
    assert {k:v['rows'] for k,v in result.items()}=={'all':3,'current_capture':1,'newly_inferred_floor':1,'explicit_floor':1,'missing_floor':1}
    with pytest.raises(ValueError):m.residual_slices(before,after,movement[:-1])


@pytest.mark.parametrize('fault',[None,'bedrooms','price','identity','sidecar'])
def test_published_revision_rejects_source_tampering(tmp_path,fault):
    from apartments.research_pipeline import publish_bundle
    from apartments.corrections import canonical
    from apartments.reviewed_cohort_quarantine import records_hash,sha
    from tests.test_floor_label_projection import example
    row,captures=example();row.update(bedrooms=0,asking_rent=3000)
    parent=tmp_path/'parent';candidate=tmp_path/'candidate'
    publish_bundle(parent,{'observations.jsonl':canonical(row)+'\n'},{'version':m.projection.PARENT})
    import json
    manifest=json.loads((parent/'complete.json').read_text())
    as_of='2026-09-19T12:00:00Z'
    after=m.projection.project_row(row,captures,[],as_of=as_of)
    change={'source_index':0,'source_row_sha256':sha(row),'listed_floor_was_present':False,
            'before_listed_floor':None,'captures':captures}
    if fault=='bedrooms':after['bedrooms']=1
    elif fault=='price':after['asking_rent']=3300
    elif fault=='identity':after['audit_id']='different'
    elif fault=='sidecar':change['source_row_sha256']='a'*64
    publish_bundle(candidate,{'observations.jsonl':canonical(after)+'\n',m.projection.SIDECAR:canonical(change)+'\n'},
        {'version':m.projection.VERSION,'source_manifest':manifest,'source_manifest_sha256':records_hash([manifest]),
         'source_rows':1,'excluded_buildings':[],'interpreted_at':as_of})
    if fault:
        with pytest.raises(ValueError):m.verify_revision(parent,candidate)
    else:assert m.verify_revision(parent,candidate)==([row],[after])


def test_common_endpoints_sum_new_thresholds_with_joint_covariance(fits):
    import xarray as xr
    rng=np.random.default_rng(818)
    for i,f in enumerate(fits):
        d=f['design'];shape=(4,1000)
        beta=rng.normal(0,.04,(*shape,len(d.features)))
        if i:
            # New 5->7 and 7->8 thresholds cancel most joint variation.
            first=d.features.index('listed_floor_gt_5');second=d.features.index('listed_floor_gt_7')
            beta[:,:,second]=.03-beta[:,:,first]+rng.normal(0,.001,shape)
        tree=xr.DataTree.from_dict({'posterior':xr.Dataset({'beta':(('chain','draw','feature'),beta)},coords={'feature':d.features}),
            'sample_stats':xr.Dataset({'energy':(('chain','draw'),rng.normal(size=shape)),
                'diverging':(('chain','draw'),np.zeros(shape,dtype=bool)),
                'maxdepth_reached':(('chain','draw'),np.zeros(shape,dtype=bool))})})
        tree.to_netcdf(f['root']/'fit/posterior.nc',engine='h5netcdf')
        f['protocol']={'chains':4,'draws':1000,'prior_multiplier':1.}
    result=m.contrast_comparison(*fits)
    common=next(r for r in result['common_endpoint_contrasts'] if (r['lower_floor'],r['upper_floor'])==(5.,8.))
    assert common['candidate']['posterior_log_sd']<.002
    assert common['reference']['prior_log_sd']==pytest.approx(.15)
    assert common['candidate']['prior_log_sd']==pytest.approx(.15*np.sqrt(2))
    assert any(r['lower_floor']==7. for r in result['expanded_candidate_contrasts']['contrasts'])
    assert 'posterior_difference' not in common
