"""The centered walk: `rentfrontier.b0_3`'s model with its trend sampled as levels.

B0.3 samples its trend non-centered. It stores one unitless shock z_w per week, with
z_w ~ Student-t(nu_T, 0, 1), and builds the levels as L_w = L_{w-1} + g + tau z_w. In B0.3's
fit, tau settled near 0.034 while the shocks the trend used spread about 0.007 a week, so
every z sat at a fifth of its prior's spread. With about 1.7 million rows pinning each week's
level, lowering tau means raising all 672 z's together by the same factor, and the sampler
could not make that move.

Here I store the levels L_1..L_W themselves and score the walk on their differences:

    L_0 = 0
    L_w - L_{w-1} ~ Student-t(nu_T, g, tau),   w = 1..W.

L_0 stays at zero, so the intercept stays identified. The map from B0.3's z to these levels
has Jacobian tau^W, and the Student-t density on the differences carries its inverse, so the
two describe the same posterior: same data, priors, ladder, bath pools, season, flags, errors
and interpolation. Only the sampler's coordinates change. Given the levels, tau reads off the
spread of the differences without moving the levels.

Starting values. Each level starts at its week's mean log ask after a least-squares fit of
the fixed design, less the first week's, with weeks holding no rows filled in from their
neighbors. tau starts at the walk's part of the spread of those starting steps, with the
weekly noise taken out (`starting_tau`). The intercept starts at the rows' mean log ask minus
their starting trend. Everything else starts as in B0.3.

    python -m rentfrontier.run --model centered-walk --split latest --name NAME [--chains 16 ...]
    python -m rentfrontier.loo NAME
"""

from __future__ import annotations

import math
import sys

import numpy as np

from . import b0, b0_1, b0_3
from .b0_3 import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    KEPT,
    POOLS,
    PROGRESS,
    TRACED,
    Priors,
    cell_log_premiums,
    design,
    diagnostics,
    modal_contrasts,
    prior_arrays,
    prior_draws,
    prior_predictive,
    scorecard,
    split_index,
    summarize,
)

NAME = "centered-walk"


def model(d: b0.Design, priors: Priors):
    """The model of design `d` as a NumPyro model function of no arguments."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    W = d.weeks
    m_fix, s_fix = prior_arrays(priors, d.names)
    fixed, steps, pools = split_index(d.names)
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    x = jnp.asarray(d.x)
    y = jnp.asarray(d.y)
    group = jnp.asarray(d.group)
    week = jnp.asarray(d.week)
    frac = jnp.asarray(d.frac)
    pools = jnp.asarray(pools)

    def fn():
        main = numpyro.sample("main", dist.Normal(m_fix, s_fix).to_event(1))
        phi = numpyro.sample(
            "phi", dist.Normal(*priors.bath).expand([len(POOLS)]).to_event(1)
        )
        s_bath = numpyro.sample("s_bath", dist.HalfNormal(priors.s_bath))
        u = numpyro.sample("bath_z", dist.Normal(0, 1).expand([len(steps)]).to_event(1))
        beta = jnp.zeros(len(d.names)).at[fixed].set(main)
        beta = beta.at[steps].set(phi[pools] + s_bath * u)
        numpyro.deterministic("beta", beta)
        g = numpyro.sample("g", dist.Normal(*priors.g))
        tau = numpyro.sample("tau", dist.Exponential(tau_rate))
        nu_t = numpyro.sample(
            "nu_t",
            dist.ImproperUniform(constraints.greater_than(priors.nu_t_min), (), ()),
        )
        numpyro.factor(
            "nu_t_prior", dist.Gamma(priors.nu_t[0], priors.nu_t[1]).log_prob(nu_t)
        )
        nu = numpyro.sample("nu", dist.Gamma(priors.nu[0], priors.nu[1]))
        sigma = numpyro.sample(
            "sigma", dist.HalfNormal(priors.sigma).expand([4]).to_event(1)
        )
        level = numpyro.sample(
            "level", dist.ImproperUniform(constraints.real_vector, (), (W,))
        )
        L = jnp.concatenate([jnp.zeros(1), level])
        step = jnp.diff(L)
        numpyro.factor("walk", dist.StudentT(nu_t, g, tau).log_prob(step).sum())
        numpyro.deterministic("L", L)
        numpyro.deterministic("eta", step - g)
        mu = x @ beta + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def starting_trend(d: b0.Design, rounds: int = 4) -> np.ndarray:
    """L_0..L_W from the weekly mean log asks, adjusted for each week's mix of ads.

    I alternate two least-squares steps: the coefficients on the fixed design given the
    trend, then each grid point's mean residual given the coefficients. Each row counts toward
    its nearer grid point, empty weeks take the line between their neighbors, and L_0 is
    zero."""
    at = np.clip(np.rint(d.week + d.frac).astype(int), 0, d.weeks)
    n = np.bincount(at, minlength=d.weeks + 1)
    seen = n > 0
    grid = np.arange(d.weeks + 1)
    xtx = d.x.T @ d.x + 1e-6 * np.eye(d.x.shape[1])
    L = np.zeros(d.weeks + 1)
    for _ in range(rounds):
        beta = np.linalg.solve(xtx, d.x.T @ (d.y - L[at]))
        s = np.bincount(at, weights=d.y - d.x @ beta, minlength=d.weeks + 1)
        L = np.interp(grid, grid[seen], s[seen] / n[seen])
        L -= L[0]
    return L


def starting_tau(L: np.ndarray) -> float:
    """The walk's shock spread in a trend measured with weekly noise.

    If each starting level is the walk plus independent noise of variance s^2, its steps
    have variance tau^2 + 2 s^2 and neighbouring steps a covariance of -s^2, so tau^2 is the
    variance plus twice the covariance. On B0.3's dense rows the steps spread 0.016 with a
    lag-one correlation of -0.37, which gives 0.008."""
    step = np.diff(L) - np.mean(np.diff(L))
    var = np.mean(step**2)
    cov = np.mean(step[1:] * step[:-1])
    return float(np.sqrt(max(var + 2 * cov, 0.002**2)))


def initial_values(d: b0.Design, priors: Priors, chains: int, seed: int) -> dict:
    """B0.3's starting points with the trend's swapped: the levels at the weekly means, tau
    at the spread of their steps, and the intercept moved to match."""
    out = b0_3.initial_values(d, priors, chains, seed)
    del out["z"]
    rng = np.random.default_rng(seed + 1)
    L = starting_trend(d)
    trend = (1 - d.frac) * L[d.week] + d.frac * L[d.week + 1]
    out["main"][:, 0] += -np.mean(trend)
    tau = starting_tau(L)
    out["tau"] = np.log(tau) + 0.1 * rng.standard_normal(chains)
    out["level"] = L[1:] + 0.001 * rng.standard_normal((chains, d.weeks))
    return out


def log_density(d: b0.Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the centered walk."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model centered-walk`: fit on the split's training rows and save."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--max-leapfrog-steps", type=int)
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=b0_1.Settings,
        sample=run,
        line="baseline-blackjax",
        spec=sys.modules[__name__],
    )
