"""The building level plus a stationary AR(1) deviation (`walk_ar`) in the
Gibbs sampler: the compact solve against a dense one, the bridge fill, the
sites, the rho prior and recovery of (rho, sd, building_scale)."""

import jax

jax.config.update("jax_enable_x64", True)

import jax.numpy as jnp
import numpy as np
import pandas as pd
import pytest
from rentfrontier import gibbs, model
from rentfrontier.features import Features
from scipy.special import betaln
from scipy.stats import beta, multivariate_normal
from test_gibbs import synthetic

AR = model.ModelConfig(building_walk=True, walk_ar=True)
AR_SLOPE = model.ModelConfig(building_walk=True, walk_ar=True, bedroom_slope=True)
SCALES = {
    "sigma": 0.05,
    "unit_scale": 0.08,
    "building_scale": 0.3,
    "trend_scale": 0.02,
    "season_scale": 0.03,
    "walk_scale": 0.06,
    "walk_decay": 0.08,
    "bedroom_slope_scale": 0.06,
}


def ar_cov(k, rho):
    idx = np.arange(k)
    return rho ** np.abs(np.subtract.outer(idx, idx))


def dense_parts(d, s):
    """Design matrix and prior precision over (global, local, units), with
    every walk knot a column and the full AR(1) prior on them."""
    n, p = d.a.shape
    K, L, J = d.n_buildings, d.n_local, d.n_units
    X = np.zeros((n, p + K * L + J))
    X[:, :p] = np.asarray(d.a)
    slots, vals, bld = (np.asarray(v) for v in (d.slots, d.slot_values, d.building))
    for m in range(slots.shape[1]):
        np.add.at(X, (np.arange(n), p + bld * L + slots[:, m]), vals[:, m])
    X[np.arange(n), p + K * L + np.asarray(d.unit)] = 1
    prior = np.zeros((X.shape[1],) * 2)
    prior[:p, :p] = np.diag(np.asarray(d.prior_fixed))
    for name, (sl, r) in d.global_blocks.items():
        prior[sl, sl] += np.asarray(r) / s[name] ** 2
    local = sum(
        np.asarray(d.local_structures[k]) / s[k] ** 2 for k in d.local_structures
    )
    ks = d.knot_start
    rho = np.exp(-s["walk_decay"])
    local[ks:, ks:] += np.linalg.inv(ar_cov(L - ks, rho)) / s["walk_scale"] ** 2
    for k in range(K):
        prior[p + k * L : p + (k + 1) * L, p + k * L : p + (k + 1) * L] = local
    prior[p + K * L :, p + K * L :] += np.eye(J) / s["unit_scale"] ** 2
    return X, prior


def zeros(d):
    return (
        jnp.zeros(d.a.shape[1]),
        jnp.zeros((d.n_buildings, d.n_local)),
        jnp.zeros(d.n_units),
    )


@pytest.mark.parametrize("config", [AR, AR_SLOPE])
def test_compact_ar_solve_matches_dense(config):
    """The posterior mean (untouched knots at their conditional mean) and the
    dependence of the marginal likelihood on (sd, rho, other scales) match a
    dense solve over every knot."""
    prep = synthetic(seed=2, units_per_building=3, months=72)
    d = gibbs.build_design(prep, config)
    assert d.walk_ar and d.buckets and d.walk_rank < d.n_buildings * d.walk_knots
    lam = np.random.default_rng(1).gamma(2.5, 1 / 2.5, d.y.shape[0])
    theta, theta_l, u, *_, ml = gibbs.gaussian_block(
        d, jnp.asarray(lam), SCALES, *zeros(d)
    )
    X, prior = dense_parts(d, SCALES)
    w = lam / SCALES["sigma"] ** 2
    mean = np.linalg.solve(X.T @ (w[:, None] * X) + prior, X.T @ (w * np.asarray(d.y)))
    p, KL = d.a.shape[1], d.n_buildings * d.n_local
    np.testing.assert_allclose(np.asarray(theta), mean[:p], atol=1e-8)
    np.testing.assert_allclose(
        np.asarray(theta_l), mean[p : p + KL].reshape(d.n_buildings, -1), atol=1e-8
    )
    np.testing.assert_allclose(np.asarray(u), mean[p + KL :], atol=1e-8)

    def dense_ml(s):
        X, prior = dense_parts(d, s)
        cov = X @ np.linalg.solve(prior, X.T) + np.diag(s["sigma"] ** 2 / lam)
        return multivariate_normal(np.zeros(len(lam)), cov).logpdf(np.asarray(d.y))

    for change in (
        {"walk_decay": 0.02},
        {"walk_decay": 0.3, "walk_scale": 0.1},
        {"building_scale": 0.2, "walk_scale": 0.03},
    ):
        other = SCALES | change
        ml2 = gibbs.gaussian_block(d, jnp.asarray(lam), other, *zeros(d))[-1]
        np.testing.assert_allclose(
            float(ml - ml2), dense_ml(SCALES) - dense_ml(other), atol=1e-6
        )


def test_filled_knots_have_the_ar_conditional_covariance():
    """fill_ar draws the untouched knots from the AR(1) given the touched
    ones: covariance sd^2 (S_uu - S_ut S_tt^-1 S_tu), S_ij = rho^|i - j|, and
    mean S_ut S_tt^-1 x_t."""
    prep = synthetic(seed=2, units_per_building=3, months=72)
    d = gibbs.build_design(prep, AR)
    k, rho, sd = d.walk_knots, 0.9, 0.07
    touched_all = np.asarray(d.fill["touched"])
    x_t = jnp.asarray(np.random.default_rng(0).normal(0, sd, (d.n_buildings, k)))
    x_t = jnp.where(touched_all, x_t, 0.0)
    mean = np.asarray(gibbs.fill_ar(d, x_t, rho, sd))
    s_all = ar_cov(k, rho)
    checked = 0
    for b in range(d.n_buildings):
        t = np.flatnonzero(touched_all[b])
        f = np.setdiff1d(np.arange(k), t)
        if len(f) == 0 or len(t) == 0:
            continue

        def draw(z, b=b):
            return gibbs.fill_ar(d, jnp.zeros((d.n_buildings, k)), rho, sd, z)[b]

        jac = np.asarray(jax.jacfwd(draw)(jnp.zeros((d.n_buildings, k))))[:, b, :]
        cov = jac @ jac.T
        gain = s_all[np.ix_(f, t)] @ np.linalg.inv(s_all[np.ix_(t, t)])
        expect = s_all[np.ix_(f, f)] - gain @ s_all[np.ix_(t, f)]
        np.testing.assert_allclose(cov[np.ix_(f, f)], sd**2 * expect, atol=1e-12)
        np.testing.assert_allclose(cov[np.ix_(t, t)], 0.0, atol=1e-14)
        np.testing.assert_allclose(mean[b, f], gain @ np.asarray(x_t)[b, t], atol=1e-12)
        np.testing.assert_allclose(mean[b, t], np.asarray(x_t)[b, t], atol=0)
        checked += 1
    assert checked > 5


def test_ar_site_values_reproduce_linear_predictor():
    prep = synthetic()
    d = gibbs.build_design(prep, AR_SLOPE)
    rng = np.random.default_rng(3)
    state = {
        "theta": jnp.asarray(rng.normal(0, 0.1, d.a.shape[1])),
        "local": jnp.asarray(rng.normal(0, 0.1, (d.n_buildings, d.n_local))),
        "unit": jnp.asarray(rng.normal(0, 0.1, d.n_units)),
        "nu": 5.0,
        "kappa": jnp.ones(d.n_units),
        "drift": jnp.zeros(d.n_units),
        **{k: SCALES.get(k, 0.05) for k in d.scale_names},
    }
    p = gibbs.site_values(d, state)
    assert "walk_step" not in p
    np.testing.assert_allclose(float(p["walk_rho"]), np.exp(-SCALES["walk_decay"]))
    mu_model = model.linear_predictor(p, prep.train.map(jnp.asarray))
    mu_gibbs = (
        d.a @ state["theta"]
        + gibbs.local_value(state["local"], d.building, d.slots, d.slot_values)
        + state["unit"][d.unit]
    )
    np.testing.assert_allclose(np.asarray(mu_model), np.asarray(mu_gibbs), atol=1e-10)


def test_walk_decay_prior_is_the_beta_prior_on_rho():
    """exp(scale_log_prior) over log(-log rho) integrates to 1 and puts the
    Beta's mass above 0.99."""
    a, b = model.ModelConfig().walk_rho_prior
    x = np.linspace(-14, 4, 200001)
    log_dens = gibbs.scale_log_prior("walk_decay", jnp.exp(x), (a, b))
    dens = np.exp(np.asarray(log_dens) - betaln(a, b))
    np.testing.assert_allclose(np.trapezoid(dens, x), 1.0, atol=1e-4)
    rho = np.exp(-np.exp(x))
    np.testing.assert_allclose(
        np.trapezoid(np.where(rho > 0.99, dens, 0.0), x), beta(a, b).sf(0.99), atol=1e-3
    )


def simulate_ar(rho, building_sd, sd, seed=0, n_buildings=160, months=120):
    """Rows from a level + AR(1) deviation per building on 6-month knots,
    with units, a trend and Student-t noise."""
    rng = np.random.default_rng(seed)
    k = model.n_knots(months, model.KNOT_MONTHS)
    level = rng.normal(0, building_sd, n_buildings)
    dev = np.asarray(
        model.ar1_path(rng.normal(size=(n_buildings, k)), rho, sd), np.float64
    )
    trend = np.concatenate([[0], np.cumsum(rng.normal(0, 0.01, months - 1))])
    rows = []
    for b in range(n_buildings):
        for j in range(6):
            u_eff = rng.normal(0, 0.08)
            x = rng.integers(0, 2, 2).astype(float)
            for m in rng.integers(0, months, rng.integers(2, 7)):
                lo, fr = divmod(m, model.KNOT_MONTHS)
                fr = fr / model.KNOT_MONTHS
                walk = (1 - fr) * dev[b, lo] + fr * dev[b, min(lo + 1, k - 1)]
                y = 0.1 + x @ [0.2, -0.1] + trend[m] + level[b] + walk + u_eff
                rows.append((b, b * 100 + j, m, *x, y + 0.05 * rng.standard_t(5)))
    frame = pd.DataFrame(rows, columns=["b", "u", "m", "x0", "x1", "y"])
    frame = frame.drop_duplicates(["u", "m"])
    units, unit_idx = np.unique(frame.u, return_inverse=True)
    x = frame[["x0", "x1"]].to_numpy()
    m = frame.m.to_numpy().astype(np.int32)
    arrays = model.Arrays(
        y=frame.y.to_numpy(),
        x=x,
        month=m,
        calendar=m % 12,
        building=frame.b.to_numpy().astype(np.int32),
        unit=unit_idx.astype(np.int32),
        knot=m // model.KNOT_MONTHS,
        knot_frac=(m % model.KNOT_MONTHS) / model.KNOT_MONTHS,
        bed_group=np.ones(len(m), np.int32),
        beds_centered=np.zeros(len(m)),
        unit_time=np.zeros(len(m)),
        noise_cell=np.zeros(len(m), np.int32),
    )
    return model.Prepared(
        features=Features("synthetic", ["x0", "x1"], ["x", "x"], x, np.ones(2)),
        offset=0.0,
        periods=pd.date_range("2014-01-01", periods=months, freq="MS"),
        buildings=np.arange(n_buildings),
        units=units,
        train=arrays,
        test=arrays.map(lambda v: v[:10]),
        test_audit_id=np.arange(10),
    )


def recover(rho, building_sd, sd, seed=0):
    prep = simulate_ar(rho, building_sd, sd, seed=seed)
    out = gibbs.run(
        prep,
        AR,
        gibbs.Settings(chains=4, warmup=600, draws=1200, keep_every=100),
        log=lambda *_: None,
    )
    names = gibbs.collect_module.SCALARS
    tr = np.asarray(out["trace"]["scalars"])  # (chains, iterations, scalars)
    draws = {
        n: tr[:, :, names.index(n)].ravel()
        for n in ("walk_rho", "walk_scale", "building_scale")
    }
    return draws


@pytest.mark.slow
@pytest.mark.parametrize(
    "rho, building_sd, sd",
    [(0.92, 0.144, 0.08), (0.98, 0.144, 0.08), (0.985, 0.05, 0.08)],
)
def test_ar_walk_recovers_rho_sd_and_building_scale(rho, building_sd, sd):
    """Each true value lies inside its posterior 80% interval (one seed per
    case), and the reported building_scale vs walk_scale posterior
    correlation shows how far the two separate."""
    draws = recover(rho, building_sd, sd)
    truth = {"walk_rho": rho, "walk_scale": sd, "building_scale": building_sd}
    for name, value in truth.items():
        lo, hi = np.quantile(draws[name], [0.1, 0.9])
        assert lo < value < hi, (name, lo, hi, value)
    corr = np.corrcoef(draws["building_scale"], draws["walk_scale"])[0, 1]
    print(f"rho={rho} building_sd={building_sd}: corr(building, walk) {corr:.2f}")


def test_new_building_variance_uses_the_stationary_deviation():
    """A new building's AR(1) deviation has variance sd^2 at each knot and
    sd^2 ((1-f)^2 + f^2 + 2 f (1-f) rho) between knots, whatever the month."""
    from rentfrontier import newbuilding

    prep = synthetic(months=72)
    a = prep.train
    assert newbuilding.walk_origin(AR, np.zeros(3)) is None
    kept = {
        "building_scale": np.array([0.1, 0.2]),
        "walk_scale": np.array([0.05, 0.15]),
        "walk_rho": np.array([0.9, 0.99]),
        "alpha": np.zeros(2),
    }
    var = newbuilding.building_variance(
        kept, a, None, np.zeros((len(a.y), 0)), np.zeros(len(a.y)), model.KNOT_MONTHS
    )
    f = np.asarray(a.knot_frac)
    for i in range(2):
        mix = (1 - f) ** 2 + f**2 + 2 * f * (1 - f) * kept["walk_rho"][i]
        expect = kept["building_scale"][i] ** 2 + kept["walk_scale"][i] ** 2 * mix
        np.testing.assert_allclose(var[i], expect, atol=1e-12)
