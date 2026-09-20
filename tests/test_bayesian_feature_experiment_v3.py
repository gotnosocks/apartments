"""Frozen v3 configuration and checkpoint contracts, with no posterior sampling."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import bayesian_feature_experiment_v3 as m


class FakeInference(dict):
    def to_netcdf(self,path,**kwargs):
        Path(path).write_bytes(b'synthetic posterior; no sampling performed')


def posterior(args,design,configuration):
    scalar = np.ones((args.chains,args.draws))*.2
    variables = {name:(('chain','draw'),scalar.copy()) for name in
                 ('alpha','annual_drift','sigma_building','sigma_unit','sigma','trend_scale','season_scale')}
    coords = {'chain':range(args.chains),'draw':range(args.draws),'feature':design.features,
              'building':design.time.buildings,'unit':design.time.unit_ids,
              'trend_basis':range(design.time.time_matrix.shape[1]),'season_basis':range(11)}
    for name,dim in [('beta','feature'),('building_effect','building'),('unit_z','unit'),
                     ('trend_coefficients','trend_basis'),('season_coefficients','season_basis')]:
        variables[name] = (('chain','draw',dim),np.repeat(scalar[:,:,None],len(coords[dim]),axis=2))
    if args.residual_scale == 'bedroom':
        coords['residual_bedroom'] = configuration['residual_bedroom_levels']
        values = np.broadcast_to(np.arange(1,len(coords['residual_bedroom'])+1)*.1,
                                 (*scalar.shape,len(coords['residual_bedroom']))).copy()
        variables['sigma_by_bedroom'] = (('chain','draw','residual_bedroom'),values)
        variables['residual_bedroom_z'] = (('chain','draw','residual_bedroom'),np.zeros_like(values))
        variables['residual_bedroom_scale'] = (('chain','draw'),scalar.copy())
        if configuration.get('residual_bedroom_parameterization') == 'centered':
            variables['residual_bedroom_offset'] = (('chain','draw','residual_bedroom'),np.zeros_like(values))
    return FakeInference(posterior=xr.Dataset(variables,coords=coords))


@pytest.fixture
def setup(tmp_path,monkeypatch):
    args = m.argument_parser().parse_args(['--dataset',str(tmp_path/'source'),'--output',str(tmp_path/'run'),
                                        '--draws','3','--tune','4','--chains','2','--seed','4'])
    rows = [{'audit_id':'a'+str(i),'source_listing_id':str(100+i),'unit_id':'u'+str(i),'building':'b'+str(i//2),
             'period':'2026-09-01','bedrooms':beds,'asking_rent':3000.+i*500,'square_feet':None,
             'analysis_price_basis':'current_capture_gross_ask' if i==0 else 'historical_initial_own_advertisement_ask',
             'bathrooms':1.,'reported_full_bathrooms':1,'reported_half_bathrooms':0,
             'bathroom_count_evidence':{'flags':[]}}
            for i,beds in enumerate([0,1,1,2])]
    publish_bundle(args.dataset,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},
                   {'version':'reviewed-bathroom-counts-projection-v1'})
    design = SimpleNamespace(features=['feature'],support={'rows':4},
                             time=SimpleNamespace(buildings=['b0','b1'],unit_ids=['u0','u1','u2','u3'],
                                                  time_matrix=np.zeros((1,2))))
    def save(target):
        for name in ('feature-design.json','time-design.json','time-design.npz'):
            (target/name).write_text('synthetic design\n')
    design.save = save
    monkeypatch.setattr(m.v2.feature,'FeatureDesign',lambda *a:design)
    events = {'build':0,'prior':0,'sample':0,'reports':0}
    class Model:
        def __enter__(self): return self
        def __exit__(self,*a): return False
    def build(data,observed_design,multiplier,**kwargs):
        events['build'] += 1
        model = Model()
        model.graph_configuration = m.graph.graph_configuration(data,multiplier,**kwargs)
        model.compression_summary = {'observations':len(data),'features':len(observed_design.features)}
        events['configuration'] = model.graph_configuration
        return model
    def prior(**kwargs):
        events['prior'] += 1; events['prior_arguments'] = kwargs
        return FakeInference()
    def sample(model,**kwargs):
        events['sample'] += 1; events['sample_arguments'] = kwargs
        inference = posterior(args,design,model.graph_configuration)
        events['inference'] = inference
        return inference
    def reports(target,inference,observed_design,data,protocol_hash):
        events['reports'] += 1
        result = {'protocol_sha256':protocol_hash,'status':'diagnostic_only_do_not_interpret_intervals'}
        for name in ('summary.json','diagnostics.json','derived-diagnostics.json',
                     'parameter-diagnostics.csv','derived-diagnostics.csv','bathroom-contrasts.json',
                     'residuals.jsonl','coefficients.json','group-effects.jsonl'):
            (target/name).write_text(canonical(result if name=='summary.json' else {})+'\n')
        return result
    monkeypatch.setattr(m.graph,'build_model',build)
    monkeypatch.setattr(m.v2.pm,'sample_prior_predictive',prior)
    monkeypatch.setattr(m.v2.sampler,'sample',sample)
    monkeypatch.setattr(m.v2,'write_reports',reports)
    monkeypatch.setattr(m.v2.az,'from_netcdf',lambda path:events['inference'])
    return args,design,events


@pytest.mark.parametrize('mode',['shared','bedroom'])
def test_explicit_graph_protocol_archival_residual_scales_and_no_resample(setup,mode):
    args,design,events = setup
    args.residual_scale = mode; args.building_prior_scale = .7; args.unit_prior_scale = .125
    result = m.run(args)
    protocol = json.loads((args.output/'protocol'/'protocol.json').read_text())
    assert protocol['version'] == m.VERSION
    assert protocol['graph_configuration'] == events['configuration']
    assert protocol['building_prior_scale'] == .7 and protocol['unit_prior_scale'] == .125
    assert protocol['source_observations_sha256'] == digest(args.dataset/'observations.jsonl')
    assert {'bayesian_feature_experiment_v3.py','bayesian_feature_experiment_v2.py',
            'bayesian_feature_experiment.py','bayesian_feature_graph_v3.py','bayesian_feature_graph.py',
            'bayesian_feature_model.py','bayesian_rent_model.py','bayesian_sampling.py','amenity_rent_model.py',
            'minimal_rent_model.py','pricing.py','corrections.py','research_pipeline.py',
            'reviewed_source_lineage.py','laundry_floor_split.py','reviewed_cohort_quarantine.py','elevator_corrections.py','floor_label_projection.py','expanded_floor_projection.py','residual_scope_projection.py'} == set(protocol['implementation_sha256'])
    for name,sha in protocol['implementation_sha256'].items():
        assert digest(args.output/'protocol'/name) == sha
    summary = json.loads((args.output/'fit'/'residual-scales.json').read_text())
    assert summary['student_t_nu'] == 5
    assert 'not its standard deviation' in summary['scale_units']
    assert summary['global_sigma']['median'] == .2
    if mode == 'bedroom':
        assert protocol['graph_configuration']['residual_bedroom_levels'] == [0,1,2]
        assert protocol['graph_configuration']['residual_bedroom_counts'] == [1,2,1]
        assert [r['sigma']['median'] for r in summary['by_bedroom']] == pytest.approx([.1,.2,.3])
        assert summary['by_bedroom'][1]['support'] == {'rows':2,'units':2,'buildings':2}
        assert 'sigma_by_bedroom' in events['prior_arguments']['var_names']
        assert 'residual_bedroom_offset' in events['prior_arguments']['var_names']
        assert protocol['residual_parameterization']=='centered'
    else:
        assert summary['by_bedroom'] == []
        assert 'sigma_by_bedroom' not in events['prior_arguments']['var_names']
    assert result['status'] == 'diagnostic_only_do_not_interpret_intervals'
    assert m.run(args) == result
    assert events['build'] == events['prior'] == events['sample'] == events['reports'] == 1
    manifest = json.loads((args.output/'fit'/'complete.json').read_text())
    assert m.REQUIRED_FIT <= manifest['files'].keys()


@pytest.mark.parametrize('name,value',[
    ('draws',0),('tune',-1),('chains',1),('chains',True),('seed',-1),
    ('prior_multiplier',0),('prior_multiplier',float('nan')),
    ('building_prior_scale',float('inf')),('unit_prior_scale',-.1),('unit_prior_scale',True),
    ('target_accept',0),('target_accept',1),('target_accept',float('nan')),
    ('residual_scale','unknown'),('residual_parameterization','unknown'),('adaptation','unknown'),('spec','unknown')])
def test_invalid_settings_fail_before_creating_protocol(setup,name,value):
    args,_,events = setup
    setattr(args,name,value)
    with pytest.raises(ValueError): m.run(args)
    assert not args.output.exists()
    assert events['sample'] == 0


@pytest.mark.parametrize('name,value',[('building_prior_scale',.7),('unit_prior_scale',.5),
                                    ('residual_scale','bedroom'),('draws',4),('seed',7)])
def test_finished_or_partial_directory_cannot_change_identity(setup,name,value):
    args,_,events = setup
    m.run(args)
    setattr(args,name,value)
    with pytest.raises(ValueError,match='Run identity changed'): m.run(args)
    assert events['sample'] == 1


def test_valid_checkpoint_resumes_reporting_without_sampling(setup,monkeypatch):
    args,_,events = setup
    original = m.v2.write_reports
    def interrupted(*a): raise RuntimeError('interrupted before reports')
    monkeypatch.setattr(m.v2,'write_reports',interrupted)
    with pytest.raises(RuntimeError,match='interrupted'): m.run(args)
    assert (args.output/'fit'/'posterior-checkpoint.json').exists()
    assert not (args.output/'fit'/'complete.json').exists()
    monkeypatch.setattr(m.v2,'write_reports',original)
    m.run(args)
    assert events['build'] == events['sample'] == events['prior'] == 1


@pytest.mark.parametrize('mutation',['bytes','protocol','draws','bedroom_coordinate'])
def test_bad_checkpoint_rejected_without_resampling(setup,monkeypatch,mutation):
    args,_,events = setup
    args.residual_scale = 'bedroom'
    original = m.v2.write_reports
    monkeypatch.setattr(m.v2,'write_reports',lambda *a: (_ for _ in ()).throw(RuntimeError('stop')))
    with pytest.raises(RuntimeError): m.run(args)
    fit = args.output/'fit'
    if mutation == 'bytes':
        (fit/'posterior.nc').write_bytes(b'changed')
    elif mutation == 'protocol':
        value = json.loads((fit/'posterior-checkpoint.json').read_text()); value['protocol_sha256'] = 'wrong'
        (fit/'posterior-checkpoint.json').write_text(canonical(value)+'\n')
    elif mutation == 'draws':
        events['inference']['posterior'] = events['inference']['posterior'].isel(draw=slice(0,2))
    else:
        events['inference']['posterior'] = events['inference']['posterior'].assign_coords(residual_bedroom=[0,1,3])
    monkeypatch.setattr(m.v2,'write_reports',original)
    with pytest.raises(ValueError,match='checkpoint|coordinate'): m.run(args)
    assert not (fit/'complete.json').exists() and events['sample'] == 1


def test_sampler_incomplete_return_never_becomes_checkpoint(setup,monkeypatch):
    args,design,events = setup
    def sample(model,**kwargs):
        inference = posterior(args,design,model.graph_configuration)
        inference['posterior'] = inference['posterior'].isel(draw=slice(0,2))
        return inference
    monkeypatch.setattr(m.v2.sampler,'sample',sample)
    with pytest.raises(ValueError,match='Incomplete posterior'): m.run(args)
    assert not (args.output/'fit'/'posterior-checkpoint.json').exists()
    assert not (args.output/'fit'/'complete.json').exists()


def test_actual_graph_configuration_cannot_differ(setup,monkeypatch):
    args,_,events = setup
    original = m.graph.build_model
    def wrong(*a,**k):
        model = original(*a,**k); model.graph_configuration['unit_prior_scale'] = 999
        return model
    monkeypatch.setattr(m.graph,'build_model',wrong)
    with pytest.raises(ValueError,match='Built graph settings'): m.run(args)
    assert events['prior'] == events['sample'] == 0


def test_completed_version_required_products_and_hash_integrity(setup):
    args,_,_ = setup
    m.run(args)
    path = args.output/'fit'/'complete.json'
    original = json.loads(path.read_text())
    manifest = {**original,'version':m.v2.VERSION}
    path.write_text(canonical(manifest)+'\n')
    with pytest.raises(ValueError,match='protocol/version'): m.run(args)
    manifest = json.loads(canonical(original)); del manifest['files']['residual-scales.json']
    path.write_text(canonical(manifest)+'\n')
    with pytest.raises(ValueError,match='required products'): m.run(args)
    path.write_text(canonical(original)+'\n')
    (args.output/'fit'/'posterior.nc').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='integrity'): m.run(args)


def test_optional_graph_evidence_requires_v3_hash(setup,tmp_path):
    args,_,_ = setup
    code = {p.name:digest(p) for p in m.implementation_paths()}
    bad = tmp_path/'bad-parity'
    value = {'passed':True,'hashes':{'bayesian_feature_graph.py':code['bayesian_feature_graph.py']},
             'rows':4,'source_observations_sha256':'source'}
    publish_bundle(bad,{'parity.json':canonical(value)+'\n'},{'version':'synthetic-parity'})
    with pytest.raises(ValueError,match='v3 implementation'): m.graph_verification(bad,code)
    good = tmp_path/'good-parity'
    value['hashes']['bayesian_feature_graph_v3.py'] = code['bayesian_feature_graph_v3.py']
    publish_bundle(good,{'parity.json':canonical(value)+'\n'},{'version':'synthetic-parity'})
    result = m.graph_verification(good,code)
    assert result['manifest_sha256'] == digest(good/'complete.json')


def test_checkpoint_graph_variables_and_coordinates_required(setup):
    args,design,_ = setup
    data,_ = m.v2.load_data(args.dataset)
    config = m.graph.graph_configuration(data)
    inference = posterior(args,design,config)
    inference['posterior'] = inference['posterior'].drop_vars('sigma')
    with pytest.raises(ValueError,match='missing required'): m.validate_posterior(inference,args,design,config)
    inference = posterior(args,design,config)
    inference['posterior'] = inference['posterior'].assign_coords(feature=['changed'])
    with pytest.raises(ValueError,match='coordinate mismatch'): m.validate_posterior(inference,args,design,config)
    inference = posterior(args,design,config)
    inference['posterior']['sigma'] = inference['posterior']['unit_z']
    with pytest.raises(ValueError,match='dimensions differ'): m.validate_posterior(inference,args,design,config)


@pytest.mark.parametrize('mode',['shared','bedroom'])
@pytest.mark.parametrize('basis',['trend_basis','season_basis'])
@pytest.mark.parametrize('mutation',['reordered','invalid_labels','missing_coordinate','truncated'])
def test_checkpoint_calendar_basis_identity_required(setup,mode,basis,mutation):
    args,design,_ = setup
    args.residual_scale = mode
    data,_ = m.load_data(args.dataset)
    config = m.graph.graph_configuration(data,residual_scale=mode)
    inference = posterior(args,design,config)
    m.validate_posterior(inference,args,design,config)
    saved = inference['posterior']
    if mutation == 'reordered':
        saved = saved.isel({basis:slice(None,None,-1)})
    elif mutation == 'invalid_labels':
        saved = saved.assign_coords({basis:saved.coords[basis].values+99})
    elif mutation == 'missing_coordinate':
        saved = saved.drop_vars(basis)
    else:
        saved = saved.isel({basis:slice(None,-1)})
    inference['posterior'] = saved
    with pytest.raises(ValueError,match='Posterior coordinate mismatch: '+basis):
        m.validate_posterior(inference,args,design,config)


@pytest.mark.parametrize('version',sorted(m.DATASET_VERSIONS))
def test_loader_preserves_review_overlay_without_mutating_v2(setup,tmp_path,version):
    args,_,_ = setup
    rows = [json.loads(line) for line in (args.dataset/'observations.jsonl').read_text().splitlines()]
    rows[0]['bathroom_count_evidence']['flags'] = ['reviewed_external_shared_bathroom_or_toilet_access']
    rows[0]['scope_composition_review_history'] = [{'decision':'source-bound review','capture_id':'captured'}]
    source = tmp_path/'reviewed'
    manifest = {'version': version}
    sidecar_files = {}
    if version in m.reviewed_source_lineage.VERSIONS:
        from tests.test_reviewed_source_lineage import revise, observations_hash
        for row in rows:
            row.update(known_at='2026-09-18T00:00:00Z', laundry_type='in_building', advertised_floor=3, capture_ids=[row['audit_id']], elevator=True)
        if version == m.reviewed_source_lineage.residual_scope_projection.VERSION:
            from tests.test_residual_scope_projection import add_scope_row
            rows = add_scope_row(rows)
        if version in (m.reviewed_source_lineage.reviewed_cohort_quarantine.VERSION, m.reviewed_source_lineage.elevator_corrections.VERSION, m.reviewed_source_lineage.floor_label_projection.VERSION, m.reviewed_source_lineage.expanded_floor_projection.VERSION, m.reviewed_source_lineage.residual_scope_projection.VERSION):
            from tests.test_reviewed_cohort_quarantine import add_excluded_row, quarantine_last
            rows = add_excluded_row(rows)
        parent = {'version': m.reviewed_source_lineage.REFRESHED,
                  'files': {'observations.jsonl': observations_hash(rows)}}
        manifest, rows = revise(parent, rows, m.reviewed_source_lineage.LAUNDRY, 'laundry_type', 'laundry')
        if version in (m.reviewed_source_lineage.FLOOR, m.reviewed_source_lineage.laundry_floor_split.VERSION,
                       m.reviewed_source_lineage.reviewed_cohort_quarantine.VERSION, m.reviewed_source_lineage.elevator_corrections.VERSION, m.reviewed_source_lineage.floor_label_projection.VERSION, m.reviewed_source_lineage.expanded_floor_projection.VERSION, m.reviewed_source_lineage.residual_scope_projection.VERSION):
            manifest, rows = revise(manifest, rows, m.reviewed_source_lineage.FLOOR, 'advertised_floor', 'floor', index=1)
        if version == m.reviewed_source_lineage.laundry_floor_split.VERSION:
            from tests.test_laundry_floor_projection import extend
            manifest, rows = extend(manifest, rows)
        if version in (m.reviewed_source_lineage.reviewed_cohort_quarantine.VERSION, m.reviewed_source_lineage.elevator_corrections.VERSION, m.reviewed_source_lineage.floor_label_projection.VERSION, m.reviewed_source_lineage.expanded_floor_projection.VERSION, m.reviewed_source_lineage.residual_scope_projection.VERSION):
            manifest, rows, sidecar = quarantine_last(manifest, rows)
            sidecar_files['quarantined.jsonl'] = ''.join(canonical(r)+'\n' for r in sidecar)
        if version in (m.reviewed_source_lineage.elevator_corrections.VERSION, m.reviewed_source_lineage.floor_label_projection.VERSION, m.reviewed_source_lineage.expanded_floor_projection.VERSION, m.reviewed_source_lineage.residual_scope_projection.VERSION):
            from tests.test_elevator_correction_projection import extend
            manifest, rows, elevator_sidecar = extend(manifest, rows)
            sidecar_files['elevator-corrections.jsonl'] = ''.join(canonical(r)+'\n' for r in elevator_sidecar)
        if version in (m.reviewed_source_lineage.floor_label_projection.VERSION, m.reviewed_source_lineage.expanded_floor_projection.VERSION, m.reviewed_source_lineage.residual_scope_projection.VERSION):
            from tests.test_floor_label_projection import extend
            manifest, rows, label_sidecar = extend(manifest, rows)
            sidecar_files['floor-label-projection.jsonl'] = ''.join(canonical(r)+'\n' for r in label_sidecar)
        if version in (m.reviewed_source_lineage.expanded_floor_projection.VERSION, m.reviewed_source_lineage.residual_scope_projection.VERSION):
            from tests.test_expanded_floor_projection import extend
            manifest, rows, expanded_sidecar = extend(manifest, rows, label_sidecar)
            sidecar_files['expanded-floor-projection.jsonl'] = ''.join(canonical(r)+'\n' for r in expanded_sidecar)
        if version == m.reviewed_source_lineage.residual_scope_projection.VERSION:
            from tests.test_residual_scope_projection import extend
            manifest, rows, scope_sidecar = extend(manifest, rows, expanded_sidecar)
            sidecar_files['residual-scope-quarantine.jsonl'] = ''.join(canonical(r)+'\n' for r in scope_sidecar)
    publish_bundle(source,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows), **sidecar_files},manifest)
    data,manifest = m.load_data(source)
    assert manifest['version'] == version and len(data) == 4
    assert data.iloc[0].reported_full_bathrooms == 1
    assert data.iloc[0].bathroom_count_evidence == rows[0]['bathroom_count_evidence']
    assert data.iloc[0].scope_composition_review_history == rows[0]['scope_composition_review_history']
    assert 'reviewed-scope-composition-projection-v2' not in m.v2.DATASET_VERSIONS
    args.dataset = source
    m.run(args)
    protocol = json.loads((args.output/'protocol'/'protocol.json').read_text())
    assert protocol['source_version'] == version
    if version in m.reviewed_source_lineage.VERSIONS:
        assert 'reviewed_source_lineage.py' in protocol['implementation_sha256']
        assert m.v2.pd.isna(data.iloc[0].laundry_type)


@pytest.mark.parametrize('version', sorted(m.reviewed_source_lineage.VERSIONS))
def test_reviewed_revision_name_without_exact_parent_lineage_is_rejected(setup, tmp_path, version):
    args, _, _ = setup
    source = tmp_path/'unsupported_revision'
    publish_bundle(source, {'observations.jsonl': (args.dataset/'observations.jsonl').read_text()}, {'version': version})
    with pytest.raises(ValueError, match='lineage|Elevator|Floor projection|Expanded floor|Residual scope'):
        m.load_data(source)


@pytest.mark.parametrize('mutation',['duplicate_audit','duplicate_unit_period','zero_rent','bad_version'])
def test_loader_retains_exact_cohort_validation(setup,tmp_path,mutation):
    args,_,_ = setup
    rows = [json.loads(line) for line in (args.dataset/'observations.jsonl').read_text().splitlines()]
    if mutation == 'duplicate_audit': rows[1]['audit_id'] = rows[0]['audit_id']
    if mutation == 'duplicate_unit_period': rows[1]['unit_id'] = rows[0]['unit_id']
    if mutation == 'zero_rent': rows[0]['asking_rent'] = 0
    source = tmp_path/'invalid'
    publish_bundle(source,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},
                   {'version':'unknown' if mutation=='bad_version' else 'reviewed-scope-composition-projection-v2'})
    with pytest.raises(ValueError): m.load_data(source)


def test_unreviewed_current_refresh_does_not_gain_implicit_acceptance(setup,tmp_path):
    args,_,_=setup
    source=tmp_path/'unreviewed'
    publish_bundle(source,{'observations.jsonl':(args.dataset/'observations.jsonl').read_text()},
                   {'version':'capture-refreshed-reviewed-analysis-v1'})
    with pytest.raises(ValueError):m.load_data(source)
