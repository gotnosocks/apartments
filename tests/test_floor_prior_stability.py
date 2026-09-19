import numpy as np
import pytest

from models.floor_prior_stability import audit_priors, covariance, contrast_sd


def test_missing_integer_thresholds_marginalize_to_gap_variance():
    levels = [-1, 0, 2, 7]
    matrix = (np.asarray(levels)[:, None] > np.arange(-1, 7)[None, :]).astype(float)
    np.testing.assert_allclose(covariance(levels, .15, 'integer_step'), .15**2*matrix@matrix.T)
    assert contrast_sd(covariance(levels, .15, 'integer_step'), 2, 3) == pytest.approx(.15*np.sqrt(5))


def test_observed_rank_prior_changes_when_an_interior_label_disappears():
    result = audit_priors([8, 9, 10], .15)
    change = result['interior_level_removal'][0]['policies']
    assert change['observed_step']['before_log_sd'] == pytest.approx(.15*np.sqrt(2))
    assert change['observed_step']['after_log_sd'] == .15
    assert change['integer_step']['before_log_sd'] == pytest.approx(change['integer_step']['after_log_sd'])


def test_matched_range_does_not_match_local_increment_priors():
    result = audit_priors([1, 2, 4, 10], .15)
    a, b, c = result['policies']
    assert a['range_log_sd'] == pytest.approx(c['range_log_sd'])
    assert b['range_log_sd'] > c['range_log_sd']
    first = result['contrasts'][0]['prior_log_sd']
    assert first['observed_step'] == first['integer_step']
    assert first['integer_step_matched_range'] < first['observed_step']
    for removal in result['interior_level_removal']:
        assert removal['policies']['integer_step_matched_range']['relative_sd_change'] == pytest.approx(0)


def test_prior_contrasts_are_translation_invariant_without_claiming_physical_height():
    np.testing.assert_array_equal(covariance([-2, 0, 4], .1, 'integer_step'),
                                  covariance([8, 10, 14], .1, 'integer_step'))


@pytest.mark.parametrize('levels,scale,policy', [([1], .15, 'integer_step'), ([2, 1], .15, 'integer_step'),
    ([1, 1, 2], .15, 'integer_step'), ([1, np.nan], .15, 'observed_step'),
    ([1, 2.5], .15, 'integer_step'), ([1, 2], 0, 'integer_step'), ([1, 2], -.1, 'integer_step'),
    ([1, 2], np.inf, 'integer_step'), ([1, 2], True, 'integer_step'), ([1, 2], .15, 'unreviewed')])
def test_unsupported_or_invalid_prior_inputs_fail(levels, scale, policy):
    with pytest.raises(ValueError): covariance(levels, scale, policy)
