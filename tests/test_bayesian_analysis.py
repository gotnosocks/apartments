"""Analysis uses joint posterior draws, exact saved design and lazy group slices."""
from copy import deepcopy
import json
import math

import numpy as np
import pytest
import xarray as xr

from apartments import bayesian_analysis as m
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import bayesian_feature_report as report
from .test_bayesian_feature_model import train
from .test_bayesian_source_sensitivity import (design_source, complete_synthetic_fit,
                                              converted, reseal)
from .test_bayesian_feature_report import publish_binary


@pytest.fixture
def posterior_fit(tmp_path, train):
    rows = design_source(train)
    source = tmp_path/'source'; root = tmp_path/'experiment'
    publish_bundle(source, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                   {'version': 'reviewed-bathroom-counts-projection-v1'})
    complete_synthetic_fit(root, source, rows, report.EXPERIMENT_VERSION)
    d = m.load_design(root/'fit', converted(rows)); t = d.time
    rng = np.random.default_rng(7102); shape = (4, 1000)
    coords = {'chain': np.arange(4), 'draw': np.arange(1000), 'feature': d.features,
              'trend_basis': np.arange(t.time_matrix.shape[1]),
              'season_basis': np.arange(t.season_matrix.shape[1]),
              'building': t.buildings, 'unit': t.unit_ids}
    data = {}
    for name, dim in [('alpha', None), ('beta', 'feature'), ('trend_coefficients', 'trend_basis'),
                      ('annual_drift', None), ('season_coefficients', 'season_basis'),
                      ('building_effect', 'building'), ('sigma_unit', None), ('sigma', None), ('unit_z', 'unit')]:
        values = rng.normal(0, .025, (*shape, *((len(coords[dim]),) if dim else ())))
        if name == 'alpha': values += math.log(4000)
        if name in ('sigma_unit','sigma'): values = np.exp(values)*.15
        data[name] = (('chain', 'draw', *((dim,) if dim else ())), values)
    # Strong positive posterior covariance must cancel in a full-minus-shortfall contrast.
    j = d.features.index('full_bathrooms_gt_1'); k = d.features.index('full_bathroom_shortfall')
    data['beta'][1][:, :, k] = data['beta'][1][:, :, j] + rng.normal(.01, .0001, shape)
    p = xr.Dataset(data, coords=coords)
    path = tmp_path/'posterior.nc'; p.to_netcdf(path, group='posterior', engine='h5netcdf')
    samples = {name: np.asarray(p[name]).reshape((-1, *p[name].shape[2:])) for name in p}
    from models.bayesian_feature_checks_v2 import reconstruct_mu
    mu = reconstruct_mu(samples, d, converted(rows))
    quantiles = np.exp(np.quantile(mu, [.025, .5, .975], axis=0))
    residuals = []
    for i, row in enumerate(rows):
        residuals.append({k: row[k] for k in ('audit_id', 'source_listing_id', 'unit_id', 'building', 'period', 'asking_rent')} |
            {'latent_rent_lower_95':float(quantiles[0,i]), 'fitted_rent':float(quantiles[1,i]),
             'latent_rent_upper_95':float(quantiles[2,i]), 'residual_dollars':row['asking_rent']-float(quantiles[1,i]),
             'residual_log':math.log(row['asking_rent']/quantiles[1,i])})
    fm = json.loads((root/'fit'/'complete.json').read_text())
    files = {name: (root/'fit'/name).read_bytes() for name in fm['files']}
    files['posterior.nc'] = path.read_bytes()
    files['residuals.jsonl'] = ''.join(canonical(r)+'\n' for r in residuals)
    summary = json.loads(files['summary.json']); summary['median_absolute_log_residual'] = float(np.median([abs(r['residual_log']) for r in residuals]))
    files['summary.json'] = canonical(summary)+'\n'
    publish_binary(root/'fit', files, {k:v for k,v in fm.items() if k != 'files'})
    return root, source, rows, p, mu


@pytest.fixture
def workspace(posterior_fit):
    root, source, *_ = posterior_fit
    result = m.load(root, source)
    yield result
    result.close()


def test_additive_contributions_exact_draw_intervals_and_lazy_unit_access(workspace, posterior_fit, monkeypatch):
    _, _, rows, posterior, mu = posterior_fit
    # A materialization spy rejects all unsliced building/unit draw loads.
    original = workspace._values
    def selected_only(array):
        assert 'unit' not in array.dims and 'building' not in array.dims
        return original(array)
    monkeypatch.setattr(workspace, '_values', selected_only)
    detail = workspace.detail(rows[1]['audit_id'])
    np.testing.assert_allclose(list(detail['fitted_median_rent'].values()), np.exp(np.quantile(mu[:,1],[.025,.5,.975])), rtol=1e-13)
    assert detail['mean_log_rent'] == pytest.approx(mu[:,1].mean(), abs=1e-13)
    assert sum(r['mean_log_contribution'] for r in detail['contributions']) == pytest.approx(detail['mean_log_rent'], abs=1e-13)
    assert sum(detail['grouped_contributions'].values()) == pytest.approx(detail['mean_log_rent'], abs=1e-13)
    assert detail['draws'] == 4000
    assert len(workspace._groups) == 2
    assert not any(name in workspace._draws for name in ('unit_z','building_effect'))
    detail['source_record']['asking_rent']=1
    assert workspace.detail(rows[1]['audit_id'])['source_record']['asking_rent'] != 1


def test_counterfactual_preserves_covariance_and_reencodes_bedroom_area(workspace):
    row = next(r for r in workspace.rows if r['bedrooms']==2 and report.composition(r)==(1,0))
    result = workspace.counterfactual(row['audit_id'], {'full_bathrooms':2})
    assert result['status'] == 'accepted'
    assert result['changed_encoded_features'] == {'full_bathrooms_gt_1':1.,'full_bathroom_shortfall':-1.}
    beta = workspace._draws['beta']; names=workspace.design.features
    expected = beta[:,names.index('full_bathrooms_gt_1')]-beta[:,names.index('full_bathroom_shortfall')]
    assert result['delta_log'] == pytest.approx(m._interval(expected))
    assert result['delta_log']['upper_95']-result['delta_log']['lower_95'] < .001
    assert result['after']['bathrooms'] == 2
    assert report.composition(row)==(1,0)
    row = next(r for r in workspace.rows if r['bedrooms']==2 and report.composition(r)==(1,0) and r['square_feet'])
    bed = workspace.counterfactual(row['audit_id'], {'bedrooms':3})
    assert bed['changed_encoded_features']['bedrooms_gt_2']==1
    assert bed['changed_encoded_features']['full_bathroom_shortfall']==1
    assert 'log_size_within_bedrooms' in bed['changed_encoded_features']
    assert bed['before']['square_feet']==bed['after']['square_feet']
    mu,_,x=workspace._terms(row)
    delta=beta@(workspace.design.matrix(m._frame([bed['after']]))[0]-x)
    assert bed['delta_dollars']==pytest.approx(m._interval(np.exp(mu)*np.expm1(delta)))


@pytest.mark.parametrize('changes', [
    {'bathrooms':2}, {'ensuite':True}, {'square_feet':None}, {'square_feet':0},
    {'bedrooms':True}, {'bedrooms':6}, {'full_bathrooms':1.5}, {'half_bathrooms':-1},
    {'laundry_type':'mystery'}, {'laundry_type':None}, {'doorman_type':'virtual'},
    {'full_bathrooms':1,'reported_full_bathrooms':2}, {'view_exposures.street':True},
])
def test_unknown_unsupported_or_invalid_changes_rejected(workspace, changes):
    with pytest.raises(ValueError): workspace.counterfactual(workspace.rows[1]['audit_id'],changes)


def test_unknown_composition_requires_both_counts_and_warns(workspace):
    row=next(r for r in workspace.rows if report.composition(r) is None)
    with pytest.raises(ValueError,match='both explicit'):
        workspace.counterfactual(row['audit_id'],{'full_bathrooms':2})
    result=workspace.counterfactual(row['audit_id'],{'full_bathrooms':2,'half_bathrooms':0})
    assert result['after']['bathroom_count_evidence']['hypothetical']
    assert any('reporting/missingness' in w for w in result['warnings'])
    assert workspace._rows[row['audit_id']]==row


def test_category_contrast_reencodes_basis_and_unknown_indicator(workspace):
    row=next(r for r in workspace.rows if r.get('laundry_type') is None)
    result=workspace.counterfactual(row['audit_id'],{'laundry_type':'in_unit'})
    assert 'laundry_type.unknown' in result['changed_encoded_features']
    assert any('laundry_type.contrast_' in k for k in result['changed_encoded_features'])
    assert any('reporting/missingness' in w for w in result['warnings'])


def test_new_contrast_bad_diagnostics_withhold_intervals(workspace,monkeypatch):
    monkeypatch.setattr(m,'contrast_diagnostics',lambda *args:{'acceptable':False})
    result=workspace.counterfactual(workspace.rows[1]['audit_id'],{'square_feet':1000})
    assert result['status']=='diagnostic_only'
    assert 'delta_log' not in result and 'after_rent' not in result


def test_stale_and_tampered_bundle_fail(workspace,posterior_fit):
    root,source,*_=posterior_fit
    path=source/'observations.jsonl'; path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Stale'):workspace.detail('a1')
    with pytest.raises(ValueError):m.load(root,source)


def test_rehashed_saved_design_semantic_tamper_fails(posterior_fit):
    root,source,*_=posterior_fit
    value=json.loads((root/'fit'/'feature-design.json').read_text());value['means'][0]+=.1
    reseal(root/'fit','feature-design.json',canonical(value)+'\n')
    with pytest.raises(ValueError,match='exact source reconstruction'):m.load(root,source)


def test_diagnostic_only_fit_rejected(posterior_fit):
    root,source,*_=posterior_fit
    value=json.loads((root/'fit'/'summary.json').read_text());value['status']='diagnostic_only'
    reseal(root/'fit','summary.json',canonical(value)+'\n')
    with pytest.raises(ValueError,match='exploratory_converged'):m.load(root,source)


def test_group_intervals_are_joint_and_mean_log_terms_add(workspace):
    result=workspace.detail('a1')
    assert result['contribution_diagnostics']['acceptable']
    _,terms,_=workspace._terms(workspace._rows['a1'])
    grouped={}
    for row in result['contributions']:
        grouped[row['kind']]=grouped.get(row['kind'],0)+terms[row['term']]
        assert row['log_interval']==pytest.approx(m._interval(terms[row['term']]))
    for row in result['grouped_contribution_intervals']:
        assert row['log_interval']==pytest.approx(m._interval(grouped[row['group']]))


def test_reporting_and_unsupported_endpoints_withhold_physical_intervals(workspace):
    unknown=next(r for r in workspace.rows if r.get('laundry_type') is None)
    result=workspace.counterfactual(unknown['audit_id'],{'laundry_type':'in_unit'})
    assert result['status']=='reporting_change' and 'delta_dollars' not in result
    known=next(r for r in workspace.rows if r['square_feet'])
    result=workspace.counterfactual(known['audit_id'],{'square_feet':100000})
    assert result['status']=='unsupported_endpoint' and 'delta_dollars' not in result
    assert not result['support']['after']['fields']['square_feet']['within_observed_range']


def test_new_derived_contrast_diagnostics_detect_chain_disagreement():
    rng=np.random.default_rng(42)
    bad=rng.normal(size=(4,1000))+np.arange(4)[:,None]
    assert not m.contrast_diagnostics({'delta':bad.ravel()},bad.shape)['acceptable']
    good=rng.normal(size=(4,1000))
    assert m.contrast_diagnostics({'delta':good.ravel()},good.shape)['acceptable']
    assert m.contrast_diagnostics({'delta':np.zeros(4000)},good.shape)['deterministic']


def convert_v3(posterior_fit,mode,centered=False):
    """Bind the same exact mean posterior to a synthetic v3 residual graph."""
    from models import bayesian_feature_graph_v3 as graph
    from models import bayesian_feature_experiment_v3 as runner
    from apartments.research_pipeline import digest
    import hashlib
    from pathlib import Path
    root,source,rows,p,mu=posterior_fit
    pm=json.loads((root/'protocol'/'complete.json').read_text())
    protocol=json.loads((root/'protocol'/'protocol.json').read_text())
    config=graph.graph_configuration(converted(rows),residual_scale=mode,
        residual_parameterization='centered' if centered else 'noncentered')
    protocol.update(version=report.EXPERIMENT_V3,residual_scale=mode,building_prior_scale=.35,
                    unit_prior_scale=.25,graph_configuration=config,
                    residual_parameterization='centered' if centered else 'noncentered')
    pf={name:(root/'protocol'/name).read_bytes() for name in pm['files'] if name!='protocol.json'}
    for module in (graph,runner):
        path=Path(module.__file__);pf[path.name]=path.read_bytes()
        protocol['implementation_sha256'][path.name]=digest(path)
    ph=hashlib.sha256(canonical(protocol).encode()).hexdigest();pf['protocol.json']=canonical(protocol)+'\n'
    publish_binary(root/'protocol',pf,{'version':report.EXPERIMENT_V3,'protocol_sha256':ph})
    fm=json.loads((root/'fit'/'complete.json').read_text()); files={name:(root/'fit'/name).read_bytes() for name in fm['files']}
    summary=json.loads(files['summary.json']);summary['protocol_sha256']=ph
    files['summary.json']=canonical(summary)+'\n'
    p=p.copy(deep=True)
    levels=config['residual_bedroom_levels']
    if mode=='bedroom':
        p=p.assign_coords(residual_bedroom=levels)
        rng=np.random.default_rng(176)
        z=rng.normal(size=(4,1000,len(levels)));z-=z.mean(axis=2,keepdims=True)
        scale=np.full((4,1000),.1)
        p['residual_bedroom_z']=(('chain','draw','residual_bedroom'),z)
        p['residual_bedroom_scale']=(('chain','draw'),scale)
        p['sigma_by_bedroom']=(('chain','draw','residual_bedroom'),p.sigma.values[:,:,None]*np.exp(scale[:,:,None]*z))
        if centered:p['residual_bedroom_offset']=(('chain','draw','residual_bedroom'),scale[:,:,None]*z)
    from .test_bayesian_feature_report import interval
    scales={'version':'bayesian-residual-scale-summary-v1','graph_configuration':config,'student_t_nu':5.,
        'scale_units':'Log advertised asking rent; Student-t scale, not its standard deviation.',
        'global_sigma':{**interval(.2),'probability_positive':1.},
        'global_sigma_role':'Shared observation scale' if mode=='shared' else 'Geometric mean of bedroom-level scales (equal level weights)',
        'by_bedroom':[{'bedrooms':b,'support':report.support([r for r in rows if r['bedrooms']==b]),
                      'sigma':{**interval(.2),'probability_positive':1.}} for b in levels],
        'interpretation':'Separate conditional 95% posterior intervals. Residual variation is not latent conditional-median uncertainty. Student-t standard deviation equals scale * sqrt(5/3); no mean or feature contribution changed by this summary.'}
    path=root/'new-posterior.nc';p.to_netcdf(path,group='posterior',engine='h5netcdf')
    files['posterior.nc']=path.read_bytes();path.unlink()
    files['graph-configuration.json']=canonical(config)+'\n';files['residual-scales.json']=canonical(scales)+'\n'
    publish_binary(root/'fit',files,{'version':report.EXPERIMENT_V3,'protocol_sha256':ph})
    return p


@pytest.mark.parametrize('mode,centered',[('shared',False),('bedroom',False),('bedroom',True)])
def test_v3_shared_and_bedroom_graphs_keep_exact_mean_posterior(posterior_fit,mode,centered):
    root,source,rows,_,mu=posterior_fit
    convert_v3(posterior_fit,mode,centered)
    workspace=m.load(root,source)
    try:
        result=workspace.detail('a1')
        assert result['draws']==4000
        np.testing.assert_allclose(list(result['fitted_median_rent'].values()),np.exp(np.quantile(mu[:,1],[.025,.5,.975])))
    finally:workspace.close()


def test_rehashed_wrong_bedroom_posterior_identity_rejected(posterior_fit):
    root,source,*_=posterior_fit
    p=convert_v3(posterior_fit,'bedroom',True)
    p['sigma_by_bedroom'].values[0,0,0]*=2
    path=root/'bad.nc';p.to_netcdf(path,group='posterior',engine='h5netcdf')
    target=root/'fit'/'posterior.nc';target.write_bytes(path.read_bytes())
    from apartments.research_pipeline import digest
    fm=json.loads((root/'fit'/'complete.json').read_text());fm['files']['posterior.nc']=digest(target)
    (root/'fit'/'complete.json').write_text(canonical(fm)+'\n')
    with pytest.raises(ValueError,match='joint parameterization'):m.load(root,source)


def test_nested_exposure_and_elevator_changes_reencode_all_interactions(tmp_path,train):
    # Exercise actual source nesting rather than flattened exposure names.
    data=train.copy(deep=True)
    data['elevator']=[i%3==0 for i in range(len(data))]
    data['physical_floor']=[float(i%9) for i in range(len(data))]
    data['window_exposures']=[{'north':i%3==1,'east':None,'south':None,'west':None} for i in range(len(data))]
    rows=design_source(data)
    for row in rows:row['listed_floor']=None
    from models.bayesian_feature_model import FeatureDesign
    workspace=m.BayesianAnalysis()
    workspace.design=FeatureDesign(converted(rows));workspace.fields=workspace._fields()
    row=rows[1];before=m._frame([row]);after=deepcopy(row)
    after['elevator']=True;after['window_exposures']['north']=False
    before_x=workspace.design.matrix(before)[0];after_x=workspace.design.matrix(m._frame([after]))[0]
    changed={name for name,v in zip(workspace.design.features,after_x-before_x) if v!=0}
    assert {'elevator','physical_floor_x_elevator','window_exposures.north'}<=changed
    assert workspace._value(row,'elevator') is False
    assert workspace._value(row,'window_exposures.north') is True
    assert row['window_exposures']['north'] is True and after['window_exposures']['east'] is None
    workspace._fresh=lambda:None
    workspace._rows={row['audit_id']:row};workspace._source=rows;workspace._data=converted(rows)
    workspace._field_observations={};workspace._shape=(4,1000)
    workspace._draws={'beta':np.random.default_rng(12).normal(0,.01,(4000,len(workspace.design.features)))}
    workspace._terms=lambda _: (np.full(4000,8.),{},before_x)
    workspace._residuals={row['audit_id']:{'latent_rent_lower_95':float(np.exp(8.)),
        'fitted_rent':float(np.exp(8.)),'latent_rent_upper_95':float(np.exp(8.))}}
    result=workspace.counterfactual(row['audit_id'],{'elevator':True,'window_exposures.north':False})
    assert result['status']=='accepted'
    assert result['after']['window_exposures']['north'] is False
    assert result['after']['window_exposures']['east'] is None
    assert result['before']['window_exposures']['north'] is True
    assert {'elevator','physical_floor_x_elevator','window_exposures.north'}<=result['changed_encoded_features'].keys()


def test_selected_residual_reconstruction_rejects_rehashed_posterior_mismatch(posterior_fit):
    root,source,rows,p,_=posterior_fit
    p=p.copy(deep=True);p['alpha']+=.2
    path=root/'changed.nc';p.to_netcdf(path,group='posterior',engine='h5netcdf')
    target=root/'fit'/'posterior.nc';target.write_bytes(path.read_bytes())
    from apartments.research_pipeline import digest
    fm=json.loads((root/'fit'/'complete.json').read_text());fm['files']['posterior.nc']=digest(target)
    (root/'fit'/'complete.json').write_text(canonical(fm)+'\n')
    workspace=m.load(root,source)
    try:
        with pytest.raises(ValueError,match='saved residual'):workspace.detail('a1')
        with pytest.raises(ValueError,match='saved residual'):workspace.counterfactual('a1',{'square_feet':1000})
    finally:workspace.close()


@pytest.mark.skipif(__import__('os').environ.get('APARTMENTS_VERIFY_REAL_BAYESIAN')!='1',
                    reason='Opt-in full archived posterior verification; no fitting')
def test_all_thirteen_current_baseline_quantiles_use_every_retained_draw():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    workspace=m.load(root/'data/model/chelsea-bayesian-bathrooms-long-20260918',
                     root/'data/model/chelsea-reviewed-bathroom-projection-20260918')
    try:
        current=workspace.summary['current_residuals']
        assert len(current)==13 and workspace._shape==(4,4000)
        for row in current:
            detail=workspace.detail(row['audit_id'])
            assert detail['draws']==16000
            expected=[row[k] for k in ('latent_rent_lower_95','fitted_rent','latent_rent_upper_95')]
            np.testing.assert_allclose(list(detail['fitted_median_rent'].values()),expected,rtol=1e-12,atol=1e-8)
            assert detail['mean_log_rent']==pytest.approx(sum(x['mean_log_contribution'] for x in detail['contributions']),abs=1e-12)
        assert not {'unit_z','building_effect'} & workspace._draws.keys()
        assert len(workspace._groups)<=32
    finally:workspace.close()


def test_reconstruction_restores_training_blas_arithmetic_without_relaxing_hashes(posterior_fit,monkeypatch):
    from threadpoolctl import threadpool_info,threadpool_limits
    original=m.verify_design
    observed=[]
    def verify(*args):
        pools=[p for p in threadpool_info() if p['user_api']=='blas']
        assert pools and all(p['num_threads']==1 for p in pools)
        observed.append(True)
        return original(*args)
    monkeypatch.setattr(m,'verify_design',verify)
    root,source,*_=posterior_fit
    with threadpool_limits(limits=2,user_api='blas'):
        workspace=m.load(root,source)
        try:assert all(p['num_threads']==2 for p in threadpool_info() if p['user_api']=='blas')
        finally:workspace.close()
    assert observed==[True]
