import dataclasses

import jax

jax.config.update("jax_enable_x64", True)

import jax.numpy as jnp
import numpy as np
import pandas as pd
import pytest
from rentfrontier import collect, gibbs, model
from rentfrontier.features import Features


def synthetic(seed=0, n_buildings=15, units_per_building=8, months=24):
    """A small dataset drawn from the model itself."""
    rng = np.random.default_rng(seed)
    beta = np.array([0.2, -0.1])
    b_eff = rng.normal(0, 0.3, n_buildings)
    trend = np.concatenate([[0], np.cumsum(rng.normal(0, 0.02, months - 1))])
    season = rng.normal(0, 0.03, 12)
    rows = []
    for b in range(n_buildings):
        for j in range(units_per_building):
            u_eff = rng.normal(0, 0.08)
            x = rng.integers(0, 2, 2).astype(float)
            beds = int(rng.integers(0, 4))
            for _ in range(rng.integers(1, 5)):
                m = rng.integers(0, months)
                cal = m % 12
                y = (
                    0.1
                    + x @ beta
                    + trend[m]
                    + season[cal]
                    - season.mean()
                    + b_eff[b]
                    + u_eff
                )
                y = y + 0.1 * (beds - 1)
                rows.append(
                    (b, b * 100 + j, m, cal, beds, *x, y + 0.05 * rng.standard_t(5))
                )
    frame = pd.DataFrame(
        rows, columns=["b", "u", "m", "cal", "beds", "x0", "x1", "y"]
    ).drop_duplicates(["u", "m"])
    units, unit_idx = np.unique(frame.u, return_inverse=True)
    x = frame[["x0", "x1"]].to_numpy()
    arrays = model.Arrays(
        y=frame.y.to_numpy(),
        x=x,
        month=frame.m.to_numpy().astype(np.int32),
        calendar=frame.cal.to_numpy().astype(np.int32),
        building=frame.b.to_numpy().astype(np.int32),
        unit=unit_idx.astype(np.int32),
        knot=(frame.m.to_numpy() // model.KNOT_MONTHS).astype(np.int32),
        knot_frac=(frame.m.to_numpy() % model.KNOT_MONTHS) / model.KNOT_MONTHS,
        bed_group=frame.beds.to_numpy().astype(np.int32),
        beds_centered=frame.beds.to_numpy() - 1.0,
        unit_time=(
            (frame.m - frame.groupby("u").m.transform("mean")) / 12.0
        ).to_numpy(),
    )
    feats = Features("synthetic", ["x0", "x1"], ["x", "x"], x, np.ones(2))
    return model.Prepared(
        features=feats,
        offset=0.0,
        periods=pd.date_range("2020-01-01", periods=months, freq="MS"),
        buildings=np.arange(n_buildings),
        units=units,
        train=arrays,
        test=arrays.map(lambda v: v[:10]),
        test_audit_id=np.arange(10),
    )


DESIGNS = {
    "base": model.ModelConfig(),
    "walk": model.ModelConfig(building_walk=True),
    "bedtime-slope": model.ModelConfig(bedroom_time=True, bedroom_slope=True),
    "all": model.ModelConfig(building_walk=True, bedroom_time=True, bedroom_slope=True),
    "fslopes": model.ModelConfig(
        building_walk=True,
        bedroom_slope=True,
        feature_slopes=("x0", "x1"),
    ),
    "tunits": model.ModelConfig(
        building_walk=True,
        bedroom_slope=True,
        feature_slopes=("x0",),
        unit_t=True,
    ),
    "drift": model.ModelConfig(building_walk=True, unit_drift=True),
    "tdrift": model.ModelConfig(
        building_walk=True,
        bedroom_slope=True,
        unit_t=True,
        unit_drift=True,
    ),
    "quarterly": model.ModelConfig(
        building_walk=True,
        bedroom_time=True,
        bedroom_slope=True,
        trend_knot_months=3,
        bedroom_time_knot_months=3,
    ),
}
SCALES = {
    "sigma": 0.05,
    "unit_scale": 0.08,
    "building_scale": 0.3,
    "trend_scale": 0.02,
    "season_scale": 0.03,
    "walk_scale": 0.04,
    "bedroom_time_scale": 0.015,
    "bedroom_slope_scale": 0.06,
    "unit_drift_scale": 0.03,
    "fslope_scale_0": 0.05,
    "fslope_scale_1": 0.07,
}


def dense_mean(d, lam, s, kappa=None):
    n, p = d.a.shape
    K, L, J = d.n_buildings, d.n_local, d.n_units
    D = J if d.unit_drift else 0
    X = np.zeros((n, p + K * L + J + D))
    X[:, :p] = np.asarray(d.a)
    if D:
        X[np.arange(n), p + K * L + J + np.asarray(d.unit)] = np.asarray(d.unit_time)
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
    for k in range(K):
        prior[p + k * L : p + (k + 1) * L, p + k * L : p + (k + 1) * L] = local
    kap = np.ones(J) if kappa is None else np.asarray(kappa)
    prior[p + K * L : p + K * L + J, p + K * L : p + K * L + J] += (
        np.diag(kap) / s["unit_scale"] ** 2
    )
    if D:
        prior[p + K * L + J :, p + K * L + J :] += (
            np.eye(D) / s["unit_drift_scale"] ** 2
        )
    w = lam / s["sigma"] ** 2
    mean = np.linalg.solve(X.T @ (w[:, None] * X) + prior, X.T @ (w * np.asarray(d.y)))
    return mean[:p], mean[p : p + K * L].reshape(K, L), mean[p + K * L : p + K * L + J]


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_joint_gaussian_mean_matches_dense_solve(design):
    prep = synthetic()
    d = gibbs.build_design(prep, DESIGNS[design])
    lam = np.random.default_rng(1).gamma(2.5, 1 / 2.5, d.y.shape[0])
    theta, theta_l, u, *_ = gibbs.gaussian_block(
        d,
        jnp.asarray(lam),
        SCALES,
        jnp.zeros(d.a.shape[1]),
        jnp.zeros((d.n_buildings, d.n_local)),
        jnp.zeros((d.n_units, 2) if d.unit_drift else d.n_units),
    )
    e_theta, e_l, e_u = dense_mean(d, lam, SCALES)
    np.testing.assert_allclose(np.asarray(theta), e_theta, atol=1e-8)
    np.testing.assert_allclose(np.asarray(theta_l), e_l, atol=1e-8)
    np.testing.assert_allclose(np.asarray(u), e_u, atol=1e-8)


def dense_logml(d, lam, s, kappa=None):
    """log N(y; 0, X Q_prior^-1 X' + W^-1), by brute force."""
    from scipy.stats import multivariate_normal

    n, p = d.a.shape
    K, L, J = d.n_buildings, d.n_local, d.n_units
    D = J if d.unit_drift else 0
    X = np.zeros((n, p + K * L + J + D))
    X[:, :p] = np.asarray(d.a)
    if D:
        X[np.arange(n), p + K * L + J + np.asarray(d.unit)] = np.asarray(d.unit_time)
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
    for k in range(K):
        prior[p + k * L : p + (k + 1) * L, p + k * L : p + (k + 1) * L] = local
    kap = np.ones(J) if kappa is None else np.asarray(kappa)
    prior[p + K * L : p + K * L + J, p + K * L : p + K * L + J] += (
        np.diag(kap) / s["unit_scale"] ** 2
    )
    if D:
        prior[p + K * L + J :, p + K * L + J :] += (
            np.eye(D) / s["unit_drift_scale"] ** 2
        )
    cov = X @ np.linalg.solve(prior, X.T) + np.diag(s["sigma"] ** 2 / lam)
    return multivariate_normal(np.zeros(n), cov).logpdf(np.asarray(d.y))


@pytest.mark.parametrize(
    "design", ["base", "all", "quarterly", "fslopes", "drift", "tdrift"]
)
def test_collapsed_marginal_likelihood_matches_dense(design):
    prep = synthetic()
    d = gibbs.build_design(prep, DESIGNS[design])
    lam = np.random.default_rng(1).gamma(2.5, 1 / 2.5, d.y.shape[0])
    other = {k: v * 1.3 for k, v in SCALES.items()}
    zeros = (
        jnp.zeros(d.a.shape[1]),
        jnp.zeros((d.n_buildings, d.n_local)),
        jnp.zeros((d.n_units, 2) if d.unit_drift else d.n_units),
    )
    ml1 = float(gibbs.gaussian_block(d, jnp.asarray(lam), SCALES, *zeros)[-1])
    ml2 = float(gibbs.gaussian_block(d, jnp.asarray(lam), other, *zeros)[-1])
    np.testing.assert_allclose(
        ml1 - ml2, dense_logml(d, lam, SCALES) - dense_logml(d, lam, other), atol=1e-6
    )


def test_student_t_units_block_matches_dense():
    """Per-unit prior precisions kappa_j / tau^2 (Student-t units as a scale mixture)."""
    prep = synthetic()
    d = gibbs.build_design(prep, DESIGNS["tunits"])
    rng = np.random.default_rng(5)
    lam = rng.gamma(2.5, 1 / 2.5, d.y.shape[0])
    kappa = rng.gamma(1.5, 1 / 1.5, d.n_units)
    zeros = (
        jnp.zeros(d.a.shape[1]),
        jnp.zeros((d.n_buildings, d.n_local)),
        jnp.zeros((d.n_units, 2) if d.unit_drift else d.n_units),
    )
    theta, theta_l, u, _, _, ml1 = gibbs.gaussian_block(
        d, jnp.asarray(lam), SCALES, *zeros, jnp.asarray(kappa)
    )
    e_theta, e_l, e_u = dense_mean(d, lam, SCALES, kappa)
    np.testing.assert_allclose(np.asarray(theta), e_theta, atol=1e-8)
    np.testing.assert_allclose(np.asarray(theta_l), e_l, atol=1e-8)
    np.testing.assert_allclose(np.asarray(u), e_u, atol=1e-8)
    other = {k: v * 1.3 for k, v in SCALES.items()}
    ml2 = float(
        gibbs.gaussian_block(d, jnp.asarray(lam), other, *zeros, jnp.asarray(kappa))[-1]
    )
    np.testing.assert_allclose(
        float(ml1) - ml2,
        dense_logml(d, lam, SCALES, kappa) - dense_logml(d, lam, other, kappa),
        atol=1e-6,
    )


@pytest.mark.parametrize("design", ["all", "quarterly", "fslopes", "tunits", "tdrift"])
def test_site_values_reproduce_linear_predictor(design):
    """Gibbs state -> NumPyro sites -> model.linear_predictor equals the Gibbs fit."""
    prep = synthetic()
    d = gibbs.build_design(prep, DESIGNS[design])
    rng = np.random.default_rng(3)
    state = {
        "theta": jnp.asarray(rng.normal(0, 0.1, d.a.shape[1])),
        "local": jnp.asarray(rng.normal(0, 0.1, (d.n_buildings, d.n_local))),
        "unit": jnp.asarray(rng.normal(0, 0.1, d.n_units)),
        "nu": 5.0,
        "unit_nu": 4.0,
        "kappa": jnp.ones(d.n_units),
        "drift": jnp.asarray(rng.normal(0, 0.05, d.n_units)),
        **{k: SCALES[k] for k in d.scale_names},
    }
    p = gibbs.site_values(d, state)
    mu_model = model.linear_predictor(p, prep.train.map(jnp.asarray))
    mu_gibbs = d.a @ state["theta"] + gibbs.local_value(
        state["local"], d.building, d.slots, d.slot_values
    )
    mu_gibbs = mu_gibbs + state["unit"][d.unit]
    if d.unit_drift:
        mu_gibbs = mu_gibbs + state["drift"][d.unit] * d.unit_time
    np.testing.assert_allclose(np.asarray(mu_model), np.asarray(mu_gibbs), atol=1e-10)


@pytest.mark.slow
@pytest.mark.parametrize(
    "design",
    [
        "base",
        "walk",
        "all",
        "tunits",
        # Passes against the non-centred reference (unit_drift_scale sd ratio
        # 0.98-1.05 over two seeds, PR #17 review); the old xfail's numbers were
        # from the centred reference. Gibbs ESS on unit_drift_scale is ~80-200
        # here, so the 15% sd tolerance is about 2 sigma.
        "tdrift",
    ],
)
def test_gibbs_matches_nuts_on_same_model(design):
    """Both samplers target the NumPyro model's posterior; compare moments."""
    from numpyro.infer import MCMC, NUTS

    prep = synthetic(seed=2)
    config = DESIGNS[design]
    # Reference: NUTS with the walk and drift sites non-centred. On this small
    # synthetic dataset their scales sit near zero, where centred NUTS mixes
    # badly (walk scale: ESS 129 centred vs 5,175 non-centred) and understates
    # the posterior sd; Gibbs matched the non-centred reference (sd 0.00851
    # vs 0.00854). The reparameterisation leaves the posterior unchanged.
    ref_config = dataclasses.replace(
        config,
        noncentered=tuple(
            site
            for site, on in (
                ("walk_step", config.building_walk),
                ("unit_drift", config.unit_drift),
            )
            if on
        ),
    )
    mcmc = MCMC(
        NUTS(model.build_model(prep, ref_config), target_accept_prob=0.9),
        num_warmup=1000,
        num_samples=2000,
        num_chains=2,
        chain_method="sequential",
        progress_bar=False,
    )
    mcmc.run(jax.random.PRNGKey(0))
    nuts = {k: np.asarray(v) for k, v in mcmc.get_samples().items()}
    out = gibbs.run(
        prep,
        config,
        gibbs.Settings(chains=8, warmup=500, draws=2000, keep_every=500),
        log=lambda *_: None,
    )
    means = out["mean"]
    sds = out["sd"]
    checks = {
        "sigma": (nuts["sigma"], means["sigma"], sds["sigma"]),
        "unit_scale": (nuts["unit_scale"], means["unit_scale"], sds["unit_scale"]),
        "building_scale": (
            nuts["building_scale"],
            means["building_scale"],
            sds["building_scale"],
        ),
        "nu": (nuts["nu"], means["nu"], sds["nu"]),
        "beta0": (nuts["beta"][:, 0], means["beta"][0], sds["beta"][0]),
        "building0": (nuts["building"][:, 0], means["building"][0], sds["building"][0]),
    }
    if config.building_walk:
        knots = np.cumsum(nuts["walk_step"], axis=2)  # knot 1.. of each building
        checks["walk_scale"] = (
            nuts["walk_scale"],
            means["walk_scale"],
            sds["walk_scale"],
        )
        checks["walk[0, 2]"] = (knots[:, 0, 1], means["walk"][0, 2], sds["walk"][0, 2])
    if config.bedroom_slope:
        checks["bedroom_slope_scale"] = (
            nuts["bedroom_slope_scale"],
            means["bedroom_slope_scale"],
            sds["bedroom_slope_scale"],
        )
        checks["bedroom_slope[0]"] = (
            nuts["bedroom_slope"][:, 0],
            means["bedroom_slope"][0],
            sds["bedroom_slope"][0],
        )
    if config.unit_drift:
        checks["unit_drift_scale"] = (
            nuts["unit_drift_scale"],
            means["unit_drift_scale"],
            sds["unit_drift_scale"],
        )
        checks["unit_drift[0]"] = (
            nuts["unit_drift"][:, 0],
            means["unit_drift"][0],
            sds["unit_drift"][0],
        )
    if config.unit_t:
        checks["unit_nu"] = (nuts["unit_nu"], means["unit_nu"], sds["unit_nu"])
        checks["unit0"] = (nuts["unit"][:, 0], means["unit"][0], sds["unit"][0])
    if config.bedroom_time:
        curve = np.cumsum(
            nuts["bedroom_time_step"], axis=2
        )  # (draws, groups, months-1)
        checks["bedroom_time[studio, 12]"] = (
            curve[:, 0, 11],
            means["bedroom_time"][0, 12],
            sds["bedroom_time"][0, 12],
        )
    from numpyro.diagnostics import effective_sample_size

    scalar_trace = dict(
        zip(collect.SCALARS, np.moveaxis(out["trace"]["scalars"], -1, 0))
    )
    n_gibbs = out["trace"]["scalars"].shape[0] * out["trace"]["scalars"].shape[1]
    for name, (draws, g_mean, g_sd) in checks.items():
        # Monte Carlo standard errors from each sampler's effective sample size.
        chains = draws.reshape(2, -1)
        ess_nuts = float(effective_sample_size(chains[..., None])[0])
        ess_gibbs = (
            float(effective_sample_size(scalar_trace[name]))
            if name in scalar_trace
            else 0.05 * n_gibbs
        )
        mcse = np.sqrt(draws.var() / ess_nuts + g_sd**2 / ess_gibbs)
        assert abs(draws.mean() - g_mean) < 4 * mcse, (name, draws.mean(), g_mean, mcse)
        assert abs(draws.std() - g_sd) < 0.15 * draws.std(), (name, draws.std(), g_sd)


def test_unseen_unit_quadrature_matches_adaptive_integration():
    """Unseen-unit density (t-level + normal drift + t-noise) vs SciPy adaptive quadrature."""
    from scipy import integrate, stats

    prep = synthetic()
    d = gibbs.build_design(prep, DESIGNS["tdrift"])
    rng = np.random.default_rng(7)
    state = {
        "theta": jnp.asarray(rng.normal(0, 0.1, d.a.shape[1])),
        "local": jnp.asarray(rng.normal(0, 0.1, (d.n_buildings, d.n_local))),
        "unit": jnp.asarray(rng.normal(0, 0.1, d.n_units)),
        "drift": jnp.asarray(rng.normal(0, 0.05, d.n_units)),
        "kappa": jnp.ones(d.n_units),
        "nu": 3.0,
        "unit_nu": 2.5,
        **{k: SCALES[k] for k in d.scale_names},
    }
    p = gibbs.site_values(d, state)
    base = prep.test.map(jnp.asarray)
    values = {f: getattr(base, f) for f in model.Arrays.FIELDS}
    values["unit"] = jnp.full_like(base.unit, -1)
    values["unit_time"] = jnp.linspace(-1.5, 2.0, len(base.y))
    test = model.Arrays(**values)
    lp = np.asarray(collect.heldout_logpdf(p, test, True))
    mu = np.asarray(model.linear_predictor(p, test, include_unit=False))
    tau, tau_d, sig = SCALES["unit_scale"], SCALES["unit_drift_scale"], SCALES["sigma"]
    for i in range(len(lp)):
        r, xt = float(test.y[i]) - mu[i], float(test.unit_time[i])

        def over_level(lev, r=r, xt=xt):
            def inner(dr):
                return stats.t.pdf(r - lev - dr * xt, 3.0, scale=sig) * stats.norm.pdf(
                    dr, 0, tau_d
                )

            return integrate.quad(inner, -8 * tau_d, 8 * tau_d, epsabs=1e-12)[
                0
            ] * stats.t.pdf(lev, 2.5, scale=tau)

        ref = integrate.quad(
            over_level, -np.inf, np.inf, points=None, limit=400, epsabs=1e-12
        )[0]
        assert abs(lp[i] - np.log(ref)) < 5e-3, (i, lp[i], np.log(ref))


def test_warmup_spread_ignores_drift_and_adaptation_cuts_dead_steps():
    rng = np.random.default_rng(0)
    t = np.arange(400)
    drift = 0.01 * t[None, :, None]  # a chain still sliding from its start
    x = drift + rng.normal(0, 0.02, (4, 400, 1))
    assert np.sqrt(gibbs._detrended_var(x).mean()) == pytest.approx(0.02, rel=0.1)
    assert np.sqrt(x.var(axis=1).mean()) > 0.5  # a plain variance sees the drift
    assert gibbs._adapt(0.0, 0.3) == 0.3
    assert gibbs._adapt(0.3, 0.3) == pytest.approx(1.0)
    assert gibbs._adapt(0.6, 0.3) > 1.0


def test_detrended_cov_recovers_correlation_despite_drift():
    rng = np.random.default_rng(1)
    c = np.array([[1.0, 0.8], [0.8, 1.0]]) * 1e-4
    z = rng.multivariate_normal([0, 0], c, (4, 2000))
    x = z + 0.001 * np.arange(2000)[None, :, None]
    np.testing.assert_allclose(gibbs._detrended_cov(x), c, rtol=0.1, atol=1e-6)
    f = np.linalg.cholesky(c)
    np.testing.assert_allclose(gibbs._step_sds(f), [0.01, 0.01])
