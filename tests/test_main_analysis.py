import json

import pytest

from apartments import main_analysis as m
from .test_bayesian_feature_report import experiment


def test_selection_records_verified_pymc_fit_and_source(experiment,tmp_path):
    fit,dataset=experiment[:2]
    target=tmp_path/'main.json'
    selected=m.select(fit,dataset,target)
    saved,actual_fit,actual_source=m.load_selection(target)
    assert saved==selected
    assert actual_fit==fit and actual_source==dataset
    assert selected['model_family']=='pymc_bayesian'
    assert selected['cohort']['rows']==4


@pytest.mark.parametrize('relative',['fit/complete.json','protocol/complete.json'])
def test_changed_selected_experiment_is_rejected(experiment,tmp_path,relative):
    fit,dataset=experiment[:2];target=tmp_path/'main.json'
    m.select(fit,dataset,target)
    (fit/relative).write_text((fit/relative).read_text()+' ')
    with pytest.raises(ValueError,match='binding differs'):m.load_selection(target)


def test_changed_source_manifest_is_rejected(experiment,tmp_path):
    fit,dataset=experiment[:2];target=tmp_path/'main.json'
    m.select(fit,dataset,target)
    (dataset/'complete.json').write_text('{}')
    with pytest.raises(ValueError,match='source_manifest'):m.load_selection(target)


def test_no_surrogate_fallback_and_failed_selection_preserves_existing_file(experiment,tmp_path):
    fit,dataset=experiment[:2];target=tmp_path/'main.json'
    m.select(fit,dataset,target);original=target.read_bytes()
    (fit/'fit/summary.json').write_text('{}')
    with pytest.raises(ValueError):m.select(fit,dataset,target)
    assert target.read_bytes()==original
    value=json.loads(original);value['model_family']='robust_regression'
    target.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='PyMC Bayesian'):m.load_selection(target)


def test_relative_paths_resolve_against_repository_root(tmp_path):
    assert m.resolve_path('data/model/main',tmp_path)==tmp_path/'data/model/main'
    with pytest.raises(ValueError):m.resolve_path('')
