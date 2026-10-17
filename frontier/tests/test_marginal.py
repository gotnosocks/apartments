import jax

jax.config.update("jax_enable_x64", True)

import jax.numpy as jnp
import numpy as np
import pytest
from rentfrontier import gibbs, marginal
from scipy.stats import multivariate_normal
from test_gibbs import DESIGNS, SCALES, synthetic, with_lines

# Compact designs with the anchored walk, from the plain walk up to the
# served model's terms (per-group noise by bedrooms and year, Student-t units,
# feature slopes, the daily Fourier season, masked slopes and walks).
COVERED = [
    "walk",
    "all",
    "fslopes",
    "tunits",
    "yearnoise",
    "dayfourier",
    "bednoise-fourier",
    "quarterly",
    "slopemin",
    "walkmin",
]


def scales(d):
    """SCALES plus a distinct sd per noise group."""
    out = {k: SCALES.get(k, 0.05) for k in d.scale_names}
    for i, n in enumerate(d.group_noise_names if d.noise_group is not None else ()):
        out[n] = 0.04 + 0.004 * i
    return out


def draws(d, seed=1):
    """Global coefficients and the row and unit weights, at random."""
    rng = np.random.default_rng(seed)
    g = jnp.asarray(rng.normal(0, 0.1, d.n_global))
    lam = jnp.asarray(rng.gamma(2.5, 1 / 2.5, d.y.shape[0]))
    kappa = jnp.asarray(rng.gamma(2.0, 1 / 2.0, d.n_units))
    return g, lam, kappa


def dense_local(d, s, kappa):
    """The full local design Z (rows, K L + J): building blocks in the full
    layout, then units, with its prior precision."""
    n = d.y.shape[0]
    K, L, J = d.n_buildings, d.n_local, d.n_units
    z = np.zeros((n, K * L + J))
    slots, vals, bld = (np.asarray(v) for v in (d.slots, d.slot_values, d.building))
    for m in range(slots.shape[1]):
        np.add.at(z, (np.arange(n), bld * L + slots[:, m]), vals[:, m])
    z[np.arange(n), K * L + np.asarray(d.unit)] = 1
    local = sum(
        np.asarray(d.local_structures[k]) / s[k] ** 2 for k in d.local_structures
    )
    prior = np.zeros((K * L + J,) * 2)
    for k in range(K):
        prior[k * L : (k + 1) * L, k * L : (k + 1) * L] = local
    prior[K * L :, K * L :] = np.diag(np.asarray(kappa) / s["unit_scale"] ** 2)
    return z, prior


def dense_log_marginal(d, g, s, lam, kappa):
    """log N(y; a g, W^-1 + Z P^-1 Z'), by brute force."""
    z, prior = dense_local(d, s, kappa)
    w = np.asarray(marginal.row_weights(d, s, lam))
    cov = z @ np.linalg.solve(prior, z.T) + np.diag(1 / w)
    mean = np.asarray(gibbs.global_value(d, g))
    return multivariate_normal(mean, cov).logpdf(np.asarray(d.y))


@pytest.mark.parametrize("design", COVERED)
def test_marginal_matches_the_dense_normal(design):
    """About 2,000 rows (80 buildings): the folded marginal equals the dense
    multivariate normal to a relative error under 1e-10."""
    d = gibbs.build_design(synthetic(n_buildings=80), DESIGNS[design])
    s = scales(d)
    g, lam, kappa = draws(d)
    got = float(marginal.log_marginal(d, g, s, lam, kappa))
    want = dense_log_marginal(d, g, s, lam, kappa)
    assert abs(got - want) < 1e-10 * abs(want)


def test_marginal_rejects_designs_it_does_not_cover():
    prep = synthetic()
    for name in ("base", "drift", "lines"):
        data = with_lines(prep) if name == "lines" else prep
        d = gibbs.build_design(data, DESIGNS[name])
        with pytest.raises(ValueError):
            marginal.log_marginal(d, *draws(d)[:1], scales(d), *draws(d)[1:])


@pytest.mark.parametrize("design", ["yearnoise", "walkmin"])
def test_target_gradients_match_central_differences(design):
    """Directional derivatives of `log_target` in g and the log scales."""
    d = gibbs.build_design(synthetic(), DESIGNS[design])
    s = scales(d)
    g, lam, kappa = draws(d)
    names = list(d.scale_names)
    x0 = jnp.concatenate([g, jnp.log(jnp.asarray([s[k] for k in names]))])
    p = d.n_global

    def f(x):
        log_s = {k: x[p + i] for i, k in enumerate(names)}
        return marginal.log_target(d, x[:p], log_s, lam, kappa)

    grad = jax.grad(f)(x0)
    rng = np.random.default_rng(4)
    eps = 1e-5
    for _ in range(5):
        v = jnp.asarray(rng.normal(size=x0.shape[0]))
        fd = (f(x0 + eps * v) - f(x0 - eps * v)) / (2 * eps)
        assert abs(float(fd - grad @ v)) < 1e-6 * abs(float(fd))


@pytest.mark.parametrize("design", ["all", "tunits", "yearnoise", "walkmin"])
def test_global_mean_matches_the_gibbs_block(design):
    """With the locals integrated out, log p(y, g | ...) is quadratic in g.
    One Newton step from any g lands on the Gibbs block's conditional mean
    of the global coefficients (`gibbs.gaussian_block` with zero noise)."""
    d = gibbs.build_design(synthetic(), DESIGNS[design])
    s = scales(d)
    g0, lam, kappa = draws(d)

    def f(g):
        return marginal.log_marginal(d, g, s, lam, kappa) + marginal.log_global_prior(
            d, g, s
        )

    step = jnp.linalg.solve(jax.hessian(f)(g0), jax.grad(f)(g0))
    zeros = (
        jnp.zeros(d.n_global),
        jnp.zeros((d.n_buildings, d.n_local)),
        jnp.zeros(d.n_units),
    )
    theta = gibbs.gaussian_block(d, lam, s, *zeros, kappa=kappa)[0]
    np.testing.assert_allclose(np.asarray(g0 - step), np.asarray(theta), atol=1e-8)


@pytest.mark.parametrize("design", ["tunits", "yearnoise", "walkmin"])
def test_local_draws_have_the_dense_conditional(design):
    """The draws are affine in the standard normals: at zero they give the
    dense conditional mean of (building blocks, units) given g, and their
    Jacobian M gives its covariance M M'."""
    d = gibbs.build_design(synthetic(), DESIGNS[design])
    s = scales(d)
    g, lam, kappa = draws(d)
    K, L, J, k = d.n_buildings, d.n_local, d.n_units, d.n_fill

    def draw(zz):
        z_l = zz[: K * L].reshape(K, L)
        z_u = zz[K * L : K * L + J]
        z_f = zz[K * L + J :].reshape(K, k)
        theta_l, u = marginal.draw_locals(d, g, s, lam, kappa, z_l, z_u, z_f)
        return jnp.concatenate([theta_l.ravel(), u])

    zero = jnp.zeros(K * L + J + K * k)
    mean = draw(zero)
    jac = jax.jacfwd(draw)(zero)

    z, prior = dense_local(d, s, kappa)
    w = np.asarray(marginal.row_weights(d, s, lam))
    r = np.asarray(d.y - gibbs.global_value(d, g))
    prec = z.T @ (w[:, None] * z) + prior
    np.testing.assert_allclose(
        np.asarray(mean), np.linalg.solve(prec, z.T @ (w * r)), atol=1e-9
    )
    np.testing.assert_allclose(
        np.asarray(jac @ jac.T), np.linalg.inv(prec), rtol=1e-7, atol=1e-10
    )
