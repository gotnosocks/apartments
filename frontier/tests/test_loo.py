import itertools
import math

import numpy as np
import pytest
from rentfrontier import loo
from scipy import integrate, stats

jax = pytest.importorskip("jax")
jax.config.update("jax_enable_x64", True)


def toy_units(rng, n_units=25):
    sizes = rng.integers(1, 5, n_units)
    unit = np.repeat(np.arange(n_units), sizes)
    return unit, sizes


def test_integrated_psis_loo_matches_exact_loo_on_a_conjugate_model():
    """y_ij = m + a_j + e_ij with Gaussian a and e: exact LOO is analytic."""
    rng = np.random.default_rng(0)
    tau, sigma, prior_sd = 0.1, 0.05, 1.0
    unit, _ = toy_units(rng)
    n = len(unit)
    y = 0.3 + rng.normal(0, tau, unit.max() + 1)[unit] + rng.normal(0, sigma, n)
    same = unit[:, None] == unit[None, :]
    cov_given_m = sigma**2 * np.eye(n) + tau**2 * same
    # Exact LOO: p(y_i | y_-i) under the joint with m integrated out.
    joint = cov_given_m + prior_sd**2
    prec = np.linalg.inv(joint)
    exact = stats.norm.logpdf(
        y, y - (prec @ y) / np.diag(prec), np.sqrt(1 / np.diag(prec))
    )
    # Exact posterior draws of m, then the integrated density per draw.
    inv = np.linalg.inv(cov_given_m)
    post_var = 1 / (1 / prior_sd**2 + inv.sum())
    post_mean = post_var * (inv @ y).sum()
    draws = 4000
    m = rng.normal(post_mean, math.sqrt(post_var), draws)
    params = {
        "nu": np.full(draws, 1e8),  # Student-t with huge nu: Gaussian noise
        "sigma": np.full(draws, sigma),
        "unit_scale": np.full(draws, tau),
    }
    ll = loo.integrated_loglik(
        y,
        np.broadcast_to(m[:, None], (draws, n)),
        unit,
        unit.max() + 1,
        np.zeros(n),
        params,
        t_units=False,
        drift=False,
    )
    elpd, k, _ = loo.psis_loo(np.asarray(ll))
    assert np.all(k < 0.5)
    np.testing.assert_allclose(elpd, exact, atol=5e-3)
    assert abs(elpd.sum() - exact.sum()) < 0.05


def test_integrated_density_matches_adaptive_quadrature_with_t_units_and_drift():
    """One unit of three rows: t-level prior, normal drift, t noise."""
    y = np.array([0.08, 0.02, 0.11])
    t = np.array([-1.0, 0.0, 1.0])
    mu = np.array([0.0, 0.01, -0.02])
    p = {
        "nu": 3.0,
        "sigma": 0.05,
        "unit_scale": 0.1,
        "unit_nu": 4.0,
        "unit_drift_scale": 0.03,
    }

    def lik(rows, a, s):
        r = y[rows] - mu[rows] - a - s * t[rows]
        return np.prod(stats.t.pdf(r / p["sigma"], p["nu"]) / p["sigma"])

    def marginal(rows):
        def f(s, a):
            return (
                lik(rows, a, s)
                * stats.t.pdf(a / p["unit_scale"], p["unit_nu"])
                / p["unit_scale"]
                * stats.norm.pdf(s, 0, p["unit_drift_scale"])
            )

        return integrate.dblquad(f, -1.5, 1.5, -0.3, 0.3, epsabs=1e-12)[0]

    expected = [
        math.log(marginal([0, 1, 2]) / marginal([j for j in range(3) if j != i]))
        for i in range(3)
    ]
    params = {k: np.array([v]) for k, v in p.items()}
    got = loo.integrated_loglik(
        y, mu[None], np.zeros(3, int), 1, t, params, t_units=True, drift=True
    )
    np.testing.assert_allclose(np.asarray(got)[0], expected, atol=5e-3)


def test_unit_chunks_keep_units_whole():
    units = np.repeat(np.arange(10), [3, 1, 4, 2, 2, 5, 1, 1, 3, 2])
    chunks = loo.unit_chunks(units, size=6)
    assert chunks[0][0] == 0 and chunks[-1][1] == len(units)
    for (lo, hi), (lo2, _) in itertools.pairwise(chunks):
        assert hi == lo2
    for lo, hi in chunks:
        assert hi - lo <= 6
        assert lo == 0 or units[lo] != units[lo - 1]
    with pytest.raises(ValueError):
        loo.unit_chunks(np.zeros(8, int), size=6)


def test_k_threshold():
    assert loo.k_threshold(320) == pytest.approx(1 - 1 / math.log10(320))
    assert loo.k_threshold(100_000) == 0.7


def test_single_listing_unit_with_heavy_tailed_prior_matches_full_integral():
    """unit_nu = 2 puts ~6e-4 of the prior beyond the grid; it must not be
    redistributed onto the grid (it was, before the fix: ~+6e-4 per row)."""
    p = {"nu": 2.5, "sigma": 0.05, "unit_scale": 0.1, "unit_nu": 2.0}
    y = np.array([0.07])

    def f(a):
        return (
            stats.t.pdf((y[0] - a) / p["sigma"], p["nu"])
            / p["sigma"]
            * stats.t.pdf(a / p["unit_scale"], p["unit_nu"])
            / p["unit_scale"]
        )

    mass = (
        integrate.quad(f, -np.inf, -1.0, limit=500)[0]
        + integrate.quad(f, -1.0, 1.0, points=[0.0, 0.07], limit=500)[0]
        + integrate.quad(f, 1.0, np.inf, limit=500)[0]
    )
    expected = math.log(mass)
    params = {k: np.array([v]) for k, v in p.items()}
    got = loo.integrated_loglik(
        y,
        np.zeros((1, 1)),
        np.zeros(1, int),
        1,
        np.zeros(1),
        params,
        t_units=True,
        drift=False,
    )
    assert abs(float(np.asarray(got)[0, 0]) - expected) < 1e-4
