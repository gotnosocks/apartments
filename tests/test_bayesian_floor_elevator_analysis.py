"""Real source/design/posterior reader integration; synthetic draws, no fit claims."""
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments import bayesian_analysis as backend
from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models import bayesian_feature_report as report
from models import bayesian_floor_elevator_experiment as experiment
from models import bayesian_source_sensitivity as verification
from tests.test_bayesian_floor_elevator_design import data
from tests.test_bayesian_source_sensitivity import design_source, converted, complete_synthetic_fit
from tests.test_bayesian_feature_report import publish_binary, interval


@pytest.fixture(params=['pooled', 'separate'])
def archive(tmp_path, request):
    rows = design_source(data())
    for row in rows: row['listed_floor'] = None
    # Floor 8 exists, but only with an elevator: marginal support is insufficient.
    for row in rows:
        if row.get('advertised_floor') == 8: row['elevator'] = True
    frame = converted(rows)
    root, source = tmp_path/'experiment', tmp_path/'source'
    publish_bundle(source, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                   {'version': 'reviewed-bathroom-counts-projection-v1'})
    with threadpool_limits(limits=1, user_api='blas'):
        complete_synthetic_fit(root, source, rows, report.EXPERIMENT_V3)
        design = experiment.feature.FeatureDesign(frame, mode=request.param)
        design.save(root/'fit')
    protocol = json.loads((root/'protocol/protocol.json').read_text())
    protocol.update(version=experiment.VERSION, feature_design_version=experiment.feature.VERSION,
        base_feature_design_version=experiment.feature.floor.VERSION, interaction_mode=request.param,
        interaction_prior_scale=.15, interaction_thresholds=list(experiment.feature.THRESHOLDS),
        interaction_policy=experiment.POLICY, floor_increment_prior_scale=.15,
        floor_levels=design.floor_levels, floor_thresholds=design.floor_thresholds)
    code = {p.name:p.read_bytes() for p in experiment.implementation_paths()}
    protocol['implementation_sha256'] = {k:hashlib.sha256(v).hexdigest() for k,v in code.items()}
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    pm = publish_binary(root/'protocol', {'protocol.json':canonical(protocol)+'\n', **code},
        {'version':experiment.VERSION, 'protocol_sha256':ph})
    time = design.time; shape = (4,1000); rng = np.random.default_rng(718)
    coords = {'chain':np.arange(4), 'draw':np.arange(1000), 'feature':design.features,
              'trend_basis':np.arange(time.time_matrix.shape[1]),
              'season_basis':np.arange(time.season_matrix.shape[1]),
              'building':time.buildings, 'unit':time.unit_ids}
    variables = {}
    for name,dim in [('alpha',None),('beta','feature'),('annual_drift',None),
                     ('trend_coefficients','trend_basis'),('season_coefficients','season_basis'),
                     ('building_effect','building'),('unit_z','unit'),('sigma_unit',None),('sigma',None)]:
        values = rng.normal(0,.02,(*shape,*((len(coords[dim]),) if dim else ())))
        if name == 'alpha': values += math.log(4000)
        if name in ('sigma_unit','sigma'): values = np.exp(values)*.15
        variables[name] = (('chain','draw',*((dim,) if dim else ())),values)
    posterior = xr.Dataset(variables,coords=coords)
    # Correlated main and interaction effects must be used jointly.
    beta = posterior.beta.values
    beta[:,:,design.features.index('listed_floor_gt_2')] = -beta[:,:,design.features.index(experiment.feature.names(request.param)[0])]/(2*math.sqrt(3) if request.param == 'pooled' else 2)+rng.normal(.03,.001,shape)
    posterior.to_netcdf(tmp_path/'posterior.nc',group='posterior',engine='h5netcdf')
    joint, table = experiment.joint_contrasts({'posterior':posterior},design,frame)
    assert joint['all_contrasts_acceptable']
    from models.bayesian_feature_checks_v2 import reconstruct_mu
    samples = {n:np.asarray(posterior[n]).reshape((-1,*posterior[n].shape[2:])) for n in posterior}
    mu = reconstruct_mu(samples,design,frame)
    q = np.exp(np.quantile(mu,[.025,.5,.975],axis=0)); residuals = []
    for i,r in enumerate(rows):
        residuals.append({k:r[k] for k in ('audit_id','source_listing_id','unit_id','building','period','asking_rent')} |
            {'latent_rent_lower_95':float(q[0,i]),'fitted_rent':float(q[1,i]),'latent_rent_upper_95':float(q[2,i]),
             'residual_dollars':float(r['asking_rent']-q[1,i]),'residual_log':float(math.log(r['asking_rent']/q[1,i]))})
    fm = json.loads((root/'fit/complete.json').read_text())
    files = {n:(root/'fit'/n).read_bytes() for n in fm['files']}
    files.update({n:(root/'fit'/n).read_bytes() for n in (*verification.comparison.DESIGNS,'interaction-design.json')})
    summary = json.loads(files['summary.json'])
    summary.update(protocol_sha256=ph,design_support=design.support,floor_elevator_contrasts_acceptable=True,
        median_absolute_log_residual=float(np.median([abs(r['residual_log']) for r in residuals])))
    files.update({'summary.json':canonical(summary)+'\n','floor-elevator-contrasts.json':canonical(joint)+'\n',
        'floor-elevator-diagnostics.csv':table.to_csv(),'posterior.nc':(tmp_path/'posterior.nc').read_bytes(),
        'coefficients.json':canonical([{'feature':n,**interval(.01)} for n in design.features])+'\n',
        'residuals.jsonl':''.join(canonical(r)+'\n' for r in residuals)})
    fm = publish_binary(root/'fit',files,{'version':experiment.VERSION,'protocol_sha256':ph})
    return root,source,protocol,{'protocol_manifest':pm,'fit_manifest':fm},design,rows,posterior


def test_report_reconstruction_and_full_joint_counterfactual(archive):
    root,source,p,manifests,design,rows,posterior = archive
    result,_ = report.build_report(root,source)
    assert result['floor_elevator']['all_joint_beta_draws']
    assert 'floors' not in result
    html = report.html_report(result)
    assert 'Listed floor by elevator access' in html
    assert 'Unobserved floor/access endpoint' in html
    with closing(backend.load(root,source)) as analysis:
        assert analysis.fields['listed_floor']['observed_levels'] == design.floor_levels
        item = analysis.detail(rows[0]['audit_id'])
        assert any(r['kind']=='floor_elevator' for r in item['contributions'])
        assert sum(r['mean_log_contribution'] for r in item['contributions']) == pytest.approx(item['mean_log_rent'])
        scenario = analysis.counterfactual(rows[0]['audit_id'],{'listed_floor':3})
        assert scenario['status'] == 'accepted'
        vector = experiment.feature.floor_contrast_vector(design,converted(rows),2,3,True)
        delta = posterior.beta.values.reshape(-1,len(design.features)) @ vector
        np.testing.assert_allclose(list(scenario['delta_log'].values()), np.quantile(delta,[.025,.5,.975]))
        assert scenario['delta_log']['upper_95']-scenario['delta_log']['lower_95'] < .05
        # Marginal floor 8 and no-elevator support exist; their joint cell does not.
        absent = analysis.counterfactual(rows[0]['audit_id'],{'listed_floor':8,'elevator':False})
        assert absent['status'] == 'unsupported_endpoint' and 'delta_log' not in absent
        assert absent['support']['after']['floor_elevator']['rows'] == 0


def test_loader_refuses_base_only_or_mismatched_protocol(archive):
    root,_,p,_,design,rows,_ = archive
    for protocol in (None, {**p,'version':report.EXPERIMENT_V4}, {**p,'interaction_prior_scale':.2}):
        with pytest.raises(ValueError): backend.load_design(root/'fit',converted(rows),protocol)
    restored = backend.load_design(root/'fit',converted(rows),p)
    np.testing.assert_array_equal(restored.matrix(converted(rows)),design.matrix(converted(rows)))


def test_rehashed_interaction_center_rejected_by_source_reconstruction(archive):
    root,source,p,manifests,_,_,_ = archive
    extra = json.loads((root/'fit/interaction-design.json').read_text())
    extra['interaction_means'][0] += .01
    files = {n:(root/'fit'/n).read_bytes() for n in manifests['fit_manifest']['files']}
    files['interaction-design.json'] = canonical(extra)+'\n'
    manifests['fit_manifest'] = publish_binary(root/'fit',files,
        {'version':experiment.VERSION,'protocol_sha256':manifests['fit_manifest']['protocol_sha256']})
    with threadpool_limits(limits=1,user_api='blas'), pytest.raises(ValueError,match='exact source reconstruction'):
        verification.verify_design(root,source,p,manifests)
    with pytest.raises(ValueError,match='centering'): report.build_report(root,source)


def test_category_and_predictive_readers_use_extended_design(archive, tmp_path):
    from models import bayesian_category_contrasts as categories
    from models import bayesian_feature_checks_v3 as checks
    root,source,_,_,design,_,_ = archive
    category = categories.run(root,source,tmp_path/'category-report')
    assert category['design_reconstruction']['verified']
    assert category['design_features'] == design.features
    result = checks.run(root,source,tmp_path/'predictive-checks',per_chain=10)
    assert result['experiment_version'] == experiment.VERSION
    assert len(result['selected_draws']) == 40
