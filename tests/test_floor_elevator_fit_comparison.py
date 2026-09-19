from copy import deepcopy
import json

import numpy as np
import pytest
import xarray as xr

from apartments.corrections import canonical
from models import floor_elevator_fit_comparison as m
from models import bayesian_floor_elevator_experiment as experiment
from tests.test_bayesian_floor_elevator_design import data
from tests.test_bayesian_feature_report import publish_binary
from tests.test_quarantine_fit_comparison import protocols as old_protocols


def protocols():
    _,a = old_protocols()
    a.update(version=m.shared.report.EXPERIMENT_V4,feature_design_version=m.contract.BASE)
    b = deepcopy(a)
    b.update(version=m.contract.EXPERIMENT,feature_design_version=m.contract.DESIGN,
        base_feature_design_version=m.contract.BASE,interaction_mode='pooled',
        interaction_prior_scale=.15,interaction_thresholds=m.contract.THRESHOLDS.copy(),
        interaction_policy=m.contract.POLICY)
    b['implementation_sha256'].update(dict.fromkeys(m.ADDED_CODE,'added'))
    return a,b


@pytest.mark.parametrize('fault',[None,'source','draws','base_prior','noise','code','added_code','storage','thresholds','policy','scale'])
def test_comparison_confines_changes_to_interaction(fault):
    a,b = protocols()
    if fault == 'source':b['source_observations_sha256']='changed'
    elif fault == 'draws':b['draws']=50
    elif fault == 'base_prior':b['floor_increment_prior_scale']=.9
    elif fault == 'noise':b['residual_scale']='bedroom'
    elif fault == 'code':b['implementation_sha256'][next(iter(a['implementation_sha256']))]='changed'
    elif fault == 'added_code':b['implementation_sha256']['extra.py']='extra'
    elif fault == 'storage':b['storage_policy']['all_retained_draws']=False
    elif fault == 'thresholds':b['interaction_thresholds'].append(5.)
    elif fault == 'policy':b['interaction_policy']='Unknown is no'
    elif fault == 'scale':b['interaction_prior_scale']=float('nan')
    if fault:
        with pytest.raises(ValueError):m.check_protocols(a,b)
    else:m.check_protocols(a,b)


@pytest.mark.parametrize('fault',[None,'depth','missing_graph','bad_graph'])
def test_matched_exact_execution_allows_distinct_feature_parity_proofs(fault):
    a,b=protocols()
    for p,sha in ((a,'a'),(b,'b')):
        p.update(maxdepth=14,execution_graph={'version':m.execution.graph.VERSION,'parity_manifest_sha256':sha*64})
    if fault=='depth':b['maxdepth']=12
    elif fault=='missing_graph':del b['execution_graph']
    elif fault=='bad_graph':b['execution_graph']['version']='surrogate'
    if fault:
        with pytest.raises(ValueError):m.check_protocols(a,b)
    else:m.check_protocols(a,b)


@pytest.fixture
def fits(tmp_path):
    frame=data();base=m.interaction.floor.FeatureDesign(frame);added=m.interaction.FeatureDesign(frame)
    fits=[]
    for name,design in [('base',base),('added',added)]:
        root=tmp_path/name;target=root/'fit';target.mkdir(parents=True)
        design.save(target)
        files={p.name:p.read_bytes() for p in target.iterdir()}
        fm=publish_binary(target,files,{})
        fits.append({'root':root,'design':design,'data':frame.copy(),
            'provenance':{'fit_manifest':fm},'reconstruction':{'time_arrays':{'same':'verified'}},
            'protocol':{'interaction_mode':'pooled','chains':4,'draws':1000,'prior_multiplier':1.}})
    return fits


@pytest.mark.parametrize('fault',[None,'centering','prior','source','saved_base','time_arrays'])
def test_base_columns_priors_and_serialized_semantics_stay_fixed(fits,fault):
    a,b=fits
    if fault=='centering':b['design'].base.means[0]+=.1
    elif fault=='prior':b['design'].base.prior_scales[0]*=2
    elif fault=='source':b['data'].loc[0,'square_feet']*=2
    elif fault=='time_arrays':b['reconstruction']['time_arrays']['same']='different'
    elif fault=='saved_base':
        target=b['root']/'fit';files={n:(target/n).read_bytes() for n in b['provenance']['fit_manifest']['files']}
        value=json.loads(files['feature-design.json']);value['spec']='other'
        files['feature-design.json']=canonical(value)+'\n'
        b['provenance']['fit_manifest']=publish_binary(target,files,{})
    if fault:
        with pytest.raises(ValueError):m.check_designs(a,b)
    else:m.check_designs(a,b)


@pytest.mark.parametrize('fault',[None,'unmixed_baseline','unmixed_gamma','coordinate','draw_count'])
def test_joint_floor_comparison_keeps_independent_posteriors_and_covariance(fits,fault):
    rng=np.random.default_rng(161)
    for i,fit in enumerate(fits):
        d=fit['design'];beta=rng.normal(0,.08,(4,1000,len(d.features)))
        if i:
            # At elevator=yes, 2->3 cancels the shared random component.
            beta[:,:,d.features.index('listed_floor_gt_2')]=-beta[:,:,-1]/(2*np.sqrt(3))+rng.normal(.03,.001,(4,1000))
        if fault=='unmixed_baseline' and not i:beta[0,:,d.features.index('listed_floor_gt_2')]+=4
        if fault=='unmixed_gamma' and i:beta[0,:,-1]+=4
        coords=d.features[::-1] if fault=='coordinate' and i else d.features
        posterior=xr.Dataset({'beta':(('chain','draw','feature'),beta)},coords={'feature':coords})
        posterior.to_netcdf(fit['root']/'fit/posterior.nc',group='posterior',engine='h5netcdf')
        if i:
            if fault=='coordinate':posterior=posterior.assign_coords(feature=d.features)
            joint,_=experiment.joint_contrasts({'posterior':posterior},d,fit['data'])
            fit['report']={'floor_elevator':joint}
    if fault=='draw_count':fits[1]['protocol']['draws']=50
    if fault:
        with pytest.raises(ValueError):m.contrast_comparison(*fits)
    else:
        result=m.contrast_comparison(*fits)
        changed=next(r for r in result['floor_changes'] if r['id']=='floor:2->3:elevator=1')
        assert changed['candidate']['log_effect']['upper_95']-changed['candidate']['log_effect']['lower_95']<.005
        assert result['interaction_differences'][0]['reference_log_effect']['point_mass']==0
        assert 'diagnostics' not in result['interaction_differences'][0]['reference_log_effect']
        gamma=result['interaction_coefficients'][0]
        assert gamma['posterior_sd_over_prior_sd']==pytest.approx(gamma['posterior_sd']/.15)
        assert 'posterior_change' not in changed


def test_source_slices_distinguish_unknown_access_and_opposing_history():
    rows=[{'audit_id':str(i),'unit_id':str(i),'building':b,'advertised_floor':f,'elevator':e}
          for i,(b,f,e) in enumerate([('a',2,True),('a',3,False),('b',3,None),('c',None,False),('d',8,True)])]
    movements=[{**r,'reference':{'residual_log':.1},'candidate':{'residual_log':.09},'fitted_rent_change':1.} for r in rows]
    result=m.residual_slices(rows,movements)
    assert result['opposing_claim_buildings']==['a']
    slices=result['slices']
    assert slices['known_floor_unknown_access']['rows']==1
    assert slices['known_floor_no_elevator']['rows']==1
    assert slices['known_floor_elevator']['rows']==2
    assert slices['unknown_floor']['rows']==1
    assert slices['lower_2_to_5_elevator']['rows']==1
    assert slices['opposing_claim_buildings']['rows']==2
    assert slices['other_buildings']['rows']==3
