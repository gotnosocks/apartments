from copy import deepcopy
import json

import pytest
from typer.testing import CliRunner

from apartments.bayesian_candidate_search import rank_current


def row(identity, rent, bedrooms=1, **fields):
    return {'audit_id': identity, 'unit_id': identity, 'source_listing_id': identity,
        'building': 'b', 'building_id': 'b', 'source': 'streeteasy',
        'rent': rent, 'asking_rent': rent, 'bedrooms': bedrooms, 'elevator': True,
        'laundry_type': 'in_unit', 'analysis_price_basis': 'current_capture_gross_ask',
        'collected_at': '2026-09-18T12:00:00Z', 'known_at': '2026-09-18T13:00:00Z',
        'listing_status': 'ACTIVE', 'price_basis': 'gross_advertised_rent', 'capture_id': identity,
        **fields}


class Analysis:
    def __init__(self, rows, shift=0., acceptable=True):
        self._rows, self.shift, self.acceptable = deepcopy(rows), shift, acceptable
        self.calls = []

    @property
    def rows(self): return deepcopy(self._rows)

    def detail(self, audit_id):
        self.calls.append(audit_id)
        r = next(r for r in self._rows if r['audit_id'] == audit_id)
        price = r['rent']+self.shift
        return {'source_record': deepcopy(r), 'residual': {
            **{k: r[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'building', 'asking_rent')},
            'residual_dollars': -self.shift, 'residual_log': 0.},
            'fitted_median_rent': {'lower_95': price-100, 'median': price, 'upper_95': price+100},
            'contribution_diagnostics': {'acceptable': self.acceptable}, 'draws': 24000, 'warnings': []}


def rank(analysis, weights=None, **kwargs):
    return rank_current(analysis, {'bedrooms': 600} if weights is None else weights,
                        as_of='2026-09-19T00:00:00Z', **kwargs)


def signature(results):
    return [(r['record']['audit_id'], r['monthly_surplus'], r['pareto_efficient']) for r in results]


def test_frontier_and_utility_are_independent_of_posterior_prices_uncertainty_and_gates():
    rows = [row('a', 2500, 0), row('b', 3000, 1), row('c', 3500, 1)]
    baseline, _, summary = rank(Analysis(rows))
    shifted, _, _ = rank(Analysis(rows, 3000))
    failed, _, _ = rank(Analysis(rows, acceptable=False))
    assert signature(baseline) == signature(shifted) == signature(failed)
    assert {r['record']['audit_id'] for r in baseline if r['pareto_efficient']} == {'a', 'b'}
    assert summary['frontier_units'] == 2
    assert all(r['market_comparison']['latent_median_rent'] is None for r in failed)
    assert all(r['market_comparison']['same_observation_in_fit'] for r in shifted)


def test_current_freshness_budget_and_status_filter_before_any_posterior_request():
    analysis = Analysis([row('active', 3000), row('historical', 2000, analysis_price_basis='historical_initial_own_advertisement_ask'),
        row('rented', 1000, listing_status='RENTED'), row('stale', 1800, collected_at='2026-08-01T00:00:00Z'),
        row('expensive', 7000), row('future', 1500, known_at='2026-09-20T00:00:00Z')])
    ranked, excluded, summary = rank(analysis, budget=4000)
    assert [r['record']['audit_id'] for r in ranked] == ['active']
    assert analysis.calls == ['active']
    assert summary['fitted_current_observations'] == 5
    assert {r['reason'] for r in excluded} == {'latest_capture_not_confirmed_active', 'stale_capture', 'over_budget', 'not_known_at_cutoff'}


def test_review_conflicts_mask_only_preferences_without_rewriting_source():
    original = row('a', 3000)
    analysis = Analysis([original])
    note = {'kind': 'bedroom_count_conflict', 'message': 'Own description disagrees.', 'interpretation_limited': True}
    results, _, summary = rank(analysis, source_notes={'a': note})
    value = results[0]
    assert value['record'] == original and analysis.rows == [original]
    assert value['preference_attribute_withholding'] == {'bedrooms': 1}
    assert not value['eligible'] and not value['pareto_efficient']
    assert value['unknown_preferences'] == ['bedrooms']
    assert value['market_comparison']['status'] == 'source_review_required'
    assert value['market_comparison']['latent_median_rent'] is None
    assert summary['source_review_withheld_units'] == 1
    # An unrelated preference stays usable, with the source review visible.
    other, _, _ = rank(analysis, {'elevator': 100}, source_notes={'a': note})
    assert other[0]['eligible'] and other[0]['market_comparison']['source_review'] == note


def test_unknown_negative_preference_is_excluded_unless_zero_explicitly_requested():
    analysis = Analysis([row('a', 3000, bedrooms=None)])
    result, _, _ = rank(analysis, {'bedrooms': -100})
    assert not result[0]['eligible']
    result, _, _ = rank(analysis, {'bedrooms': -100}, unknown_policy='zero')
    assert result[0]['eligible'] and result[0]['monthly_surplus'] == -3000
    assert result[0]['unknown_preferences'] == ['bedrooms']


def test_fitted_candidate_mismatch_and_unknown_preference_keys_fail():
    analysis = Analysis([row('a', 3000, asking_rent=3001)])
    with pytest.raises(ValueError, match='fitted observation'): rank(analysis)
    with pytest.raises(ValueError, match='Unknown'): rank(Analysis([]), {'bedroms': 500})
    with pytest.raises(ValueError, match='Duplicate'): rank(Analysis([row('a', 1), row('a', 2)]))


def test_unscoped_source_conflict_is_not_silently_treated_as_known():
    analysis = Analysis([row('a', 3000)])
    result, excluded, summary = rank(analysis, source_notes={'a': {'kind': 'new_conflict', 'interpretation_limited': True}})
    assert result == [] and analysis.calls == []
    assert excluded[0]['reason'] == 'unscoped_source_review_required'
    assert summary['exclusion_counts'] == {'unscoped_source_review_required': 1}


def test_merging_compatible_ads_cannot_hide_another_ads_source_conflict():
    analysis = Analysis([row('a', 3000, unit_id='same'), row('z', 3000, unit_id='same')])
    note = {'kind': 'bedroom_count_conflict', 'interpretation_limited': True}
    result, excluded, summary = rank(analysis, source_notes={'a': note})
    assert result == [] and analysis.calls == []
    assert excluded[0]['reason'] == 'merged_advertisement_source_review_required'
    assert excluded[0]['source_review_audit_ids'] == ['a']
    assert summary['compatible_active_advertisements_merged'] == 1


def test_cli_routes_to_selected_bayesian_ranking_without_legacy_fallback(monkeypatch):
    from apartments import bayesian_candidate_search, candidate_search, main_analysis
    from apartments.cli import app
    calls = []
    def run(*args, **kwargs): calls.append((args, kwargs)); return {'frontier_units': 2}
    monkeypatch.setattr(bayesian_candidate_search, 'run', run)
    monkeypatch.setattr(candidate_search, 'score_candidates', lambda *a, **k: pytest.fail('No legacy model fallback'))
    result = CliRunner().invoke(app, ['rank-current-apartments', 'prefs.json', 'out', '--as-of', '2026-09-19', '--budget', '6000'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)['frontier_units'] == 2
    assert calls[0][1]['selection'] == main_analysis.DEFAULT_SELECTION
    assert calls[0][1]['budget'] == 6000
    def fail(*a, **k): raise ValueError('Posterior does not match source')
    monkeypatch.setattr(bayesian_candidate_search, 'run', fail)
    result = CliRunner().invoke(app, ['rank-current-apartments', 'prefs.json', 'out', '--as-of', '2026-09-19'])
    assert result.exit_code == 1 and 'Posterior does not match source' in result.output
