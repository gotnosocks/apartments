import jax

jax.config.update("jax_enable_x64", True)

import dataclasses
from types import SimpleNamespace

import jax.numpy as jnp
import numpy as np
import pytest
from rentfrontier import gibbs, marginal_hmc
from rentfrontier.marginal_hmc import NU_HI, NU_LO
from scipy import stats
from test_gibbs import DESIGNS, synthetic


def t_residuals(n, nu, seed=0):
    rng = np.random.default_rng(seed)
    return jnp.asarray(stats.t.rvs(nu, size=n, random_state=rng)), jnp.ones(n)


def test_nu_proposal_density_integrates_to_one():
    e, sig = t_residuals(800, 4.0)
    edges, log_w = marginal_hmc.nu_proposal(
        lambda v: marginal_hmc.nu_log_target(v, e, sig)
    )
    v = jnp.linspace(NU_LO, NU_HI, 400_001)[:-1] + 0.5 * (NU_HI - NU_LO) / 400_000
    q = jnp.exp(jax.vmap(lambda x: marginal_hmc.nu_log_q(x, edges, log_w))(v))
    assert abs(float(q.mean() * (NU_HI - NU_LO)) - 1) < 1e-3


def test_nu_draws_match_the_grid_posterior():
    """Independent chains from scattered starts, 3 Metropolis steps each, give
    log nu with the mean and sd of the dense numerical posterior."""
    e, sig = t_residuals(800, 4.0)
    grid = jnp.linspace(NU_LO, NU_HI, 20_001)
    lp = jax.vmap(lambda v: marginal_hmc.nu_log_target(v, e, sig))(grid)
    w = np.exp(np.asarray(lp - lp.max()))
    w /= w.sum()
    mean = float((w * grid).sum())
    sd = float(np.sqrt((w * (grid - mean) ** 2).sum()))

    n = 4000
    starts = jax.random.uniform(jax.random.PRNGKey(1), (n,), minval=NU_LO, maxval=NU_HI)
    keys = jax.random.split(jax.random.PRNGKey(2), n)
    xs, acc = jax.jit(jax.vmap(lambda k, x: marginal_hmc.draw_log_nu(k, x, e, sig, 3)))(
        keys, starts
    )
    xs = np.asarray(xs)
    assert float(acc.mean()) > 0.7
    assert abs(xs.mean() - mean) < 4 * sd / np.sqrt(n)
    assert abs(xs.std() / sd - 1) < 0.06


def test_interweaving_keeps_the_prior():
    """With the scales from their half-normal priors and the weights from
    Gamma(nu / 2, rate nu / 2), the move returns draws from the same joint:
    each scale and each weight keeps its marginal."""
    n_rows, n_units, reps, nu = 40, 25, 4000, 3.0
    d = SimpleNamespace(
        noise_group=jnp.arange(n_rows) % 2,
        group_noise_names=("sigma_a", "sigma_b"),
        y=jnp.zeros(n_rows),
        prior_sd={"sigma_a": 0.2, "sigma_b": 0.5, "unit_scale": 0.3},
        unit_t=True,
        unit_nu_fixed=4.0,
        n_units=n_units,
    )
    keys = jax.random.split(jax.random.PRNGKey(3), 6)
    sd = jnp.asarray([0.2, 0.5])
    sig = jnp.abs(jax.random.normal(keys[0], (reps, 2))) * sd
    s_u = jnp.abs(jax.random.normal(keys[1], (reps,))) * 0.3
    lam = jax.random.gamma(keys[2], nu / 2, (reps, n_rows)) / (nu / 2)
    kappa = jax.random.gamma(keys[3], 2.0, (reps, n_units)) / 2.0

    def move(k, sig, s_u, lam, kappa):
        s = {"sigma_a": sig[0], "sigma_b": sig[1], "unit_scale": s_u}
        return marginal_hmc.interweave(k, d, s, lam, kappa, nu)

    s, lam, kappa = jax.vmap(move)(
        jax.random.split(keys[4], reps), sig, s_u, lam, kappa
    )
    for name, scale in d.prior_sd.items():
        assert stats.kstest(np.asarray(s[name]), "halfnorm", (0, scale)).pvalue > 1e-3
    for i in (0, 1):
        got = np.asarray(lam[:, i])
        assert stats.kstest(got, "gamma", (nu / 2, 0, 2 / nu)).pvalue > 1e-3
    assert stats.kstest(np.asarray(kappa[:, 0]), "gamma", (2.0, 0, 0.5)).pvalue > 1e-3


def test_block_scale_draws_keep_the_posterior():
    """Alternating exact draws of g given the scales with `block_scales` on a
    Gaussian toy (data precision A about mu, two blocks under half-normal
    scales) gives each scale the mean and sd of its grid posterior, from the
    marginal likelihood N(mu; 0, Q(s)^-1 + A^-1)."""
    rng = np.random.default_rng(4)
    p = 6
    m = rng.normal(size=(p, p))
    a = jnp.asarray(m @ m.T / p + 0.5 * np.eye(p))
    mu = jnp.asarray(rng.normal(size=p) * 0.6)
    r1 = jnp.asarray(2 * np.eye(4) - np.eye(4, k=1) - np.eye(4, k=-1) + 0.2 * np.eye(4))
    blocks = {"s1": (slice(1, 5), r1), "s2": (slice(5, 6), jnp.eye(1))}
    prior_sd = {"s1": 0.5, "s2": 1.0}

    def prec(s1, s2):
        q = jnp.zeros((p, p)).at[0, 0].set(1.0)
        q = q.at[1:5, 1:5].add(r1 / s1**2)
        return q.at[5, 5].add(1 / s2**2)

    def f(g):
        return -0.5 * (g - mu) @ a @ (g - mu)

    def sweep(carry, k):
        g, s = carry
        k1, k2 = jax.random.split(k)
        h = a + prec(s["s1"], s["s2"])
        chol = jnp.linalg.cholesky(h)
        mean = jax.scipy.linalg.cho_solve((chol, True), a @ mu)
        g = mean + jax.scipy.linalg.solve_triangular(
            chol.T, jax.random.normal(k1, (p,)), lower=False
        )
        return marginal_hmc.block_scales(k2, f, g, s, blocks, prior_sd), None

    def chain(k):
        s0 = {"s1": jnp.asarray(0.3), "s2": jnp.asarray(0.5)}
        (g, s), _ = jax.lax.scan(sweep, (mu, s0), jax.random.split(k, 150))
        return s

    n = 4000
    draws = jax.jit(jax.vmap(chain))(jax.random.split(jax.random.PRNGKey(5), n))

    grid1 = jnp.linspace(1e-3, 3.0, 300)
    grid2 = jnp.linspace(1e-3, 5.0, 300)
    a_inv = jnp.linalg.inv(a)

    def log_post(s1, s2):
        cov = jnp.linalg.inv(prec(s1, s2)) + a_inv
        lml = jax.scipy.stats.multivariate_normal.logpdf(mu, jnp.zeros(p), cov)
        return lml - s1**2 / (2 * 0.25) - s2**2 / 2

    lp = jax.vmap(lambda s1: jax.vmap(lambda s2: log_post(s1, s2))(grid2))(grid1)
    w = np.exp(np.asarray(lp - lp.max()))
    w /= w.sum()
    for name, grid, marg in (("s1", grid1, w.sum(1)), ("s2", grid2, w.sum(0))):
        grid = np.asarray(grid)
        mean = (marg * grid).sum()
        sd = np.sqrt((marg * (grid - mean) ** 2).sum())
        got = np.asarray(draws[name])
        assert abs(got.mean() - mean) < 4 * sd / np.sqrt(n), (name, got.mean(), mean)
        assert abs(got.std() / sd - 1) < 0.06, (name, got.std(), sd)


def test_run_scores_and_traces_like_gibbs():
    config = dataclasses.replace(DESIGNS["yearnoise"], unit_nu_fixed=4.0)
    prep = synthetic()
    out = marginal_hmc.run(
        prep,
        config,
        marginal_hmc.Settings(chains=2, warmup=40, pilot=20, draws=20, keep_every=10),
        log=lambda *_: None,
    )
    d = gibbs.build_design(prep, config, dense=False)
    assert np.all(np.isfinite(out["lpd"]))
    assert np.asarray(out["mean"]["sigma"]).shape == (len(d.group_noise_names),)
    assert np.all(np.asarray(out["mean"]["sigma"]) > 0)
    for k in ("accept_prob", "num_steps", "diverging", "nu_accept", "beta"):
        assert out["trace"][k].shape[:2] == (2, 20)
    assert out["sampler"] == "marginal-nuts"


def test_run_rejects_estimated_unit_nu():
    with pytest.raises(ValueError):
        marginal_hmc.run(
            synthetic(),
            DESIGNS["tunits"],
            marginal_hmc.Settings(chains=1, warmup=4, pilot=2, draws=2, keep_every=1),
            log=lambda *_: None,
        )


@pytest.mark.slow
@pytest.mark.parametrize("design", ["walkmin", "tunits"])
def test_marginal_nuts_matches_nuts_on_same_model(design):
    """Marginal NUTS and NumPyro's NUTS on the full NumPyro model (walk
    non-centred, as in `test_gibbs_matches_nuts_on_same_model`) give the same
    posterior moments: means within 4 combined MCSE, sds within 15%."""
    from numpyro.diagnostics import effective_sample_size
    from numpyro.infer import MCMC, NUTS
    from rentfrontier import collect, model

    prep = synthetic(seed=2)
    config = DESIGNS[design]
    if config.unit_t:
        config = dataclasses.replace(config, unit_nu_fixed=4.0)
    mcmc = MCMC(
        NUTS(
            model.build_model(
                prep, dataclasses.replace(config, noncentered=("walk_step",))
            ),
            target_accept_prob=0.9,
        ),
        num_warmup=1000,
        num_samples=2000,
        num_chains=2,
        chain_method="sequential",
        progress_bar=False,
    )
    mcmc.run(jax.random.PRNGKey(0))
    nuts = {k: np.asarray(v) for k, v in mcmc.get_samples().items()}
    out = marginal_hmc.run(
        prep,
        config,
        marginal_hmc.Settings(
            chains=4, warmup=500, pilot=150, draws=1000, keep_every=50, local_sweeps=3
        ),
        log=lambda *_: None,
    )
    means, sds = out["mean"], out["sd"]
    checks = {
        n: (nuts[n], means[n], sds[n])
        for n in ("sigma", "nu", "unit_scale", "building_scale", "walk_scale")
    }
    checks["bedroom_slope_scale"] = (
        nuts["bedroom_slope_scale"],
        means["bedroom_slope_scale"],
        sds["bedroom_slope_scale"],
    )
    checks["beta0"] = (nuts["beta"][:, 0], means["beta"][0], sds["beta"][0])
    checks["building0"] = (
        nuts["building"][:, 0],
        means["building"][0],
        sds["building"][0],
    )
    checks["unit0"] = (nuts["unit"][:, 0], means["unit"][0], sds["unit"][0])
    b = int(np.flatnonzero(model.walk_mask(prep, config))[0])
    checks[f"walk[{b}, 2]"] = (
        np.cumsum(nuts["walk_step"], axis=2)[:, b, 1],
        means["walk"][b, 2],
        sds["walk"][b, 2],
    )
    scalar_trace = dict(
        zip(collect.SCALARS, np.moveaxis(out["trace"]["scalars"], -1, 0))
    )
    n_draws = out["trace"]["scalars"].shape[0] * out["trace"]["scalars"].shape[1]
    for name, (draws, m_mean, m_sd) in checks.items():
        ess_nuts = float(effective_sample_size(draws.reshape(2, -1)[..., None])[0])
        ess_m = (
            float(effective_sample_size(scalar_trace[name]))
            if name in scalar_trace
            else 0.25 * n_draws
        )
        mcse = np.sqrt(draws.var() / ess_nuts + m_sd**2 / ess_m)
        assert abs(draws.mean() - m_mean) < 4 * mcse, (name, draws.mean(), m_mean, mcse)
        assert abs(draws.std() - m_sd) < 0.15 * draws.std(), (name, draws.std(), m_sd)
