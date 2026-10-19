"""The level walk: `rentfrontier.centered_walk` with the intercept folded into the levels.

The centered walk fixes week 0's level at zero and keeps a separate intercept. Its fit
showed the cost of that. Raising every later week's level and lowering the intercept by the
same amount leaves every fitted rent after week 0 unchanged, so the posterior runs along a
ridge with slope -1 between the intercept and the average level. The sampler can only follow
it by moving all 672 levels together, and each chain stopped at its own point on it.

Here I store the levels M_0..M_W themselves, with M_w = intercept + L_w:

    M_0 ~ the intercept's prior
    M_w - M_{w-1} ~ Student-t(nu_T, g, tau),   w = 1..W.

The map from (intercept, L_1..L_W) to M has Jacobian 1, so the posterior is the centered
walk's. I report the intercept as M_0 and the trend as L = M - M_0, and so every summary
reads the same quantities as before. The slide along the ridge becomes a move of M_0 alone,
held by week 0's ads and by its first step.

Starting values come from the centered walk's: M_0 at its starting intercept and M_w at that
intercept plus the starting trend.

    python -m rentfrontier.run --model level-walk --split latest --name NAME [--chains 16 ...]
    python -m rentfrontier.loo NAME
"""

from __future__ import annotations

import math
import sys

import numpy as np

from . import b0, b0_1, centered_walk
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

NAME = "level-walk"


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
        M = numpyro.sample(
            "level", dist.ImproperUniform(constraints.real_vector, (), (W + 1,))
        )
        numpyro.factor(
            "level_0", dist.Normal(m_fix[alpha], s_fix[alpha]).log_prob(M[0])
        )
        step = jnp.diff(M)
        numpyro.factor("walk", dist.StudentT(nu_t, g, tau).log_prob(step).sum())
        beta = jnp.zeros(len(d.names)).at[rest].set(main).at[alpha].set(M[0])
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
    """The centered walk's starting points, with its intercept moved into the levels."""
    out = centered_walk.initial_values(d, priors, chains, seed)
    fixed, _, _ = split_index(d.names)
    keep = fixed != d.names.index("alpha")
    a = out["main"][:, ~keep][:, 0]
    out["main"] = out["main"][:, keep]
    out["level"] = np.concatenate([a[:, None], a[:, None] + out["level"]], axis=1)
    return out


def log_density(d: b0.Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the level walk."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model level-walk`: fit on the split's training rows and save."""
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
