"""Free bath steps: `rentfrontier.total_walk` with each bath step given its own prior.

B0.3 pools the bath steps across bedroom levels. Each step is a shared mean phi_k for its place
against the modal count, plus s_bath times a standardized offset u. The centered-walk fit
showed that pooling failing to converge. The ads determine the steps themselves (R-hat 1.04 at
worst), but a pool mean and every offset in its pool trade one for one, and the four pool means
stayed at R-hat 1.28 to 2.12 with 15 to 32 effective draws.

Here I drop the pooling. Each bath step at each bedroom level, theta_{b,j}, gets B0's bath
prior on its own,

    theta_{b,j} ~ Normal(0.1, 0.2),

and I sample the steps directly, with no phi_k, s_bath or u. A level with few ads off its modal
count now keeps a step near that prior instead of borrowing from the other levels. This changes
the model, unlike the walk's reparametrizations. Everything else is the total walk's.

Starting values come from the total walk's, with each step started at its pool mean plus its
spread times its offset.

    python -m rentfrontier.run --model free-bath --split latest --name NAME [--chains 16 ...]
    python -m rentfrontier.loo NAME
"""

from __future__ import annotations

import math
import sys

import numpy as np

from . import b0, b0_1, b0_3, total_walk
from .b0_3 import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    Priors,
    cell_log_premiums,
    design,
    modal_contrasts,
    prior_arrays,
    split_index,
)
from .total_walk import SEASON, grid_season

NAME = "free-bath"
KEPT = ("beta", "g", "L", "nu", "sigma", "tau", "nu_t", "eta")
TRACED = ("beta", "g", "nu", "sigma", "tau", "nu_t")
PROGRESS = ("nu", "tau", "nu_t")


def model(d: b0.Design, priors: Priors):
    """The model of design `d` as a NumPyro model function of no arguments."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    W = d.weeks
    m_fix, s_fix = prior_arrays(priors, d.names)
    fixed, steps, _ = split_index(d.names)
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
    B = jnp.asarray(grid_season(d))
    season = jnp.asarray([d.names.index(n) for n in SEASON])

    def fn():
        main = numpyro.sample("main", dist.Normal(m_fix[keep], s_fix[keep]).to_event(1))
        theta = numpyro.sample(
            "bath", dist.Normal(*priors.bath).expand([len(steps)]).to_event(1)
        )
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
        beta = beta.at[steps].set(theta)
        numpyro.deterministic("beta", beta)
        L = M - M[0]
        numpyro.deterministic("L", L)
        numpyro.deterministic("eta", step - g)
        mu = x @ beta + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def initial_values(d: b0.Design, priors: Priors, chains: int, seed: int) -> dict:
    """The total walk's starting points, with each bath step started where the pooled
    starting values put it."""
    out = total_walk.initial_values(d, priors, chains, seed)
    _, _, pools = split_index(d.names)
    phi, s_bath, u = out.pop("phi"), out.pop("s_bath"), out.pop("bath_z")
    out["bath"] = phi[:, pools] + np.exp(s_bath)[:, None] * u
    return out


def _with_constant_pools(draws: dict) -> dict:
    """`draws` with the pooled terms B0.3's readers expect, held at zero. Their diagnostics
    skip a constant quantity."""
    shape = np.shape(draws["g"])
    return draws | {
        "phi": np.zeros((*shape, len(b0_3.POOLS))),
        "s_bath": np.zeros(shape),
    }


def diagnostics(trace: dict, names) -> dict:
    """B0.3's convergence table, without the pooled terms."""
    return b0_3.diagnostics(_with_constant_pools(trace), names)


def summarize(kept: dict, names) -> dict:
    """B0.3's summary, without the shared bath steps and s_bath."""
    out = b0_3.summarize(_with_constant_pools(kept), names)
    del out["shared_bath_steps"], out["hyper"]["s_bath"]
    return out


def scorecard(summary, season, trend) -> list:
    """B0.3's predictions that still apply here: all but the shared bath step (3) and s_bath
    (6)."""
    full = summary | {
        "shared_bath_steps": {"bath+1": {"median": math.nan}},
        "hyper": summary["hyper"] | {"s_bath": {"median": math.nan}},
    }
    return [r for r in b0_3.scorecard(full, season, trend) if r["n"] not in (3, 6)]


def log_density(d: b0.Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the total walk with free bath steps."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model free-bath`: fit on the split's training rows and save."""
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
