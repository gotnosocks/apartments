"""rescore's approximate held-out density with one residual scale per bedroom group."""

from types import SimpleNamespace

import jax.numpy as jnp
import numpy as np
from rentfrontier import rescore


def _test_rows():
    rng = np.random.default_rng(0)
    n = 12
    return SimpleNamespace(
        y=jnp.asarray(rng.normal(0, 0.1, n)),
        unit=jnp.asarray(np.where(np.arange(n) % 3 == 0, -1, np.arange(n))),
        unit_time=jnp.asarray(rng.uniform(0, 2, n)),
        bed_group=jnp.asarray(np.arange(n) % 4),
    )


def _params(sigma):
    return {
        "nu": jnp.asarray(5.0),
        "sigma": sigma,
        "unit_scale": jnp.asarray(0.1),
        "unit_drift_scale": jnp.asarray(0.01),
        "unit_nu": jnp.asarray(4.0),
    }


def test_grouped_scales_that_are_equal_match_one_scale():
    test = _test_rows()
    mu, u = jnp.zeros(12), jnp.full(12, 0.02)
    one = rescore._approx_unseen_logpdf(_params(jnp.asarray(0.04)), test, mu, u)
    grouped = rescore._approx_unseen_logpdf(_params(jnp.full(4, 0.04)), test, mu, u)
    np.testing.assert_allclose(np.asarray(grouped), np.asarray(one), rtol=1e-6)


def test_grouped_scales_use_each_rows_group():
    test = _test_rows()
    mu, u = jnp.zeros(12), jnp.full(12, 0.02)
    sigma = jnp.asarray([0.03, 0.035, 0.04, 0.05])
    grouped = rescore._approx_unseen_logpdf(_params(sigma), test, mu, u)
    for g in range(4):
        rows = np.asarray(test.bed_group) == g
        alone = rescore._approx_unseen_logpdf(_params(sigma[g]), test, mu, u)
        np.testing.assert_allclose(
            np.asarray(grouped)[rows], np.asarray(alone)[rows], rtol=1e-6
        )
