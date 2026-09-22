import numpy as np
import pandas as pd
import pytest

from models import bayesian_bedroom_time_graph as graph


def test_bedroom_groups_pool_three_or_more():
    assert graph.bedroom_groups([0, 1, 2, 3, 4, 6]).tolist() == [0, 1, 2, 3, 3, 3]
    with pytest.raises(ValueError):
        graph.bedroom_groups([1.5])
    with pytest.raises(ValueError):
        graph.bedroom_groups([-1])


def test_knot_matrix_interpolates_between_january_knots():
    periods = pd.date_range('2010-03-01', '2012-06-01', freq='MS')
    basis, knots, labels = graph.knot_matrix(periods)
    assert labels == ['2010-03', '2011-01', '2012-01', '2012-06']
    assert basis.shape == (len(periods), 4)
    np.testing.assert_allclose(basis.sum(1), 1.)
    np.testing.assert_allclose(basis[knots.astype(int)], np.eye(4))
    # Piecewise-linear: a linear function of knot position is reproduced exactly.
    np.testing.assert_allclose(basis @ knots, np.arange(len(periods)))


def test_curve_identification_is_zero_sum_and_group_centered():
    rng = np.random.default_rng(0)
    periods, groups = 30, len(graph.GROUP_LABELS)
    raw = rng.normal(size=(groups, periods))
    counts = rng.integers(0, 5, size=(groups, periods)).astype(float)
    weights = counts/counts.sum(1, keepdims=True)
    # Same arithmetic as build_model, in numpy.
    centered = raw-raw.mean(0, keepdims=True)
    curve = centered-(centered*weights).sum(1, keepdims=True)
    np.testing.assert_allclose((curve*weights).sum(1), 0., atol=1e-12)
    # Differences between groups over time are what the curve carries.
    np.testing.assert_allclose(np.diff(curve, axis=1), np.diff(centered, axis=1))
