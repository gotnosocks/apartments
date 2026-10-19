"""B0.2: B0 with a random walk with drift for its trend and a joint bedroom-by-bath ladder.

For row i, with y_i the log of its net-effective latest ask, dated at its latest ask's day t_i:

    y_i = alpha + Ladder_i + Half_i + T(t_i) + Season(t_i) + Flags_i + e_i,
    e_i ~ Student-t(nu, 0, sigma_g(i)), one sigma per bedroom group (studio, 1, 2, 3+).

B0.2 changes two parts of B0 (`rentfrontier.b0`) and keeps the rest: the half bath, the
season, the flags, the Student-t errors and their per-group scales.

The ladder. I put each ad in a cell (b, f) of a grid, with b its bedrooms (0 to 5, 5 or more
capped at 5) and f its full baths (1 to 4, 4 or more capped at 4, none counted as 1). A cell's
mean adds up every step at or below it:

    Ladder(b, f) = sum over i <= b and j <= f of theta_ij,  with theta_01 = 0 (alpha holds it).

- theta_i1 for i = 1..5 is the step to i bedrooms at one full bath, the column `bed>=i`.
- theta_0j for j = 2..4 is the step to j full baths for a studio, the column `full>=j`.
- theta_ij for i >= 1 and j >= 2 is how much the bath step j changes from i - 1 bedrooms to i
  bedrooms, the column `bed>=i&full>=j`. Its indicator is 1[beds >= i and full baths >= j].

The bedroom and studio bath steps keep B0's priors. The 15 interaction steps share a scale:
theta_ij ~ Normal(0, s_int) with s_int ~ HalfNormal(0.1). Each theta_ij is a second
difference of four neighbouring cells, (i, j) - (i-1, j) - (i, j-1) + (i-1, j-1), so a
step next to a thin cell is weakly identified even when its column holds many ads: on the
2026-10-19 off-market rows theta_14 rests on cells of 15, 60, 44 and 171 ads. Shrinking
s_int pulls such steps toward zero, and then the bath step full>=j serves every bedroom
count alike, as in B0, with the thin cells borrowing it from the larger ones. The weak
steps and the shared scale make a funnel, so I sample the interaction steps non-centered,
theta_ij = s_int u_ij with u_ij ~ Normal(0, 1).

The trend. The weekly level moves by a drift and a Student-t shock:

    L_0 = 0,  L_w = L_{w-1} + g + tau z_w,  z_w ~ Student-t(nu_T, 0, 1),

read at t_i by linear interpolation, as in B0. B0's damped slope (its half-life h and slope
state S) is gone. B0 put h at 2.3 days, where its trend and this one coincide. I sample the
standardized shocks z and build L by a cumulative sum: a week's ads pin its level to about
0.006 against a shock scale near 0.002, so the shocks are weakly identified one by one, and
their prior governs them. eta = tau z keeps B0's name for the trend's shocks.

The sampler is B0.1's (`rentfrontier.b0_1`): ChEES-HMC in BlackJAX on the NumPyro model below,
in float64.

    python -m rentfrontier.b0_2 prior DATASET [--rows N]
    python -m rentfrontier.run --model b0.2 --split latest --name NAME [--chains 16 ...]
    python -m rentfrontier.loo NAME
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, b0_1

NAME = "b0.2"
BEDS = 5  # the ladder's top bedroom level
BATHS = 4  # the ladder's top full-bath level


@dataclass(frozen=True)
class Priors:
    alpha: tuple = b0.Priors.alpha
    bed: tuple = b0.Priors.bed
    bath: tuple = b0.Priors.bath
    half: tuple = b0.Priors.half
    bath_unknown: tuple = b0.Priors.bath_unknown
    season: tuple = b0.Priors.season
    flag: tuple = b0.Priors.flag
    s_int: float = 0.1  # HalfNormal scale of the interaction steps' shared sd
    g: tuple = b0.Priors.g
    # PC prior on the level shocks' scale: P(tau > tau_u) = tau_alpha. B0's tau_u of 0.0003
    # bounded shocks to the slope. A shock to the level moves rent once, and B0's slope shocks
    # with a 2.3-day half-life amount to level shocks of about 0.002.
    tau_u: float = 0.005
    tau_alpha: float = 0.01
    nu: tuple = b0.Priors.nu
    nu_t: tuple = b0.Priors.nu_t
    nu_t_min: float = b0.Priors.nu_t_min
    sigma: float = b0.Priors.sigma

    def to_dict(self):
        return dataclasses.asdict(self)


def interaction(name):
    return "&" in name


def design(frame: pd.DataFrame, start: pd.Timestamp | None = None) -> b0.Design:
    """B0's design of `frame` with the ladder's interaction columns after the bath steps. I
    leave out an interaction column no row sets, as B0 leaves out its empty indicators."""
    d = b0.design(frame, start)
    cols, names, count = [d.x], list(d.names), dict(d.count)
    at = max(j for j, n in enumerate(names) if n.startswith("full>=")) + 1
    new, new_names = [], []
    for i in range(1, BEDS + 1):
        for j in range(2, BATHS + 1):
            n = f"bed>={i}&full>={j}"
            if f"bed>={i}" not in names or f"full>={j}" not in names:
                continue
            col = d.x[:, names.index(f"bed>={i}")] * d.x[:, names.index(f"full>={j}")]
            count[n] = int(col.sum())
            if count[n] > 0:
                new.append(col)
                new_names.append(n)
    cols = [d.x[:, :at], *(c[:, None] for c in new), d.x[:, at:]]
    names = names[:at] + new_names + names[at:]
    return dataclasses.replace(d, x=np.hstack(cols), names=names, count=count)


def prior_arrays(priors: Priors, names):
    """Means and sds of the coefficients outside the interactions, in `names` order."""
    return b0.prior_arrays(priors, [n for n in names if not interaction(n)])


def split_index(names):
    """Positions of the interaction columns and of the others in `names`."""
    inter = np.array([j for j, n in enumerate(names) if interaction(n)], dtype=int)
    fixed = np.array([j for j, n in enumerate(names) if not interaction(n)], dtype=int)
    return fixed, inter


def model(d: b0.Design, priors: Priors):
    """The B0.2 model of design `d` as a NumPyro model function of no arguments."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    W = d.weeks
    m_fix, s_fix = prior_arrays(priors, d.names)
    fixed, inter = split_index(d.names)
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    x = jnp.asarray(d.x)
    y = jnp.asarray(d.y)
    group = jnp.asarray(d.group)
    week = jnp.asarray(d.week)
    frac = jnp.asarray(d.frac)

    def fn():
        main = numpyro.sample("main", dist.Normal(m_fix, s_fix).to_event(1))
        s_int = numpyro.sample("s_int", dist.HalfNormal(priors.s_int))
        u = numpyro.sample(
            "inter_z", dist.Normal(0, 1).expand([len(inter)]).to_event(1)
        )
        steps = s_int * u
        beta = jnp.zeros(len(d.names)).at[fixed].set(main).at[inter].set(steps)
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
        z = numpyro.sample("z", dist.StudentT(nu_t, 0, 1).expand([W]).to_event(1))
        L = jnp.concatenate([jnp.zeros(1), jnp.cumsum(g + tau * z)])
        numpyro.deterministic("L", L)
        numpyro.deterministic("eta", tau * z)
        mu = x @ beta + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def initial_values(d: b0.Design, priors: Priors, chains: int, seed: int) -> dict:
    """Unconstrained starting points, one per chain: B0.1's scatter, the intercept at the mean
    log rent, the trend near its prior drift, and interaction steps near zero."""
    rng = np.random.default_rng(seed)
    m_fix, _ = prior_arrays(priors, d.names)
    _, inter = split_index(d.names)
    main = np.tile(m_fix, (chains, 1))
    main[:, 0] = np.mean(d.y)
    main += 0.01 * rng.standard_normal(main.shape)
    nu_t = 2.0 * np.exp(0.2 * rng.standard_normal(chains))
    return {
        "main": main,
        "s_int": np.log(0.1) + 0.3 * rng.standard_normal(chains),
        "inter_z": 0.1 * rng.standard_normal((chains, len(inter))),
        "g": np.full(chains, priors.g[0]),
        "tau": np.log(0.002) + 0.3 * rng.standard_normal(chains),
        "nu_t": np.log(nu_t - priors.nu_t_min),
        "nu": np.log(10) + 0.3 * rng.standard_normal(chains),
        "sigma": np.log(0.3) + 0.2 * rng.standard_normal((chains, 4)),
        "z": 0.1 * rng.standard_normal((chains, d.weeks)),
    }


KEPT = ("beta", "g", "L", "nu", "sigma", "tau", "nu_t", "eta", "s_int")
TRACED = ("beta", "g", "nu", "sigma", "tau", "nu_t", "s_int")
PROGRESS = ("nu", "tau", "nu_t", "s_int")


def log_density(d: b0.Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def diagnostics(trace: dict, names) -> dict:
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    quantities = {f"beta[{n}]": trace["beta"][..., j] for j, n in enumerate(names)}
    quantities |= {k: trace[k] for k in ("g", "nu", "tau", "nu_t", "s_int")}
    quantities |= {f"sigma[{i}]": trace["sigma"][..., i] for i in range(4)}
    rows = {
        n: {"rhat": split_rhat(np.asarray(x)), "ess": ess(np.asarray(x))}
        for n, x in quantities.items()
        if np.ptp(x) > 0
    }
    worst = max(rows, key=lambda n: rows[n]["rhat"])
    least = min(rows, key=lambda n: rows[n]["ess"])
    return {
        "per_quantity": rows,
        "max_rhat": rows[worst]["rhat"],
        "max_rhat_name": worst,
        "min_ess": rows[least]["ess"],
        "min_ess_name": least,
        "passes": rows[worst]["rhat"] <= RHAT_GATE and rows[least]["ess"] > ESS_GATE,
    }


def cell_log_premiums(beta: np.ndarray, names) -> dict:
    """Each ladder cell's log premium over a studio with one full bath, per draw: the sum of
    every step at or below the cell. A step the design left out counts as zero."""
    col = {n: j for j, n in enumerate(names)}

    def step(i, j):
        n = f"bed>={i}" if j == 1 else f"full>={j}" if i == 0 else f"bed>={i}&full>={j}"
        return beta[..., col[n]] if n in col else 0.0

    return {
        (b, f): sum(
            step(i, j)
            for i in range(b + 1)
            for j in range(1, f + 1)
            if (i, j) != (0, 1)
        )
        + np.zeros(beta.shape[:-1])
        for b in range(BEDS + 1)
        for f in range(1, BATHS + 1)
    }


def summarize(kept: dict, names) -> dict:
    """Posterior medians and 95% intervals: coefficients as % premiums, every ladder cell as
    its % premium over a studio with one full bath, hyperparameters as they are."""

    def q(x):
        lo, med, hi = np.quantile(np.asarray(x).reshape(-1), [0.025, 0.5, 0.975])
        return {"median": float(med), "lo": float(lo), "hi": float(hi)}

    def pct(x):
        return {k: 100 * math.expm1(v) for k, v in q(x).items()}

    beta = kept["beta"].reshape(-1, kept["beta"].shape[-1])
    coef = {}
    for j, n in enumerate(names):
        if n == "alpha":
            coef[n] = {k: float(math.exp(v)) for k, v in q(beta[:, j]).items()}
        elif n.startswith(("sin", "cos")):
            coef[n] = q(beta[:, j])
        else:
            coef[n] = pct(beta[:, j])
    cells = cell_log_premiums(beta, names)
    hyper = {
        "nu": q(kept["nu"]),
        **{f"sigma[{i}]": q(kept["sigma"][..., i]) for i in range(4)},
        "g_yearly_pct": q(100 * np.expm1(52 * kept["g"])),
        "tau": q(kept["tau"]),
        "nu_t": q(kept["nu_t"]),
        "s_int": q(kept["s_int"]),
    }
    return {
        "coefficients": coef,
        "cells": {f"{b}bed_{f}bath": pct(v) for (b, f), v in cells.items()},
        "hyper": hyper,
    }


def scorecard(summary, season, trend) -> list:
    """The predictions written before B0.2's first full fit (PR #1148), each with the measured
    value and hit or miss. The rest (convergence, PSIS-LOO, coverage, fit time) are in the PR
    and the fit's notes."""
    cells, h = summary["cells"], summary["hyper"]
    rows = []

    def add(n, claim, value, hit):
        rows.append({"n": n, "claim": claim, "value": value, "hit": bool(hit)})

    def ratio(a, b):
        return 100 * (
            (1 + cells[a]["median"] / 100) / (1 + cells[b]["median"] / 100) - 1
        )

    one = cells["1bed_1bath"]["median"]
    add(
        1, "1 bed 1 bath is +15% to +25% over a studio", f"{one:+.1f}%", 15 <= one <= 25
    )
    r = ratio("2bed_1bath", "1bed_1bath")
    add(2, "2 beds 1 bath is -5% to +8% over 1 bed 1 bath", f"{r:+.1f}%", -5 <= r <= 8)
    r = ratio("2bed_2bath", "2bed_1bath")
    add(
        3,
        "2 beds 2 baths is +45% to +80% over 2 beds 1 bath",
        f"{r:+.1f}%",
        45 <= r <= 80,
    )
    r1 = ratio("1bed_2bath", "1bed_1bath")
    r2 = ratio("2bed_2bath", "2bed_1bath")
    add(
        4,
        "the 2nd full bath adds more at 2 beds than at 1 bed",
        f"{r1:+.1f}% at 1 bed, {r2:+.1f}% at 2 beds",
        r2 > r1,
    )
    s = h["s_int"]["median"]
    add(5, "s_int is 0.05 to 0.30", f"{s:.3f}", 0.05 <= s <= 0.30)
    drop = trend["covid_drop_pct"]["median"]
    add(
        6,
        "2020 trough is 20% to 32% below early 2020",
        f"{drop:.1f}%",
        -32 <= drop <= -20,
    )
    g, tau, nt = (h[k]["median"] for k in ("g_yearly_pct", "tau", "nu_t"))
    add(
        7,
        "g +1% to +4% a year, tau 0.0012 to 0.004, nu_T < 2",
        f"g {g:+.2f}%/yr, tau {tau:.4f}, nu_T {nt:.2f}",
        1 <= g <= 4 and 0.0012 <= tau <= 0.004 and nt < 2,
    )
    peak = float(season["days"][np.argmax(np.median(season["curve"], axis=0))])
    month = (pd.Timestamp("2001-01-01") + pd.Timedelta(days=peak)).month
    add(
        8,
        "season peaks May to July",
        f"peak day {peak:.0f} (month {month})",
        5 <= month <= 7,
    )
    return rows


def prior_draws(d: b0.Design, priors: Priors, draws: int, seed: int = 0) -> dict:
    """Parameters drawn from the priors, the trend simulated forward on the grid."""
    rng = np.random.default_rng(seed)
    m_fix, s_fix = prior_arrays(priors, d.names)
    fixed, inter = split_index(d.names)
    beta = np.zeros((draws, len(d.names)))
    beta[:, fixed] = rng.normal(m_fix, s_fix, (draws, len(fixed)))
    s_int = np.abs(rng.normal(0, priors.s_int, draws))
    beta[:, inter] = rng.normal(0, 1, (draws, len(inter))) * s_int[:, None]
    g = rng.normal(*priors.g, draws)
    tau = rng.exponential(priors.tau_u / -math.log(priors.tau_alpha), draws)
    nu_t = np.empty(draws)
    for i in range(draws):
        while (v := rng.gamma(priors.nu_t[0], 1 / priors.nu_t[1])) <= priors.nu_t_min:
            pass
        nu_t[i] = v
    z = rng.standard_t(nu_t[:, None], (draws, d.weeks))
    L = np.concatenate(
        [np.zeros((draws, 1)), np.cumsum(g[:, None] + tau[:, None] * z, axis=1)], axis=1
    )
    nu = rng.gamma(priors.nu[0], 1 / priors.nu[1], draws)
    sigma = np.abs(rng.normal(0, priors.sigma, (draws, 4)))
    return dict(
        beta=beta, g=g, tau=tau, nu_t=nu_t, L=L, nu=nu, sigma=sigma, s_int=s_int
    )


def prior_predictive(d: b0.Design, priors: Priors, draws=200, rows=50_000, seed=0):
    """B0's prior predictive check on B0.2's priors."""
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(d.y), size=min(rows, len(d.y)), replace=False)
    s = b0.subset(d, np.isin(np.arange(len(d.y)), pick))
    pr = prior_draws(s, priors, draws, seed)
    trend = (1 - s.frac) * pr["L"][:, s.week] + s.frac * pr["L"][:, s.week + 1]
    mu = pr["beta"] @ s.x.T + trend
    rent = np.exp(
        mu + rng.standard_t(pr["nu"][:, None], mu.shape) * pr["sigma"][:, s.group]
    )
    q = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    return {
        "draws": draws,
        "rows": len(s.y),
        "rent_quantiles": dict(
            zip(map(str, q), np.quantile(rent, q).round(0).tolist())
        ),
        "share_1000_30000": float(np.mean((rent >= 1000) & (rent <= 30000))),
        "trend_end_quantiles": dict(
            zip(map(str, q), np.quantile(pr["L"][:, -1], q).round(3).tolist())
        ),
    }


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on B0.2's model."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model b0.2`: fit B0.2 on the split's training rows and save it."""
    parser = b0.run_parser()
    parser.prog = "rentfrontier.run --model b0.2"
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


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prior", help="prior predictive check")
    pp.add_argument("dataset", type=Path)
    pp.add_argument("--rows", type=int, default=50_000)
    pp.add_argument("--draws", type=int, default=200)
    args = p.parse_args(argv)
    if args.cmd == "prior":
        frame = b0.load_frame(args.dataset)
        print(
            json.dumps(
                prior_predictive(design(frame), Priors(), args.draws, args.rows),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
