"""The total walk: `rentfrontier.level_walk` with the season folded into the weekly levels.

The centered-walk fit showed the walk and the season trading the yearly cycle between them.
In each chain the season coefficients and the yearly content of the weekly levels moved one
for one in opposite directions, and their sum agreed across all 16 chains to within 0.0001.
The ads determine that sum. Shifting the split moved all 673 levels at once, and each chain stopped
at its own split.

Here I sample the total at each grid week, D_w = M_w + S_w, where M_w is the level walk's
level (intercept included) and S_w = B_w s is the season at grid week w, with B_w the
season's sin and cos terms at that week's day of year. I derive the walk's level by
subtracting the season:

    M_w = D_w - B_w s
    M_0 ~ the intercept's prior
    M_w - M_{w-1} ~ Student-t(nu_T, g, tau),   w = 1..W.

The regression still adds each ad's season at its exact day, and I subtract the season
interpolated between the two grid weeks, so each ad's mean equals the level walk's. The map from
(M, s) to (D, s) has Jacobian 1, so the posterior is the level walk's. Moving the season with
D held fixed changes only the walk's steps, through the 4 season coordinates.

Starting values come from the level walk's, with the starting season added to its levels.

    python -m rentfrontier.run --model total-walk --split latest --name NAME [--chains 16 ...]
    python -m rentfrontier.loo NAME
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

from . import b0, b0_1, level_walk
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

NAME = "total-walk"
SEASON = [f"{f}{k}" for k in range(1, b0.HARMONICS + 1) for f in ("sin", "cos")]


def grid_season(d: b0.Design) -> np.ndarray:
    """The season's sin and cos terms at each grid week's day of year, as the design builds
    them for an ad on that day: a (W + 1) x 4 matrix in SEASON's order."""
    day = d.start + pd.to_timedelta(7 * np.arange(d.weeks + 1), unit="D")
    doy = day.dayofyear.to_numpy() - 1 + 0.5
    cols = []
    for k in range(1, b0.HARMONICS + 1):
        angle = 2 * np.pi * k * doy / b0.YEAR_DAYS
        cols += [np.sin(angle), np.cos(angle)]
    return np.column_stack(cols)


def model(d: b0.Design, priors: Priors):
    """The model of design `d` as a NumPyro model function of no arguments."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    W = d.weeks
    m_fix, s_fix = prior_arrays(priors, d.names)
    fixed, steps, pools = split_index(d.names)
    # The intercept leaves the fixed coefficients and becomes week 0's level.
    alpha = d.names.index("alpha")
    rest = fixed[fixed != alpha]
    keep = fixed != alpha
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    x = jnp.asarray(d.x)
    y = jnp.asarray(d.y)
    group = jnp.asarray(d.group)
    week = jnp.asarray(d.week)
    frac = jnp.asarray(d.frac)
    pools = jnp.asarray(pools)
    B = jnp.asarray(grid_season(d))
    season = jnp.asarray([d.names.index(n) for n in SEASON])

    def fn():
        main = numpyro.sample("main", dist.Normal(m_fix[keep], s_fix[keep]).to_event(1))
        phi = numpyro.sample(
            "phi", dist.Normal(*priors.bath).expand([len(POOLS)]).to_event(1)
        )
        s_bath = numpyro.sample("s_bath", dist.HalfNormal(priors.s_bath))
        u = numpyro.sample("bath_z", dist.Normal(0, 1).expand([len(steps)]).to_event(1))
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
        D = numpyro.sample(
            "total", dist.ImproperUniform(constraints.real_vector, (), (W + 1,))
        )
        beta = jnp.zeros(len(d.names)).at[rest].set(main)
        M = D - B @ beta[season]
        numpyro.factor(
            "level_0", dist.Normal(m_fix[alpha], s_fix[alpha]).log_prob(M[0])
        )
        step = jnp.diff(M)
        numpyro.factor("walk", dist.StudentT(nu_t, g, tau).log_prob(step).sum())
        beta = beta.at[alpha].set(M[0])
        beta = beta.at[steps].set(phi[pools] + s_bath * u)
        numpyro.deterministic("beta", beta)
        L = M - M[0]
        numpyro.deterministic("L", L)
        numpyro.deterministic("eta", step - g)
        mu = x @ beta + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def initial_values(d: b0.Design, priors: Priors, chains: int, seed: int) -> dict:
    """The level walk's starting points, with each chain's starting season added to its
    levels."""
    out = level_walk.initial_values(d, priors, chains, seed)
    fixed, _, _ = split_index(d.names)
    rest = list(fixed[fixed != d.names.index("alpha")])
    s = out["main"][:, [rest.index(d.names.index(n)) for n in SEASON]]
    out["total"] = out.pop("level") + s @ grid_season(d).T
    return out


def log_density(d: b0.Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the total walk."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model total-walk`: fit on the split's training rows and save."""
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
