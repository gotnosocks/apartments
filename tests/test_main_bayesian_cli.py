"""Main CLI routing is exact PyMC; no sampling or fallback in these tests."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from apartments.cli import app


@pytest.fixture
def fit_route(monkeypatch):
    from models import bayesian_feature_experiment_v3 as runner
    from apartments import research_pipeline
    seen=[]
    def run(args):
        from threadpoolctl import threadpool_info
        assert all(p['num_threads']==1 for p in threadpool_info() if p['user_api']=='blas')
        seen.append(vars(args).copy())
        return {'status':'diagnostic_only','protocol_sha256':'synthetic'}
    monkeypatch.setattr(runner,'run',run)
    monkeypatch.setattr(research_pipeline,'fit_dataset',lambda *a,**kw:pytest.fail('No robust fallback'))
    return seen


def test_fit_pricing_routes_defaults_to_exact_v3_runner(fit_route):
    result=CliRunner().invoke(app,['fit-pricing','source','posterior'])
    assert result.exit_code==0,result.output
    assert json.loads(result.output)['status']=='diagnostic_only'  # Never silently promotes diagnostics.
    assert fit_route==[{'dataset':Path('source'),'output':Path('posterior'),'draws':4000,'tune':2000,
        'chains':4,'seed':20260918,'spec':'full_half_balance','residual_scale':'shared',
        'target_accept':.93,'adaptation':'diag','prior_multiplier':1.,'building_prior_scale':.35,
        'unit_prior_scale':.25,'residual_parameterization':'centered','graph_validation':None}]


def test_explicit_sampler_and_model_options_are_preserved(fit_route):
    result=CliRunner().invoke(app,['fit-pricing','source','posterior','--draws','1200','--tune','1600',
        '--chains','3','--seed','12','--spec','full_half','--residual-scale','bedroom',
        '--target-accept','.97','--adaptation','low_rank','--prior-multiplier','.5',
        '--building-prior-scale','.7','--unit-prior-scale','.125',
        '--residual-parameterization','noncentered','--graph-validation','proof'])
    assert result.exit_code==0,result.output
    assert fit_route[0]=={'dataset':Path('source'),'output':Path('posterior'),'draws':1200,'tune':1600,
        'chains':3,'seed':12,'spec':'full_half','residual_scale':'bedroom','target_accept':.97,
        'adaptation':'low_rank','prior_multiplier':.5,'building_prior_scale':.7,'unit_prior_scale':.125,
        'residual_parameterization':'noncentered','graph_validation':Path('proof')}


@pytest.mark.parametrize('args',[
    ['--chains','1'],['--draws','0'],['--tune','0'],['--target-accept','1'],
    ['--prior-multiplier','nan'],['--spec','surrogate'],['--residual-scale','robust'],
    ['--adaptation','variational'],['--residual-parameterization','other'],
])
def test_invalid_settings_fail_before_runner(fit_route,args):
    result=CliRunner().invoke(app,['fit-pricing','source','posterior',*args])
    assert result.exit_code!=0
    assert not fit_route


def test_sampler_or_source_failure_never_calls_legacy(fit_route,monkeypatch):
    from models import bayesian_feature_experiment_v3 as runner
    def fail(args):raise ValueError('Source manifest mismatch')
    monkeypatch.setattr(runner,'run',fail)
    result=CliRunner().invoke(app,['fit-pricing','source','posterior'])
    assert result.exit_code==1 and 'Source manifest mismatch' in result.output


def test_legacy_fitter_has_explicit_separate_command(monkeypatch):
    from apartments import research_pipeline
    calls=[]
    monkeypatch.setattr(research_pipeline,'fit_dataset',lambda *args,**kwargs:calls.append((args,kwargs)) or {'legacy':True})
    result=CliRunner().invoke(app,['fit-pricing-legacy','source','old-model','--holdout-fraction','0','--ridge','2'])
    assert result.exit_code==0,result.output
    assert json.loads(result.output)=={'legacy':True}
    assert calls==[((Path('source'),Path('old-model')),{'holdout_fraction':0.,'ridge':2.})]


@pytest.fixture
def analysis_route(monkeypatch):
    from apartments import main_analysis,bayesian_analysis
    calls=[]
    selection={'model_family':'pymc_bayesian','protocol_sha256':'bound'}
    workspace=SimpleNamespace(detail=lambda key:calls.append(('detail',key)) or {'audit_id':key,'draws':16000},
        counterfactual=lambda key,changes:calls.append(('counterfactual',key,changes)) or {'status':'reporting_change'},
        close=lambda:calls.append(('close',)))
    def selected(path):
        calls.append(('selection',path));return selection,Path('accepted-fit'),Path('exact-source')
    def load(experiment,dataset):
        calls.append(('load',experiment,dataset));return workspace
    monkeypatch.setattr(main_analysis,'load_selection',selected)
    monkeypatch.setattr(bayesian_analysis.BayesianAnalysis,'load',load)
    return calls,workspace


def test_analysis_uses_selected_binding_detail_and_joint_source_values(analysis_route):
    calls,_=analysis_route
    result=CliRunner().invoke(app,['analyze-apartment','capture:123','--selection','chosen.json',
        '--changes','{"bedrooms":2,"full_bathrooms":2,"window_exposures.north":true}'])
    assert result.exit_code==0,result.output
    value=json.loads(result.output)
    assert value['detail']['draws']==16000 and value['counterfactual']['status']=='reporting_change'
    assert calls==[('selection',Path('chosen.json')),('load',Path('accepted-fit'),Path('exact-source')),
        ('detail','capture:123'),('counterfactual','capture:123',{'bedrooms':2,'full_bathrooms':2,'window_exposures.north':True}),('close',)]
    assert 'delta_dollars' not in value['counterfactual']


def test_default_analysis_selection_and_no_implicit_counterfactual(analysis_route):
    from apartments.main_analysis import DEFAULT_SELECTION
    calls,_=analysis_route
    result=CliRunner().invoke(app,['analyze-apartment','a1'])
    assert result.exit_code==0,result.output
    assert calls[0]==('selection',DEFAULT_SELECTION)
    assert 'counterfactual' not in json.loads(result.output)
    assert not any(call[0]=='counterfactual' for call in calls)


@pytest.mark.parametrize('changes',['[]','{}','null','not-json','{"bedrooms":1e309}','{"bedrooms":NaN}','{"bedrooms":1,"bedrooms":2}'])
def test_invalid_json_rejected_before_opening_posterior(analysis_route,changes):
    calls,_=analysis_route
    result=CliRunner().invoke(app,['analyze-apartment','a1','--changes',changes])
    assert result.exit_code==1 and not calls


def test_selected_binding_failure_has_no_fallback_or_posterior_load(analysis_route,monkeypatch):
    from apartments import main_analysis
    def fail(path):raise ValueError('Selected source differs')
    monkeypatch.setattr(main_analysis,'load_selection',fail)
    calls,_=analysis_route
    result=CliRunner().invoke(app,['analyze-apartment','a1'])
    assert result.exit_code==1 and 'Selected source differs' in result.output
    assert not calls


def test_unknown_apartment_closes_verified_workspace(analysis_route):
    calls,workspace=analysis_route
    def fail(key):raise KeyError(key)
    workspace.detail=fail
    result=CliRunner().invoke(app,['analyze-apartment','unknown'])
    assert result.exit_code==1 and calls[-1]==('close',)


def test_unsupported_change_closes_workspace_and_returns_no_partial_result(analysis_route):
    calls,workspace=analysis_route
    def fail(key,changes):raise ValueError('Unsupported field')
    workspace.counterfactual=fail
    result=CliRunner().invoke(app,['analyze-apartment','a1','--changes','{"foo":1}'])
    assert result.exit_code==1 and 'Unsupported field' in result.output
    assert calls[-1]==('close',)
    assert '"detail"' not in result.output


def test_runner_scope_restores_caller_blas_thread_count(fit_route):
    from threadpoolctl import threadpool_info,threadpool_limits
    with threadpool_limits(limits=2,user_api='blas'):
        result=CliRunner().invoke(app,['fit-pricing','source','posterior'])
        assert result.exit_code==0,result.output
        assert all(p['num_threads']==2 for p in threadpool_info() if p['user_api']=='blas')
    assert len(fit_route)==1
