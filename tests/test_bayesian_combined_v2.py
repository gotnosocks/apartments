"""Combined v2 (last code-hash protocol): reader terms and leave-own-row-out fits."""

import numpy as np
import pandas as pd
from scipy import stats

from models import bayesian_location_terms_v2 as terms
from models.bayesian_combined_experiment import loo_quantiles


def test_loo_quantiles_match_exact_leave_one_out_for_a_normal_mean():
    rng = np.random.default_rng(0)
    n, draws = 20, 20000
    y = rng.normal(0, 1, n)
    y[0] = 4.0
    posterior = rng.normal(y.mean(), 1 / np.sqrt(n), draws)
    mu = np.repeat(posterior[:, None], n, 1)
    quantiles, pareto_k = loo_quantiles(mu, stats.norm.logpdf(y[None], mu, 1))
    for row in (0, 1):
        rest = np.delete(y, row)
        assert abs(quantiles[1, row] - rest.mean()) < 0.02
        exact = rest.mean() + np.array([-1.96, 1.96]) / np.sqrt(n - 1)
        assert np.allclose(quantiles[[0, 2], row], exact, atol=0.03)
    assert pareto_k[0] < 0.7
    # The outlying row's own estimate moves away from its ask when left out.
    assert quantiles[1, 0] < np.median(posterior)


def test_centered_walk_matches_graph_centering():
    rng = np.random.default_rng(1)
    samples, buildings, knots = 50, 4, 5
    z = rng.normal(size=(buildings, knots, samples))
    scale = rng.uniform(0.02, 0.1, samples)
    years = 0.5
    rows = np.array([10, 30, 5, 55])
    share = rows / rows.sum()
    levels = scale[None, None] * np.sqrt(years) * np.cumsum(z, axis=1)
    common = np.einsum("bks,b->ks", levels, share)
    centered = levels - common[None]
    basis = rng.uniform(size=(3, knots))
    centers = rng.dirichlet(np.ones(knots), size=buildings)
    for b in range(buildings):
        expected = (
            np.einsum("ks,rk->sr", centered[b], basis)
            - (np.einsum("ks,k->s", centered[b], centers[b])[:, None])
        )
        actual = terms.centered_building_walk(
            z[b].T, scale, years, basis, centers[b], common.T
        )
        assert np.allclose(actual, expected, rtol=1e-12, atol=1e-14)


def test_bedroom_step_caps_at_four_bedrooms():
    steps = terms.bedroom_step(pd.Series([0, 1, 2, 4, 6]))
    assert steps.tolist() == [-1.0, 0.0, 1.0, 3.0, 3.0]


def test_combined_v2_is_a_drift_version_with_slope_and_walk_variables():
    protocol = {"version": terms.COMBINED_V2_EXPERIMENT}
    assert terms.COMBINED_V2_EXPERIMENT in terms.DRIFT_VERSIONS
    whole = terms.variable_dims(protocol)
    lazy = terms.lazy_variable_dims(protocol)
    assert whole["citywide_walk"] == ("period",)
    assert whole["building_walk_common"] == ("building_walk_knot",)
    assert lazy["building_bedroom_slope_z"] == ("building",)
    assert lazy["building_feature_slope_z"] == ("building_slope",)
