"""The normal walk: `rentfrontier.total_walk` with Normal shocks and a prior for each bath step.

I change two parts of the total walk and keep the rest: data, ladder, season, flags, noise
model, the intercept folded into week 0's level, and the weekly totals D_w = M_w + S_w.

The bath steps. B0.3 pools them across bedroom levels: each step is a shared mean phi_k for its
place against the modal count, plus s_bath times a standardized offset u. In the centered-walk
fit the ads determined the steps themselves (R-hat 1.04 at worst), but a pool mean and every
offset in its pool traded one for one, and the four pool means stayed at R-hat 1.28 to 2.12
with 15 to 32 effective draws. Here I drop the pooling and sample each bath step at each
bedroom level directly, with

    theta_{b,j} ~ Normal(0, 0.5)

in log rent. A level with few ads off its modal count keeps a step near zero instead of
borrowing from the other levels.

The shocks. The level walk scores its steps as Student-t(nu_T, g, tau). I score them as

    M_w - M_{w-1} ~ Normal(g, tau)

and drop nu_T. In the centered-walk fit nu_T sat near 4, and tau and nu_T traded against
each other (R-hat 1.30 and 1.23). With Normal shocks tau is the shocks' standard deviation.

Starting values come from the total walk's, with each step started at its pool mean plus its
spread times its offset, and no nu_T.

    python -m rentfrontier.run --model normal-walk --split latest --name NAME [--chains 16 ...]
    python -m rentfrontier.loo NAME
"""

from __future__ import annotations

import dataclasses
import math
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import b0, b0_1, b0_2, b0_3, total_walk
from .b0_3 import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    cell_log_premiums,
    design,
    modal_contrasts,
    prior_arrays,
    split_index,
)
from .total_walk import SEASON, grid_season

NAME = "normal-walk"
KEPT = ("beta", "g", "L", "nu", "sigma", "tau", "eta")
TRACED = ("beta", "g", "nu", "sigma", "tau")
PROGRESS = ("nu", "tau")


@dataclass(frozen=True)
class Priors:
    alpha: tuple = b0.Priors.alpha  # week 0's level
    bed: tuple = b0.Priors.bed
    bath: tuple = (0.0, 0.5)  # each bath step theta_{b,j}
    half: tuple = b0.Priors.half
    bath_unknown: tuple = b0.Priors.bath_unknown
    season: tuple = b0.Priors.season
    flag: tuple = b0.Priors.flag
    g: tuple = b0.Priors.g
    tau_u: float = b0_2.Priors.tau_u
    tau_alpha: float = b0_2.Priors.tau_alpha
    nu: tuple = b0.Priors.nu
    sigma: float = b0.Priors.sigma

    def to_dict(self):
        return dataclasses.asdict(self)


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
        numpyro.factor("walk", dist.Normal(g, tau).log_prob(step).sum())
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
    out = total_walk.initial_values(d, b0_3.Priors(), chains, seed)
    del out["nu_t"]
    _, _, pools = split_index(d.names)
    phi, s_bath, u = out.pop("phi"), out.pop("s_bath"), out.pop("bath_z")
    out["bath"] = phi[:, pools] + np.exp(s_bath)[:, None] * u
    return out


def _with_constants(draws: dict) -> dict:
    """`draws` with the pooled terms and nu_T B0.3's readers expect, held constant. Their
    diagnostics skip a constant quantity."""
    shape = np.shape(draws["g"])
    return draws | {
        "phi": np.zeros((*shape, len(b0_3.POOLS))),
        "s_bath": np.zeros(shape),
        "nu_t": np.zeros(shape),
    }


def diagnostics(trace: dict, names) -> dict:
    """B0.3's convergence table, without the pooled terms and nu_T."""
    return b0_3.diagnostics(_with_constants(trace), names)


def summarize(kept: dict, names) -> dict:
    """B0.3's summary without the shared bath steps, s_bath and nu_T, and with the realized
    shocks' spread against tau."""
    out = b0_3.summarize(_with_constants(kept), names)
    del out["shared_bath_steps"], out["hyper"]["s_bath"], out["hyper"]["nu_t"]
    eta = np.asarray(kept["eta"])
    spread = eta.std(axis=-1)
    q = lambda v: {  # noqa: E731
        "median": float(np.median(v)),
        "lo": float(np.quantile(v, 0.025)),
        "hi": float(np.quantile(v, 0.975)),
    }
    out["shocks"] = {
        "sd": q(spread),
        "sd_over_tau": q(spread / kept["tau"]),
        "max_abs_over_tau": q(np.abs(eta).max(axis=-1) / kept["tau"]),
    }
    return out


def scorecard(summary, season, trend) -> list:
    """The predictions written before the normal walk's first full fit (PR #1156), each with
    the measured value and hit or miss. Convergence and fit time are in the PR and the fit's
    notes."""
    c, h, sh = summary["modal_contrasts"], summary["hyper"], summary["shocks"]
    rows = []

    def add(n, claim, value, hit):
        rows.append({"n": n, "claim": claim, "value": value, "hit": bool(hit)})

    one = c["bed 0->1 on modal path"]["median"]
    add(1, "1 bed is +15% to +25% over a studio", f"{one:+.1f}%", 15 <= one <= 25)
    two = c["bed 1->2 on modal path"]["median"]
    add(2, "2 beds is -5% to +8% over 1 bed, at 1 bath", f"{two:+.1f}%", -5 <= two <= 8)
    r2 = c["2 bed: +1 full bath over 1"]["median"]
    add(3, "2 beds: a 2nd full bath adds +60% to +80%", f"{r2:+.1f}%", 60 <= r2 <= 80)
    r4 = c["4 bed: -1 full bath from 2"]["median"]
    add(4, "4 beds with 1 bath rent 20% to 35% below 4 beds with 2",
        f"{r4:+.1f}%", -35 <= r4 <= -20)  # fmt: skip
    tau = h["tau"]["median"]
    add(5, "tau 0.011 to 0.014", f"{tau:.4f}", 0.011 <= tau <= 0.014)
    r = sh["sd_over_tau"]["median"]
    add(6, "realized shock sd is 0.9 to 1.1 tau", f"{r:.2f}", 0.9 <= r <= 1.1)
    m = sh["max_abs_over_tau"]["median"]
    add(7, "the largest shock is 3.5 to 5.5 tau", f"{m:.1f}", 3.5 <= m <= 5.5)
    drop = trend["covid_drop_pct"]["median"]
    add(8, "2020 trough is 22% to 29% below early 2020",
        f"{drop:.1f}%", -29 <= drop <= -22)  # fmt: skip
    g = h["g_yearly_pct"]["median"]
    add(9, "g +1% to +4% a year", f"g {g:+.2f}%/yr", 1 <= g <= 4)
    peak = float(season["days"][np.argmax(np.median(season["curve"], axis=0))])
    month = (pd.Timestamp("2001-01-01") + pd.Timedelta(days=peak)).month
    add(10, "season peaks May to July", f"peak day {peak:.0f} (month {month})",
        5 <= month <= 7)  # fmt: skip
    return rows


def log_density(d: b0.Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the normal walk."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model normal-walk`: fit on the split's training rows and save."""
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
