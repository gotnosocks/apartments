"""Completed-report integrity gates without loading posterior arrays."""
import json
from pathlib import Path
import shutil

import pytest

from apartments import bayesian_review as m
from apartments.corrections import canonical
from apartments.research_pipeline import digest,publish_bundle

ROOT=Path(__file__).resolve().parents[1]/'data/model'
AVAILABLE=all((ROOT/name/'complete.json').exists() for name in m.NAMES.values())


def accepted_diagnostics():
    return {'acceptable':True,'max_rhat':1.002,'min_ess_bulk':900.,'min_ess_tail':800.,
            'min_bfmi':.8,'divergences':0,'maxdepth_reached':0,'nonfinite_diagnostics':0}


@pytest.mark.parametrize('key,value',[('acceptable',False),('max_rhat',1.02),('min_ess_bulk',399),
    ('min_ess_tail',float('nan')),('min_bfmi',.2),('divergences',1)])
def test_convergence_gate_rejects_optimistic_flags_or_nonfinite_values(key,value):
    diag=accepted_diagnostics();diag[key]=value
    with pytest.raises(ValueError):m.diagnostics(diag)


def test_small_saved_product_hash_gate_and_missing_completion(tmp_path):
    directory=tmp_path/'saved'
    manifest=publish_bundle(directory,{'summary.json':'{}\n'},{'version':'test'})
    assert m.read_bound(directory,manifest,'summary.json')==b'{}\n'
    (directory/'summary.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='integrity'):m.read_bound(directory,manifest,'summary.json')
    with pytest.raises((OSError,ValueError)):m.load_bundle(tmp_path/'missing','report.json',m.REPORT_VERSION)


def test_nonfinite_or_unordered_intervals_and_impossible_support_refused():
    interval={'median':2.,'lower_95':1.,'upper_95':3.,'probability_positive':.95}
    m.interval(interval);m.support({'rows':12,'units':10,'buildings':3})
    for invalid in [{**interval,'lower_95':4},{**interval,'median':float('nan')},{**interval,'probability_positive':2}]:
        with pytest.raises(ValueError):m.interval(invalid)
    with pytest.raises(ValueError):m.support({'rows':2,'units':3,'buildings':1})


@pytest.fixture
def bundles(tmp_path):
    if not AVAILABLE:pytest.skip('Local completed Bayesian Chelsea bundles unavailable')
    for name in m.NAMES.values():shutil.copytree(ROOT/name,tmp_path/name)
    return tmp_path


def mutate(root,key,name,change,rehash=True):
    directory=root/m.NAMES[key];path=directory/name
    value=json.loads(path.read_text());change(value);path.write_text(canonical(value)+'\n')
    if rehash:
        manifest=json.loads((directory/'complete.json').read_text())
        manifest['files'][name]=digest(path)
        (directory/'complete.json').write_text(canonical(manifest)+'\n')


def test_actual_completed_workspace_never_opens_posterior(monkeypatch,bundles):
    original=Path.open
    def guard(path,*args,**kwargs):
        if path.name=='posterior.nc':pytest.fail('UI attempted to open full posterior')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guard)
    signature=m.workspace_signature(bundles)
    workspace=m.BayesianWorkspace.load(bundles)
    assert len(signature)==64
    assert len(workspace.baseline['current_residuals'])==13
    assert len(workspace.categories['contrasts'])==16
    assert workspace.bathroom_sensitivity['second_half_support']['advertisements']==2
    assert workspace.bathroom_sensitivity['second_half_support']['rows']==2
    assert 7.81<workspace.bathroom_sensitivity['maximum_current_fitted_rent_movement']<7.82
    assert workspace.half['method']['prior_multiplier']==.5
    assert workspace.identity['baseline']['source_observations_sha256']==workspace.identity['half_prior']['source_observations_sha256']


@pytest.mark.parametrize('mutation',['diagnostic_only','optimistic_diagnostics','category_binding','current_source','comparison_shift','report_tamper'])
def test_actual_backend_refuses_invalid_reports_even_when_rehashed(bundles,mutation):
    if mutation=='diagnostic_only':mutate(bundles,'baseline','report.json',lambda x:x.update(status='diagnostic_only_do_not_interpret_intervals'))
    elif mutation=='optimistic_diagnostics':mutate(bundles,'baseline','report.json',lambda x:x['diagnostics']['derived'].update(max_rhat=1.2))
    elif mutation=='category_binding':mutate(bundles,'categories','contrasts.json',lambda x:x['bindings'].update(fit='0'*64))
    elif mutation=='current_source':mutate(bundles,'baseline','report.json',lambda x:x['current_residuals'][0]['source_record'].update(asking_rent=1))
    elif mutation=='comparison_shift':mutate(bundles,'sensitivity','comparison.json',lambda x:x['contrasts'][0].update(median_shift_percentage_points=100))
    else:mutate(bundles,'baseline','report.json',lambda x:x.update(status='tampered'),rehash=False)
    with pytest.raises(ValueError):m.BayesianWorkspace.load(bundles)


@pytest.mark.parametrize('mutation',['binding','protocol','design','interval','support','current'])
def test_bathroom_prior_comparison_must_bind_exact_reports(bundles,mutation):
    key='bathroom_sensitivity'
    if mutation=='binding':
        path=bundles/m.NAMES[key]/'complete.json';value=json.loads(path.read_text())
        value['experiments'][0]['manifest_sha256']['source']='0'*64
        path.write_text(canonical(value)+'\n')
    elif mutation=='protocol':mutate(bundles,key,'comparison.json',lambda x:x['fixed_protocol'].update(source_observations_sha256='0'*64))
    elif mutation=='design':mutate(bundles,key,'comparison.json',lambda x:x['design_sha256'].update(**{'feature-design.json':'0'*64}))
    elif mutation=='interval':mutate(bundles,key,'comparison.json',lambda x:x['comparisons'][0]['bathrooms']['full_bath_increments'][0]['changes']['percent_effect']['candidate'].update(median=99))
    elif mutation=='support':mutate(bundles,key,'comparison.json',lambda x:x['comparisons'][0]['bathrooms']['half_bath_increments'][0]['support_after'].update(rows=999))
    else:mutate(bundles,key,'comparison.json',lambda x:x['comparisons'][0]['residuals']['current_rows'][0]['changes'].update(fitted_rent=999))
    with pytest.raises(ValueError):m.BayesianWorkspace.load(bundles)
