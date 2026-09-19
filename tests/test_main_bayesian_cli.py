"""Main CLI routing is exact PyMC; no sampling or fallback in these tests."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from apartments.cli import app


@pytest.fixture
def fit_route(monkeypatch):
    from models import bayesian_disk_experiment as runner
    from models import bayesian_floor_spline_experiment as spline
    from apartments import research_pipeline
    seen=[]
    def run(args, route):
        from threadpoolctl import threadpool_info
        assert all(p['num_threads']==1 for p in threadpool_info() if p['user_api']=='blas')
        seen.append({**vars(args), '_runner': route})
        return {'status':'diagnostic_only','protocol_sha256':'synthetic'}
    monkeypatch.setattr(runner,'run',lambda args:run(args, 'legacy_disk'))
    monkeypatch.setattr(spline,'run',lambda args:run(args, 'spline'))
    monkeypatch.setattr(research_pipeline,'fit_dataset',lambda *a,**kw:pytest.fail('No robust fallback'))
    return seen


def test_fit_pricing_defaults_to_exact_spline_disk_runner(fit_route):
    result=CliRunner().invoke(app,['fit-pricing','source','posterior'])
    assert result.exit_code==0,result.output
    assert json.loads(result.output)['status']=='diagnostic_only'  # Never silently promotes diagnostics.
    assert fit_route==[{'dataset':Path('source'),'output':Path('posterior'),'draws':4000,'tune':2000,
        'chains':4,'seed':20260918,'spec':'full_half_balance','residual_scale':'shared',
        'target_accept':.93,'adaptation':'diag','prior_multiplier':1.,'building_prior_scale':.35,
        'unit_prior_scale':.25,'residual_parameterization':'centered','graph_validation':None,
        'floor_increments':False,'floor_increment_prior_scale':.15,
        'floor_prior_scale':.10,'maxdepth':10,'_runner':'spline'}]


def test_explicit_sampler_and_model_options_are_preserved(fit_route):
    result=CliRunner().invoke(app,['fit-pricing','source','posterior','--draws','1200','--tune','1600',
        '--chains','3','--seed','12','--spec','full_half','--residual-scale','bedroom',
        '--target-accept','.97','--adaptation','low_rank','--prior-multiplier','.5',
        '--building-prior-scale','.7','--unit-prior-scale','.125',
        '--residual-parameterization','noncentered','--graph-validation','proof','--floor-increments'])
    assert result.exit_code==0,result.output
    assert fit_route[0]=={'dataset':Path('source'),'output':Path('posterior'),'draws':1200,'tune':1600,
        'chains':3,'seed':12,'spec':'full_half','residual_scale':'bedroom','target_accept':.97,
        'adaptation':'low_rank','prior_multiplier':.5,'building_prior_scale':.7,'unit_prior_scale':.125,
        'residual_parameterization':'noncentered','graph_validation':Path('proof'),
        'floor_increments':True,'floor_increment_prior_scale':.15,
        'floor_prior_scale':.10,'maxdepth':None,'_runner':'legacy_disk'}


@pytest.mark.parametrize('args',[
    ['--chains','1'],['--draws','0'],['--tune','0'],['--target-accept','1'],
    ['--prior-multiplier','nan'],['--spec','surrogate'],['--residual-scale','robust'],
    ['--adaptation','variational'],['--residual-parameterization','other'],
    ['--execution','surrogate'],['--floor-increments','--floor-increment-prior-scale','0'],
    ['--floor-model','unknown'],['--floor-model',''],['--floor-prior-scale','0'],['--floor-prior-scale','nan'],
    ['--floor-prior-scale','inf'],['--maxdepth','0'],['--maxdepth','21'],
    ['--execution','memory'],['--graph-validation','legacy-proof'],
    ['--floor-model','spline','--floor-increments'],
    ['--floor-model','spline','--linear-floor'],
    ['--floor-model','increments','--floor-increments'],
    ['--linear-floor','--execution','memory','--maxdepth','10'],
])
def test_invalid_settings_fail_before_runner(fit_route,args):
    result=CliRunner().invoke(app,['fit-pricing','source','posterior',*args])
    assert result.exit_code!=0
    assert not fit_route


def test_sampler_or_source_failure_never_calls_legacy(fit_route,monkeypatch):
    from models import bayesian_floor_spline_experiment as runner
    def fail(args):raise ValueError('Source manifest mismatch')
    monkeypatch.setattr(runner,'run',fail)
    result=CliRunner().invoke(app,['fit-pricing','source','posterior'])
    assert result.exit_code==1 and 'Source manifest mismatch' in result.output
    assert not fit_route


def test_explicit_floor_design_routes_to_disk_with_its_prior(fit_route):
    result=CliRunner().invoke(app,['fit-pricing','source','posterior','--floor-increments',
        '--floor-increment-prior-scale','.08'])
    assert result.exit_code==0,result.output
    assert fit_route[0]['floor_increments'] is True
    assert fit_route[0]['floor_increment_prior_scale']==.08
    assert fit_route[0]['_runner']=='legacy_disk'
    assert fit_route[0]['maxdepth'] is None


@pytest.mark.parametrize('model', ['spline', 'increments', 'linear'])
def test_explicit_floor_model_routes_without_legacy_flag(fit_route, model):
    result = CliRunner().invoke(app, ['fit-pricing', 'source', 'posterior', '--floor-model', model])
    assert result.exit_code == 0, result.output
    assert fit_route[0]['_runner'] == ('spline' if model == 'spline' else 'legacy_disk')
    assert fit_route[0]['floor_increments'] is (model == 'increments')
    assert fit_route[0]['maxdepth'] == (10 if model == 'spline' else None)


def test_explicit_spline_prior_and_depth_are_preserved(fit_route):
    result = CliRunner().invoke(app, ['fit-pricing', 'source', 'posterior', '--floor-model', 'spline',
        '--floor-prior-scale', '.05', '--maxdepth', '12', '--tune', '4000', '--draws', '6000', '--seed', '20260924'])
    assert result.exit_code == 0, result.output
    assert fit_route[0]['floor_prior_scale'] == .05
    assert fit_route[0]['maxdepth'] == 12
    assert (fit_route[0]['tune'], fit_route[0]['draws'], fit_route[0]['seed']) == (4000, 6000, 20260924)


def test_legacy_disk_depth_is_explicit(fit_route):
    result = CliRunner().invoke(app, ['fit-pricing', 'source', 'posterior', '--linear-floor', '--maxdepth', '14'])
    assert result.exit_code == 0, result.output
    assert fit_route[0]['_runner'] == 'legacy_disk'
    assert fit_route[0]['maxdepth'] == 14


@pytest.mark.parametrize('increments',[False,True])
def test_memory_execution_is_explicit_for_older_protocol_replay(fit_route,monkeypatch,increments):
    from models import bayesian_disk_experiment as disk
    calls=[]
    runner=disk.increments if increments else disk.linear
    monkeypatch.setattr(runner,'run',lambda args:calls.append(vars(args)) or {'status':'replayed'})
    result=CliRunner().invoke(app,['fit-pricing','source','posterior','--execution','memory',
        *(['--floor-increments'] if increments else ['--linear-floor'])])
    assert result.exit_code==0,result.output
    assert not fit_route and len(calls)==1
    assert calls[0]['floor_increments']==increments


def test_linear_floor_requires_explicit_legacy_choice(fit_route):
    result = CliRunner().invoke(app, ['fit-pricing', 'source', 'posterior', '--linear-floor'])
    assert result.exit_code == 0, result.output
    assert fit_route[0]['floor_increments'] is False


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
