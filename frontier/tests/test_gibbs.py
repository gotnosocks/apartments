import jax

jax.config.update("jax_enable_x64", True)

import jax.numpy as jnp  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from rentfrontier import gibbs, model  # noqa: E402
from rentfrontier.features import Features  # noqa: E402


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
                rows.append((b, b * 100 + j, m, cal, *x, y + 0.05 * rng.standard_t(5)))
    frame = pd.DataFrame(
        rows, columns=["b", "u", "m", "cal", "x0", "x1", "y"]
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
    )
    feats = Features("synthetic", ["x0", "x1"], ["x", "x"], x, np.ones(2))
    return model.Prepared(
        features=feats,
        offset=0.0,
        periods=pd.date_range("2020-01-01", periods=months, freq="MS"),
        buildings=np.arange(n_buildings),
        units=units,
        train=arrays,
        test=model.Arrays(
            *(
                v[:10]
                for v in (
                    arrays.y,
                    x,
                    arrays.month,
                    arrays.calendar,
                    arrays.building,
                    arrays.unit,
                )
            )
        ),
        test_audit_id=np.arange(10),
    )


def dense_mean(d, lam, s):
    n, p = d.a.shape
    K, J = d.n_buildings, d.n_units
    X = np.zeros((n, p + K + J))
    X[:, :p] = np.asarray(d.a)
    X[np.arange(n), p + np.asarray(d.building)] = 1
    X[np.arange(n), p + K + np.asarray(d.unit)] = 1
    prior = np.zeros((p + K + J,) * 2)
    prior[:p, :p] = np.diag(np.asarray(d.prior_fixed))
    t = d.trend
    prior[t, t] += gibbs._rw1_anchored(t.stop - t.start) / s["trend_scale"] ** 2
    prior[d.season, d.season] += np.eye(12) / s["season_scale"] ** 2
    prior[p : p + K, p : p + K] += np.eye(K) / s["building_scale"] ** 2
    prior[p + K :, p + K :] += np.eye(J) / s["unit_scale"] ** 2
    w = lam / s["sigma"] ** 2
    mean = np.linalg.solve(X.T @ (w[:, None] * X) + prior, X.T @ (w * np.asarray(d.y)))
    return mean[:p], mean[p : p + K], mean[p + K :]


def test_joint_gaussian_mean_matches_dense_solve():
    prep = synthetic()
    d = gibbs.build_design(prep, model.ModelConfig())
    lam = np.random.default_rng(1).gamma(2.5, 1 / 2.5, d.y.shape[0])
    s = {
        "sigma": 0.05,
        "unit_scale": 0.08,
        "building_scale": 0.3,
        "trend_scale": 0.02,
        "season_scale": 0.03,
    }
    theta, b, u, _ = gibbs.gaussian_block(
        d,
        jnp.asarray(lam),
        s,
        jnp.zeros(d.a.shape[1]),
        jnp.zeros(d.n_buildings),
        jnp.zeros(d.n_units),
    )
    e_theta, e_b, e_u = dense_mean(d, lam, s)
    np.testing.assert_allclose(np.asarray(theta), e_theta, atol=1e-8)
    np.testing.assert_allclose(np.asarray(b), e_b, atol=1e-8)
    np.testing.assert_allclose(np.asarray(u), e_u, atol=1e-8)


@pytest.mark.slow
def test_gibbs_matches_nuts_on_same_model():
    """Both samplers target the NumPyro model's posterior; compare moments."""
    from numpyro.infer import MCMC, NUTS

    prep = synthetic(seed=2)
    config = model.ModelConfig()
    mcmc = MCMC(
        NUTS(model.build_model(prep, config), target_accept_prob=0.9),
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
    for name, (draws, g_mean, g_sd) in checks.items():
        # Means within 0.15 posterior sd (MC error of both samplers), sds within 15%.
        assert abs(draws.mean() - g_mean) < 0.15 * draws.std(), name
        assert abs(draws.std() - g_sd) < 0.15 * draws.std(), name
