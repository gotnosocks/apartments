from copy import deepcopy
import pytest
from models.source_movement_review import compare_details


def detail():
    return {'audit_id': 'a', 'source_record': {'asking_rent': 5000, 'source_listing_id': 'ad', 'unit_id': 'u', 'building': 'b'},
        'mean_log_rent': 8.5,
        'contributions': [{'term': 'intercept', 'mean_log_contribution': 8.}, {'term': 'building', 'mean_log_contribution': .5}],
        'grouped_contributions': {'intercept': 8., 'building': .5},
        'fitted_median_rent': {'median': 4900, 'lower_95': 4500, 'upper_95': 5300},
        'contribution_diagnostics': {'acceptable': True}}


def test_decomposition_uses_additive_mean_log_changes_without_pairing_draws():
    a = detail(); b = deepcopy(a)
    b['mean_log_rent'] = 8.6; b['contributions'][1]['mean_log_contribution'] = .6
    b['grouped_contributions']['building'] = .6
    r = compare_details(a, b)
    assert r['mean_log_rent_change'] == pytest.approx(.1)
    assert r['term_changes'][0]['term'] == 'building'
    assert r['reference_fitted_interval'] == r['candidate_fitted_interval']


@pytest.mark.parametrize('damage', ['identity', 'target', 'sum', 'terms'])
def test_invalid_comparisons_fail(damage):
    a = detail(); b = deepcopy(a)
    if damage == 'identity': b['audit_id'] = 'different'
    if damage == 'target': b['source_record']['asking_rent'] = 6000
    if damage == 'sum': b['mean_log_rent'] = 9
    if damage == 'terms': b['contributions'][1]['term'] = 'unit'
    with pytest.raises(ValueError): compare_details(a, b)
