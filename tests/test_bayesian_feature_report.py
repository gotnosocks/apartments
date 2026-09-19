"""Frozen posterior reporting requires convergence, source binding and semantics."""
import copy
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_report as m


def interval(median=.1):
    return {'median': median, 'lower_95': median-.05, 'upper_95': median+.05, 'probability_positive': .98 if median > 0 else .02}


def diagnostics():
    return {'acceptable': True, 'max_rhat': 1.002, 'min_ess_bulk': 800., 'min_ess_tail': 600.,
            'min_bfmi': .8, 'divergences': 0, 'maxdepth_reached': 0, 'nonfinite_diagnostics': 0}


def publish_binary(path, files, metadata):
    path.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (path/name).write_bytes(content if isinstance(content, bytes) else content.encode())
    manifest = {**metadata, 'files': {name: digest(path/name) for name in files}}
    (path/'complete.json').write_text(canonical(manifest)+'\n')
    return manifest


@pytest.fixture
def experiment(tmp_path):
    rows = []
    for i, (full, half) in enumerate([(1,0),(2,0),(3,0),(2,1)]):
        rows.append({'audit_id': 'a'+str(i), 'source_listing_id': str(100+i), 'unit_id': 'u'+str(i),
            'building': 'b'+str(i//2), 'period': '2026-09-01', 'asking_rent': 3000.+i*500,
            'bedrooms': 2, 'bathrooms': full+.5*half, 'reported_full_bathrooms': full,
            'reported_half_bathrooms': half, 'bathroom_count_evidence': {'flags': []},
            'analysis_price_basis': 'current_capture_gross_ask' if i == 0 else 'historical_initial_own_advertisement_ask',
            'canonical_unit_url': 'https://streeteasy.com/building/example/'+str(i)})
    dataset = tmp_path/'dataset'
    source = publish_bundle(dataset, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)},
                            {'version': 'reviewed-bathroom-counts-projection-v1'})
    protocol = {'version': m.EXPERIMENT_VERSION, 'source_manifest_sha256': digest(dataset/'complete.json'),
        'source_observations_sha256': source['files']['observations.jsonl'], 'source_version': source['version'],
        'implementation_sha256': {}, 'rows': 4, 'units': 4, 'buildings': 2, 'current_rows': 1,
        'specification': 'full_half_balance', 'likelihood': 'Student-t log ask', 'bathroom_policy': 'Source counts',
        'uncertainty': 'Conditional associations', 'chains': 4, 'draws': 1000, 'tune': 1000, 'prior_multiplier': 1.}
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    root = tmp_path/'experiment'
    publish_bundle(root/'protocol', {'protocol.json': canonical(protocol)+'\n'},
                   {'version': m.EXPERIMENT_VERSION,'protocol_sha256': ph})
    counts = {'rows': 1, 'units': 1, 'buildings': 1}
    increments = [{'bedrooms':2, 'before_full_half':[1,0], 'after_full_half':[2,0],
        'log_effect': interval(), 'percent_effect': interval(10), 'support_before':counts,
        'support_after':counts, 'supported_endpoints':True}]
    half = {'bedrooms':2, 'full_bathrooms':2, 'before_half':0, 'after_half':1,
        'log_effect': interval(.04), 'percent_effect': interval(4), 'support_before':counts,
        'support_after':counts, 'supported_endpoints':True, 'encoded_contrast':True}
    balance = {'bedrooms':2, 'difference':{**interval(.03),'probability_positive':.8}, 'probability_first_increment_larger':.8,
               'support':[counts,counts,counts]}
    contrasts = {'increments':increments, 'half_bath_increments':[half], 'balance':[balance]}
    names = ['bedrooms_gt_1','listed_floor','bathroom_composition_unknown','laundry_type.contrast_0','laundry_type.unknown']
    design_support = {'rows':4,'bathroom_composition_known':4,'features':len(names)}
    design = {'spec':'full_half_balance','support':design_support,'features':names,
              'numeric':{'listed_floor':{'center':5.,'scale':3.}}}
    coefficients = [{'feature':name,**interval()} for name in names]
    residuals = []
    for i,row in enumerate(rows):
        fit = row['asking_rent']*(.9 if i%2 == 0 else 1.2)
        residuals.append({k:row[k] for k in ('audit_id','source_listing_id','unit_id','building','period','asking_rent')} | {
            'fitted_rent':fit,'latent_rent_lower_95':fit*.9,'latent_rent_upper_95':fit*1.1,
            'residual_dollars':row['asking_rent']-fit,'residual_log':math.log(row['asking_rent']/fit)})
    group_rows = [{'kind':kind,'id':identity,'log_effect':interval(.1 if i%2 == 0 else -.1),
                   'percent_effect':interval(10 if i%2 == 0 else -10)}
                  for kind,keys in [('building',['b0','b1']),('unit',['u0','u1','u2','u3'])]
                  for i,identity in enumerate(keys)]
    diag = diagnostics()
    summary = {'protocol_sha256':ph,'status':'exploratory_converged','diagnostics':diag,
               'derived_diagnostics':diag,'design_support':design_support,'bathroom_balance':[balance],
               'median_absolute_log_residual':(abs(residuals[0]['residual_log'])+abs(residuals[1]['residual_log']))/2}
    files = {'summary.json':canonical(summary)+'\n','diagnostics.json':canonical(diag)+'\n',
        'derived-diagnostics.json':canonical(diag)+'\n','bathroom-contrasts.json':canonical(contrasts)+'\n',
        'coefficients.json':canonical(coefficients)+'\n','feature-design.json':canonical(design)+'\n',
        'time-design.json':canonical({'buildings':['b0','b1'],'unit_ids':['u0','u1','u2','u3']})+'\n',
        'time-design.npz':bytes(range(256)), 'posterior.nc':bytes(reversed(range(256))),
        'residuals.jsonl':''.join(canonical(r)+'\n' for r in residuals),
        'group-effects.jsonl':''.join(canonical(r)+'\n' for r in group_rows)}
    publish_binary(root/'fit', files, {'version':m.EXPERIMENT_VERSION,'protocol_sha256':ph})
    return root,dataset,rows,files,summary,contrasts


def rewrite_fit(root, files):
    manifest = json.loads((root/'fit'/'complete.json').read_text())
    publish_binary(root/'fit', files, {'version':manifest['version'],'protocol_sha256':manifest['protocol_sha256']})


def test_verified_report_deduplicates_contrasts_separates_reporting_and_replays(experiment,tmp_path):
    root,dataset,rows,files,summary,contrasts = experiment
    # The original runner repeats the same increment in its balance section.
    contrasts['increments'] *= 2
    files['bathroom-contrasts.json'] = canonical(contrasts)+'\n'
    rewrite_fit(root,files)
    report,_ = m.build_report(root,dataset,top=1)
    assert len(report['bathrooms']['full_bath_increments']) == 1
    assert len(report['bathrooms']['half_bath_increments']) == 1
    assert report['cohort']['current_rows'] == 1
    assert len(report['group_rankings']) == 4
    assert len(report['residual_cases']) == 2
    assert len(report['current_residuals']) == 1
    assert report['coefficients']['omitted_category_basis_coefficients'] == ['laundry_type.contrast_0']
    assert {r['feature'] for r in report['coefficients']['reporting_coefficients']} == {'bathroom_composition_unknown','laundry_type.unknown'}
    notes = {r['feature']:r['encoded_unit'] for r in report['coefficients']['encoded_value_coefficients']}
    assert '3 raw units' in notes['listed_floor']
    assert 'not a fixed-square-footage' in notes['bedrooms_gt_1']
    output=tmp_path/'report'
    first=m.run(root,dataset,output,top=1)
    assert m.run(root,dataset,output,top=1) == first
    _,saved=_verified_bundle(output,retain={'report.json','report.html'})
    assert json.loads(saved['report.json']) == report
    assert b'<a href="https://streeteasy.com/rental/' in saved['report.html']
    assert b'<script' not in saved['report.html'] and b'<iframe' not in saved['report.html']


@pytest.mark.parametrize('mutation', ['status','parameter_failure','derived_failure','optimistic_flag'])
def test_diagnostic_only_or_unacceptable_fit_refused(experiment,mutation):
    root,dataset,_,files,summary,_ = experiment
    if mutation == 'status':
        summary['status']='diagnostic_only_do_not_interpret_intervals'
    else:
        key='diagnostics' if mutation == 'parameter_failure' else 'derived_diagnostics'
        updated=copy.deepcopy(summary[key])
        if mutation == 'optimistic_flag':updated['max_rhat']=1.05
        else:updated['acceptable']=False
        summary[key]=updated
        files['diagnostics.json' if key == 'diagnostics' else 'derived-diagnostics.json']=canonical(updated)+'\n'
    files['summary.json']=canonical(summary)+'\n';rewrite_fit(root,files)
    with pytest.raises(ValueError,match='diagnostic|Diagnostic|status'):
        m.build_report(root,dataset)


def test_source_target_and_membership_must_match_even_if_files_rehashed(experiment):
    root,dataset,_,files,_,_=experiment
    residuals=m.jsonl(files['residuals.jsonl'].encode())
    residuals[0]['asking_rent']+=100
    files['residuals.jsonl']=''.join(canonical(r)+'\n' for r in residuals)
    rewrite_fit(root,files)
    with pytest.raises(ValueError,match='target or arithmetic'):
        m.build_report(root,dataset)
    residuals[0]['audit_id']='wrong'
    files['residuals.jsonl']=''.join(canonical(r)+'\n' for r in residuals)
    rewrite_fit(root,files)
    with pytest.raises(ValueError,match='identity'):
        m.build_report(root,dataset)


def test_contrast_support_recomputed_from_source(experiment):
    root,dataset,_,files,_,contrasts=experiment
    contrasts['increments'][0]['support_before']={'rows':2,'units':1,'buildings':1}
    files['bathroom-contrasts.json']=canonical(contrasts)+'\n';rewrite_fit(root,files)
    with pytest.raises(ValueError,match='increment support'):
        m.build_report(root,dataset)


def test_binary_posterior_tampering_refused(experiment):
    root,dataset,*_=experiment
    (root/'fit'/'posterior.nc').write_bytes(b'changed')
    with pytest.raises(ValueError,match='integrity failure: posterior.nc'):
        m.build_report(root,dataset)


def test_alternate_valid_source_bundle_refused(experiment,tmp_path):
    root,_,rows,*_=experiment
    other=tmp_path/'different-source'
    rows=copy.deepcopy(rows);rows[0]['asking_rent']+=10
    publish_bundle(other,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},
                   {'version':'reviewed-bathroom-counts-projection-v1'})
    with pytest.raises(ValueError,match='Source dataset'):
        m.build_report(root,other)


def test_html_escapes_source_strings_and_does_not_label_basis_as_premium(experiment):
    root,dataset,*_=experiment
    report,_=m.build_report(root,dataset)
    report['group_rankings'][0]['id']='<script>alert(1)</script>'
    html=m.html_report(report)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'not a difference in percentage points' in html
    assert 'not predictive uncertainty or mean rent' in html
    assert 'laundry_type.contrast_0' not in html
    HTMLParser().feed(html)


def v3_fixture(experiment, mode='bedroom', source_version='reviewed-scope-composition-projection-v2'):
    """Upgrade only synthetic saved products; never import the sampling runtime."""
    root,dataset,rows,files,summary,contrasts = experiment
    # Preserve the supported 2BR full-bath balance cells; change only the half-bath case.
    rows[3]['bedrooms'] = 1
    half = contrasts['half_bath_increments'][0]
    half['support_after'] = {'rows':0,'units':0,'buildings':0}
    half['supported_endpoints'] = False
    files['bathroom-contrasts.json'] = canonical(contrasts)+'\n'
    source = publish_binary(dataset,{'observations.jsonl':''.join(canonical(r)+'\n' for r in rows)},
                            {'version':source_version})
    config = {'version':'bayesian-feature-residual-graph-v3','residual_scale':mode,'student_t_nu':5.,
              'beta_prior_multiplier':1.,'building_prior_scale':.7,'unit_prior_scale':.125,
              'residual_sigma_prior_scale':.25,'residual_bedroom_levels':[1,2] if mode=='bedroom' else [],
              'residual_bedroom_counts':[1,3] if mode=='bedroom' else [],
              'residual_bedroom_offset_scale_prior':.3 if mode=='bedroom' else None,
              'parameterization':'Synthetic saved configuration; no graph compiled.'}
    def scale(value): return {**interval(value),'probability_positive':1.}
    scales = {'version':'bayesian-residual-scale-summary-v1','graph_configuration':config,'student_t_nu':5.,
              'scale_units':'Log advertised asking rent; Student-t scale, not its standard deviation.',
              'global_sigma':scale(.2),
              'global_sigma_role':'Geometric mean of bedroom-level scales (equal level weights)' if mode=='bedroom' else 'Shared observation scale',
              'by_bedroom':[{'bedrooms':1,'sigma':scale(.15),'support':{'rows':1,'units':1,'buildings':1}},
                            {'bedrooms':2,'sigma':scale(.25),'support':{'rows':3,'units':3,'buildings':2}}] if mode=='bedroom' else [],
              'interpretation':'Separate conditional 95% posterior intervals. Residual variation is not latent conditional-median uncertainty. Student-t standard deviation equals scale * sqrt(5/3); no mean or feature contribution changed by this summary.'}
    protocol = json.loads((root/'protocol'/'protocol.json').read_text())
    protocol.update(version=m.EXPERIMENT_V3,source_manifest_sha256=digest(dataset/'complete.json'),
        source_observations_sha256=source['files']['observations.jsonl'],source_version=source['version'],
        graph_configuration=config,residual_scale=mode,building_prior_scale=.7,unit_prior_scale=.125)
    files['graph-configuration.json'] = canonical(config)+'\n'
    files['residual-scales.json'] = canonical(scales)+'\n'
    rewrite_v3(root,protocol,files)
    return root,dataset,protocol,files,scales


def rewrite_v3(root, protocol, files):
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    publish_binary(root/'protocol',{'protocol.json':canonical(protocol)+'\n'},
                   {'version':protocol['version'],'protocol_sha256':ph})
    summary = json.loads(files['summary.json']); summary['protocol_sha256'] = ph
    files['summary.json'] = canonical(summary)+'\n'
    publish_binary(root/'fit',files,{'version':protocol['version'],'protocol_sha256':ph})


@pytest.mark.parametrize('version,fault', [(v, f) for v in sorted(m.reviewed_source_lineage.VERSIONS)
    for f in [None, 'missing_lineage', 'unintended_change', 'missing_sidecar', 'changed_sidecar']
    if f not in ('missing_sidecar', 'changed_sidecar') or v in
        (m.reviewed_source_lineage.reviewed_cohort_quarantine.VERSION, m.reviewed_source_lineage.elevator_corrections.VERSION)])
def test_corrected_source_report_requires_exact_review_lineage(experiment, tmp_path, version, fault):
    from tests.test_reviewed_source_lineage import revise, observations_hash

    root, dataset, protocol, files, _ = v3_fixture(experiment, mode='shared')
    rows = m.jsonl((dataset/'observations.jsonl').read_bytes())
    for row in rows:
        row.update(known_at='2026-09-18T00:00:00Z', laundry_type='in_building', advertised_floor=3, capture_ids=[row['audit_id']], elevator=True)
    sidecar_files = {}
    if version in (m.reviewed_source_lineage.reviewed_cohort_quarantine.VERSION, m.reviewed_source_lineage.elevator_corrections.VERSION):
        from tests.test_reviewed_cohort_quarantine import add_excluded_row, quarantine_last
        rows = add_excluded_row(rows)
    parent = {'version': m.reviewed_source_lineage.REFRESHED,
              'files': {'observations.jsonl': observations_hash(rows)}}
    manifest, rows = revise(parent, rows, m.reviewed_source_lineage.LAUNDRY, 'laundry_type', 'laundry')
    if version in (m.reviewed_source_lineage.FLOOR, m.reviewed_source_lineage.laundry_floor_split.VERSION,
                   m.reviewed_source_lineage.reviewed_cohort_quarantine.VERSION, m.reviewed_source_lineage.elevator_corrections.VERSION):
        manifest, rows = revise(manifest, rows, m.reviewed_source_lineage.FLOOR, 'advertised_floor', 'floor', index=1)
    if version == m.reviewed_source_lineage.laundry_floor_split.VERSION:
        from tests.test_laundry_floor_projection import extend
        manifest, rows = extend(manifest, rows)
    if version in (m.reviewed_source_lineage.reviewed_cohort_quarantine.VERSION, m.reviewed_source_lineage.elevator_corrections.VERSION):
        manifest, rows, sidecar = quarantine_last(manifest, rows)
        sidecar_files['quarantined.jsonl'] = ''.join(canonical(r)+'\n' for r in sidecar)
    if version == m.reviewed_source_lineage.elevator_corrections.VERSION:
        from tests.test_elevator_correction_projection import extend
        manifest, rows, elevator_sidecar = extend(manifest, rows)
        sidecar_files['elevator-corrections.jsonl'] = ''.join(canonical(r)+'\n' for r in elevator_sidecar)
    if fault == 'missing_lineage':
        manifest = {'version': version}
    elif fault == 'unintended_change':
        rows[2]['known_at'] = '2026-09-17T00:00:00Z'
    elif fault == 'missing_sidecar': sidecar_files.clear()
    elif fault == 'changed_sidecar':
        sidecar[0]['observation']['asking_rent'] += 1
        sidecar_files['quarantined.jsonl'] = ''.join(canonical(r)+'\n' for r in sidecar)
    source = publish_binary(dataset, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows), **sidecar_files}, manifest)
    protocol.update(source_manifest_sha256=digest(dataset/'complete.json'),
                    source_observations_sha256=source['files']['observations.jsonl'], source_version=version)
    rewrite_v3(root, protocol, files)
    if fault:
        with pytest.raises(ValueError, match='lineage|Reconstructed parent|Reconstructed laundry|Reconstructed quarantine|Quarantine|Elevator'):
            m.build_report(root, dataset)
    else:
        report, _ = m.build_report(root, dataset)
        assert report['source_version'] == version and report['cohort']['rows'] == 4
        output = tmp_path/'corrected-report'
        m.run(root, dataset, output)
        assert (output/'reviewed_source_lineage.py').read_text() == Path(m.reviewed_source_lineage.__file__).read_text()


@pytest.mark.parametrize('mode',['shared','bedroom'])
@pytest.mark.parametrize('source_version',['reviewed-scope-composition-projection-v2','reviewed-capture-refreshed-analysis-v1'])
def test_v3_source_bound_scale_summary_and_html(experiment,tmp_path,mode,source_version):
    root,dataset,protocol,files,scales = v3_fixture(experiment,mode,source_version)
    report,_ = m.build_report(root,dataset)
    assert m.EXPERIMENT_VERSION == 'observable-bayesian-bathroom-experiment-v2'
    assert report['version'] == 'verified-bayesian-feature-report-v2'
    assert report['experiment_version'] == m.EXPERIMENT_V3
    assert report['source_version'] == source_version
    assert report['residual_scales'] == scales
    assert report['graph_configuration'] == protocol['graph_configuration']
    assert report['method']['residual_scale'] == mode
    assert report['method']['building_prior_scale'] == .7
    assert report['method']['unit_prior_scale'] == .125
    assert report['cohort']['rows'] == 4 and len(report['current_residuals']) == 1
    html = m.html_report(report)
    assert 'Residual-scale mode: '+mode in html
    assert 'Student-t scale, not its standard deviation' in html
    assert 'not latent conditional-median uncertainty' in html
    if mode == 'bedroom':
        assert 'Geometric mean of bedroom-level scales' in html and '1 bedrooms' in html
    output = tmp_path/'v3-report'
    first = m.run(root,dataset,output)
    assert m.run(root,dataset,output) == first


@pytest.mark.parametrize('name',['graph-configuration.json','residual-scales.json'])
def test_v3_missing_or_tampered_noise_products_refused(experiment,name):
    root,dataset,protocol,files,_ = v3_fixture(experiment)
    (root/'fit'/name).write_text('{}\n')
    with pytest.raises(ValueError,match='integrity'): m.build_report(root,dataset)
    del files[name]
    rewrite_v3(root,protocol,files)
    with pytest.raises(ValueError,match='missing inference products'): m.build_report(root,dataset)


@pytest.mark.parametrize('mutation',['protocol_mode','protocol_prior','configuration_only','summary_only',
    'graph_version','nu','sigma_prior','bedroom_offset_prior','source_levels','source_counts','boolean_level'])
def test_v3_rehashed_configuration_contradictions_refused(experiment,mutation):
    root,dataset,protocol,files,scales = v3_fixture(experiment)
    config = copy.deepcopy(protocol['graph_configuration'])
    if mutation == 'protocol_mode': protocol['residual_scale'] = 'shared'
    if mutation == 'protocol_prior': protocol['building_prior_scale'] = .8
    if mutation == 'configuration_only': config['unit_prior_scale'] = .9
    if mutation == 'summary_only': scales['graph_configuration'] = {**config,'unit_prior_scale':.9}
    if mutation == 'graph_version': config['version'] = 'unsupported'
    if mutation == 'nu': config['student_t_nu'] = 7
    if mutation == 'sigma_prior': config['residual_sigma_prior_scale'] = .7
    if mutation == 'bedroom_offset_prior': config['residual_bedroom_offset_scale_prior'] = .6
    if mutation == 'source_levels': config['residual_bedroom_levels'] = [1,3]
    if mutation == 'source_counts': config['residual_bedroom_counts'] = [2,2]
    if mutation == 'boolean_level': config['residual_bedroom_levels'] = [True,2]
    if mutation not in ('protocol_mode','protocol_prior','configuration_only','summary_only'):
        protocol['graph_configuration'] = config
        scales['graph_configuration'] = config
    files['graph-configuration.json'] = canonical(config)+'\n'
    files['residual-scales.json'] = canonical(scales)+'\n'
    rewrite_v3(root,protocol,files)
    with pytest.raises(ValueError,match='Residual|residual|Unsupported'): m.build_report(root,dataset)


@pytest.mark.parametrize('mutation',['support_rows','support_units','support_buildings','missing_level','duplicate_level',
    'negative_scale','zero_scale','unordered_interval','positive_probability','wrong_scale_units','wrong_role','wrong_summary_nu'])
def test_v3_rehashed_scale_claims_refused(experiment,mutation):
    root,dataset,protocol,files,scales = v3_fixture(experiment)
    if mutation.startswith('support_'): scales['by_bedroom'][0]['support'][mutation.removeprefix('support_')] += 1
    if mutation == 'missing_level': scales['by_bedroom'].pop()
    if mutation == 'duplicate_level': scales['by_bedroom'][1]['bedrooms'] = 1
    if mutation == 'negative_scale': scales['global_sigma']['lower_95'] = -.1
    if mutation == 'zero_scale': scales['by_bedroom'][0]['sigma']['lower_95'] = 0
    if mutation == 'unordered_interval': scales['by_bedroom'][0]['sigma']['upper_95'] = .01
    if mutation == 'positive_probability': scales['global_sigma']['probability_positive'] = .5
    if mutation == 'wrong_scale_units': scales['scale_units'] = 'Standard deviation'
    if mutation == 'wrong_role': scales['global_sigma_role'] = 'Frequency-weighted mean'
    if mutation == 'wrong_summary_nu': scales['student_t_nu'] = 8
    files['residual-scales.json'] = canonical(scales)+'\n'
    rewrite_v3(root,protocol,files)
    with pytest.raises(ValueError,match='Residual|residual|posterior interval'): m.build_report(root,dataset)


@pytest.mark.parametrize('family',['diagnostics','derived_diagnostics'])
def test_v3_both_diagnostic_gates_still_required(experiment,family):
    root,dataset,protocol,files,_ = v3_fixture(experiment)
    summary = json.loads(files['summary.json']); summary[family]['max_rhat'] = 1.02
    files['summary.json'] = canonical(summary)+'\n'
    files['diagnostics.json' if family=='diagnostics' else 'derived-diagnostics.json'] = canonical(summary[family])+'\n'
    rewrite_v3(root,protocol,files)
    with pytest.raises(ValueError,match='Unacceptable.*diagnostics'): m.build_report(root,dataset)
