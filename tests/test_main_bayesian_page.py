"""Main page respects accepted-posterior boundaries and joint comparison gates."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
pytest.importorskip('streamlit')
import streamlit as st
from streamlit.testing.v1 import AppTest
from apartments import bayesian_analysis, bayesian_evidence, main_analysis, bayesian_source_review

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT/'pages/2_Contributions_and_Residuals.py'


def widget(page, kind, label):
    return next(item for item in getattr(page, kind) if item.label == label)


def interval(median):
    return {'lower_95': median*.9, 'median': median, 'upper_95': median*1.1}


class Workspace:
    def __init__(self, status='accepted', contribution_ok=True):
        self.status = status
        self.called = None
        self.summary = {'status': 'exploratory_converged', 'experiment_version': 'verified-test'}
        self.fields = {'bedrooms': {'kind': 'numeric'}, 'full_bathrooms': {'kind': 'numeric'},
            'half_bathrooms': {'kind': 'numeric'}, 'square_feet': {'kind': 'numeric'},
            'view_exposures.courtyard': {'kind': 'boolean'},
            'laundry_type': {'kind': 'category', 'options': ['in_building','in_unit']}}
        self.rows = [{'audit_id': 'a', 'building': 'one-building', 'unit_id': 'unit-a', 'source_listing_id': '123',
            'period': '2026-09-01', 'analysis_price_basis': 'current_capture_gross_ask',
            'bedrooms': 1, 'reported_full_bathrooms': 1, 'reported_half_bathrooms': 0,
            'square_feet': 777, 'laundry_type': 'in_building', 'view_exposures': {'courtyard': True},
            'canonical_unit_url': 'https://streeteasy.com/building/example/a'}]
        self.residuals = [{'audit_id': 'a', 'building': 'one-building', 'unit_id': 'unit-a', 'source_listing_id': '123',
            'period': '2026-09-01', 'asking_rent': 5000., 'fitted_rent': 4900., 'latent_rent_lower_95': 4500.,
            'latent_rent_upper_95': 5300., 'residual_dollars': 100., 'residual_log': .02}]
        self.contribution_ok = contribution_ok

    def detail(self, audit_id):
        return {'source_record': deepcopy(self.rows[0]), 'residual': deepcopy(self.residuals[0]),
            'fitted_median_rent': interval(4900), 'mean_log_rent': 8.5, 'draws': 16000,
            'warnings': [], 'grouped_contributions': {'intercept': 8., 'encoded_feature': .5},
            'grouped_contribution_intervals': ([{'group': 'encoded_feature', 'log_interval': interval(.5)}]
                                             if self.contribution_ok else []),
            'contribution_diagnostics': {'acceptable': self.contribution_ok},
            'contributions': [{'term': 'feature:bedrooms', 'kind': 'encoded_feature', 'mean_log_contribution': .5}],
            'feature_values': {'bedrooms': -99., 'square_feet': -55.},
            'source_values': {'bedrooms': 1., 'full_bathrooms': 1., 'half_bathrooms': 0., 'square_feet': 777.,
                              'view_exposures.courtyard': True, 'laundry_type': 'in_building'},
            'unit_history': deepcopy(self.residuals)}

    def counterfactual(self, audit_id, changes):
        self.called = (audit_id, changes)
        result = {'status': self.status, 'changes': changes, 'warnings': [],
            'support': {'before': {'layout': {'rows': 100}}, 'after': {'layout': {'rows': 90}}},
            'diagnostics': {'acceptable': self.status == 'accepted'}, 'held_fixed': 'Date, building and unit effects.',
            'uncertainty': 'Joint posterior conditional associations.'}
        # Deliberately present estimates for failed statuses: UI must obey status gate.
        result.update(after_rent=interval(5500), delta_dollars=interval(600), delta_percent=interval(12))
        return result


@pytest.fixture
def mocked(monkeypatch, tmp_path):
    st.cache_resource.clear()
    workspace = Workspace()
    monkeypatch.setattr(main_analysis, 'load_selection', lambda path: ({'fit_manifest_sha256':'fit'},tmp_path/'experiment',tmp_path/'dataset'))
    monkeypatch.setattr(bayesian_analysis, 'bundle_signature', lambda *args: str(tmp_path))
    monkeypatch.setattr(bayesian_analysis.BayesianAnalysis, 'load', lambda *args: workspace)
    monkeypatch.setattr(bayesian_evidence, 'load_evidence', lambda *args: {'a': [{'capture_id': 1,
        'source_collected_at': '2026-09-01', 'description': '<b>Literal description</b><script>not executable</script>'}]})
    yield workspace
    st.cache_resource.clear()


def test_raw_source_defaults_joint_changes_and_literal_evidence(mocked):
    page = AppTest.from_file(str(PAGE)).run()
    assert not page.exception and not page.error
    assert len(widget(page,'selectbox','Observation to inspect').options) == 1
    assert any('<b>Literal description</b>' in item.value for item in page.text)
    assert any('MEAN log contributions' in item.value for item in page.caption)
    widget(page,'multiselect','Features to change together').set_value(['bedrooms','square_feet','view_exposures.courtyard']).run()
    assert widget(page,'number_input','square feet').value == 777.
    assert widget(page,'number_input','bedrooms').value == 1.
    assert widget(page,'selectbox','view exposures · courtyard').value is True
    widget(page,'number_input','bedrooms').set_value(2.)
    widget(page,'number_input','square feet').set_value(900.)
    widget(page,'button','Compare with recorded apartment').click().run()
    assert not page.exception and not page.error
    assert mocked.called == ('a', {'bedrooms':2.,'square_feet':900.,'view_exposures.courtyard':True})
    assert any(item.label=='Joint rent change' for item in page.metric)


def test_description_default_follows_selected_cohort_archive(mocked, monkeypatch, tmp_path):
    archive = tmp_path/'refreshed-descriptions'
    monkeypatch.setattr(main_analysis, 'load_selection', lambda path: (
        {'fit_manifest_sha256': 'fit', 'evidence': str(archive)}, tmp_path/'experiment', tmp_path/'dataset'))
    page = AppTest.from_file(str(PAGE)).run()
    assert not page.exception and not page.error
    assert widget(page, 'text_input', 'Archived description bundle').value == str(archive)


@pytest.mark.parametrize('status',['reporting_change','unsupported_endpoint','diagnostic_only'])
def test_failed_comparisons_never_display_physical_intervals(mocked, status):
    mocked.status = status
    page = AppTest.from_file(str(PAGE)).run()
    widget(page,'multiselect','Features to change together').set_value(['bedrooms']).run()
    widget(page,'button','Compare with recorded apartment').click().run()
    assert not page.exception
    assert any(status in item.value for item in page.warning)
    assert not any(item.label in ['Joint rent change','Changed apartment: fitted median'] for item in page.metric)


def test_contribution_intervals_withheld_and_search_empty(mocked):
    mocked.contribution_ok = False
    page = AppTest.from_file(str(PAGE)).run()
    assert any('Contribution diagnostics failed' in item.value for item in page.warning)
    assert 'Lower 95% CrI (log)' not in page.dataframe[1].value.columns
    widget(page,'text_input','Find advertisement ID or unit URL').set_value('absent').run()
    assert not page.exception
    assert any('No observations match' in item.value for item in page.info)


def test_invalid_selection_stops_without_fallback(mocked, monkeypatch):
    def invalid(path): raise ValueError('Selected main model binding differs')
    monkeypatch.setattr(main_analysis,'load_selection',invalid)
    page = AppTest.from_file(str(PAGE)).run()
    assert not page.exception and page.error
    assert 'could not be verified' in page.error[0].value
    assert len(page.dataframe) == 0 and len(page.metric) == 0


def test_review_warning_is_visible_in_listing_and_scenario(mocked, monkeypatch, tmp_path):
    monkeypatch.setattr(main_analysis, 'load_selection', lambda path: (
        {'source_review': str(tmp_path/'review')}, tmp_path/'experiment', tmp_path/'dataset'))
    monkeypatch.setattr(bayesian_source_review, 'load_source_review', lambda *a, **k: {
        'a': {'kind': 'bedroom_count_conflict', 'message': 'Studio and one-bedroom claims disagree.',
              'interpretation_limited': True}})
    page = AppTest.from_file(str(PAGE)).run()
    assert not page.error and not page.exception
    assert page.dataframe[0].value['Source review'].tolist() == ['bedroom count conflict']
    assert any('Studio and one-bedroom claims disagree' in x.value for x in page.warning)
    assert any('does not resolve the source conflict' in x.value for x in page.warning)
    assert mocked.rows[0]['bedrooms'] == 1


def test_invalid_review_stops_the_page_without_silently_dropping_notes(mocked, monkeypatch, tmp_path):
    monkeypatch.setattr(main_analysis, 'load_selection', lambda path: (
        {'source_review': str(tmp_path/'review')}, tmp_path/'experiment', tmp_path/'dataset'))
    def fail(*args, **kwargs): raise ValueError('Review belongs to another fit')
    monkeypatch.setattr(bayesian_source_review, 'load_source_review', fail)
    page = AppTest.from_file(str(PAGE)).run()
    assert page.error and not page.exception
    assert len(page.metric) == 0


@pytest.mark.skipif(not (ROOT/'config/main-analysis.json').exists(), reason='Accepted local selection unavailable')
def test_actual_accepted_current_cohort_and_joint_counterfactual():
    st.cache_resource.clear()
    selection, experiment, dataset = main_analysis.load_selection()
    rows = [json.loads(line) for line in (dataset/'observations.jsonl').open()]
    candidates = [r for r in rows if r.get('analysis_price_basis')=='current_capture_gross_ask'
                  and r.get('laundry_type') in {'in_building','in_unit'}
                  and r.get('reported_full_bathrooms') is not None and r.get('reported_half_bathrooms') is not None]
    assert candidates
    page = AppTest.from_file(str(PAGE)).run(timeout=120)
    assert not page.exception and not page.error
    count = sum(r.get('analysis_price_basis') == 'current_capture_gross_ask' for r in rows)
    assert any(item.label=='Saved current observations' and item.value==str(count) for item in page.metric)
    assert len(widget(page,'selectbox','Observation to inspect').options)==min(count, 100)
    assert len(page.dataframe[0].value)==min(count, 100)
    target = candidates[0]
    widget(page,'text_input','Find advertisement ID or unit URL').set_value(target['source_listing_id']).run(timeout=60)
    widget(page,'selectbox','Observation to inspect').set_value(target['audit_id']).run(timeout=90)
    widget(page,'multiselect','Features to change together').set_value(['laundry_type']).run(timeout=60)
    new = 'in_unit' if target['laundry_type']=='in_building' else 'in_building'
    widget(page,'selectbox','laundry type').set_value(new)
    widget(page,'button','Compare with recorded apartment').click().run(timeout=90)
    assert not page.exception and not page.error
    assert any(item.label=='Joint rent change' for item in page.metric)
    widget(page,'text_input','Find advertisement ID or unit URL').set_value('').run(timeout=60)
    widget(page,'selectbox','Observation scope').set_value('All fitted observations').run(timeout=60)
    assert not page.exception
    assert len(page.dataframe[0].value)==100
    st.cache_resource.clear()


def test_entry_page_links_through_application_routing():
    page = AppTest.from_file(str(ROOT/'app.py')).switch_page('pages/1_Bayesian_Model.py').run()
    assert not page.exception
    assert len(page.get('page_link')) == 3


def test_historical_source_issue_merges_with_review_and_warns_in_scenario(mocked,monkeypatch,tmp_path):
    from apartments import source_issues
    mocked.rows[0]['analysis_price_basis']='historical_initial_own_advertisement_ask'
    monkeypatch.setattr(main_analysis,'load_selection',lambda path:(
        {'source_review':str(tmp_path/'review'),'source_issues':str(tmp_path/'issues'),'evidence':str(tmp_path/'evidence')},
        tmp_path/'experiment',tmp_path/'dataset'))
    monkeypatch.setattr(bayesian_source_review,'load_source_review',lambda *a,**k:{'a':{
        'kind':'bedroom_count_conflict','message':'Bedroom count remains disputed.','interpretation_limited':True}})
    monkeypatch.setattr(source_issues,'load_source_issues',lambda *a,**k:{'a':{
        'kind':'advertised_price_basis_conflict','message':'Historical headline price is net.',
        'interpretation_limited':True,'issues':[{'id':'price-case'}]}})
    page=AppTest.from_file(str(PAGE)).run()
    assert not page.exception and not page.error
    widget(page,'selectbox','Observation scope').set_value('All fitted observations').run()
    assert not page.exception and not page.error
    assert page.dataframe[0].value['Source review'].ne('').all()
    assert any('Historical headline price is net.' in w.value and 'Bedroom count remains disputed.' in w.value for w in page.warning)
    widget(page,'multiselect','Features to change together').set_value(['bedrooms']).run()
    widget(page,'number_input','bedrooms').set_value(2.)
    widget(page,'button','Compare with recorded apartment').click().run()
    assert not page.exception and not page.error
    assert any('does not resolve the source conflict' in w.value for w in page.warning)
    assert any(m.label=='Changed apartment: fitted median' for m in page.metric)
    assert mocked.rows[0]['bedrooms']==1 and mocked.residuals[0]['asking_rent']==5000.


def test_invalid_source_issues_stop_page_instead_of_hiding_annotations(mocked,monkeypatch,tmp_path):
    from apartments import source_issues
    monkeypatch.setattr(main_analysis,'load_selection',lambda path:(
        {'source_issues':str(tmp_path/'issues'),'evidence':str(tmp_path/'evidence')},tmp_path/'experiment',tmp_path/'dataset'))
    def fail(*a,**k):raise ValueError('Source issues do not match dataset')
    monkeypatch.setattr(source_issues,'load_source_issues',fail)
    page=AppTest.from_file(str(PAGE)).run()
    assert page.error and not page.exception
    assert 'Source issues do not match dataset' in page.error[0].value
    assert len(page.metric)==0


def test_source_issue_cache_uses_evidence_and_reload_clears_it(mocked,monkeypatch,tmp_path):
    from apartments import source_issues
    archive=tmp_path/'evidence';issues=tmp_path/'issues';dataset=tmp_path/'dataset'
    monkeypatch.setattr(main_analysis,'load_selection',lambda path:(
        {'source_issues':str(issues),'evidence':str(archive)},tmp_path/'experiment',dataset))
    calls=[]
    def load(*args,**kwargs):calls.append((args,kwargs));return {}
    monkeypatch.setattr(source_issues,'load_source_issues',load)
    page=AppTest.from_file(str(PAGE)).run()
    assert not page.exception and not page.error
    assert calls==[((str(dataset),str(issues)),{'evidence':str(archive)})]
    widget(page,'selectbox','Maximum rows to review').set_value(500).run()
    assert len(calls)==1
    widget(page,'button','Reload saved analysis').click().run()
    assert not page.exception and not page.error
    assert len(calls)==2
