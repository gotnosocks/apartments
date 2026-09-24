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
    periods = pd.date_range("2010-03-01", "2012-06-01", freq="MS")
    basis, knots, labels = graph.knot_matrix(periods)
    assert labels == ["2010-03", "2011-01", "2012-01", "2012-06"]
    assert basis.shape == (len(periods), 4)
    np.testing.assert_allclose(basis.sum(1), 1.0)
    np.testing.assert_allclose(basis[knots.astype(int)], np.eye(4))
    # Piecewise-linear: a linear function of knot position is reproduced exactly.
    np.testing.assert_allclose(basis @ knots, np.arange(len(periods)))


def test_curve_identification_is_zero_sum_and_group_centered():
    rng = np.random.default_rng(0)
    periods, groups = 30, len(graph.GROUP_LABELS)
    raw = rng.normal(size=(groups, periods))
    counts = rng.integers(0, 5, size=(groups, periods)).astype(float)
    weights = counts / counts.sum(1, keepdims=True)
    # Same arithmetic as build_model, in numpy.
    centered = raw - raw.mean(0, keepdims=True)
    curve = centered - (centered * weights).sum(1, keepdims=True)
    np.testing.assert_allclose((curve * weights).sum(1), 0.0, atol=1e-12)
    # Differences between groups over time are what the curve carries.
    np.testing.assert_allclose(np.diff(curve, axis=1), np.diff(centered, axis=1))


def test_reader_location_terms_match_graph_groups_and_skip_other_versions():
    from models import bayesian_location_terms as terms
    from models import bayesian_floor_spline_contract as contract

    assert terms.BEDROOM_GROUPS == graph.GROUP_LABELS
    assert terms.BEDROOM_TIME_EXPERIMENT == contract.BEDROOM_TIME_EXPERIMENT
    assert terms.BEDROOM_TIME_EXPERIMENT in contract.FAMILY
    assert [terms.bedroom_group(b) for b in (0, 1, 2, 3, 5)] == [0, 1, 2, 3, 3]
    assert terms.variable_dims({"version": contract.EXPERIMENT}) == {}
    assert (
        terms.row_terms({"version": contract.EXPERIMENT}, {}, pd.DataFrame(), None)
        == {}
    )


def test_reader_location_term_indexes_group_and_period():
    from models import bayesian_location_terms as terms

    class Time:
        periods = pd.date_range("2020-01-01", periods=3, freq="MS")

        def arrays(self, frame):
            return {"period": self.periods.get_indexer(pd.DatetimeIndex(frame.period))}

    class Design:
        time = Time()

    draws = {"bedroom_time": np.arange(2 * 4 * 3, dtype=float).reshape(2, 4, 3)}
    frame = pd.DataFrame({"bedrooms": [4], "period": [pd.Timestamp("2020-02-01")]})
    result = terms.row_terms(
        {"version": terms.BEDROOM_TIME_EXPERIMENT}, draws, frame, Design()
    )
    np.testing.assert_array_equal(
        result["bedroom_time"], draws["bedroom_time"][:, 3, 1]
    )
