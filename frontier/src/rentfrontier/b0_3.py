"""B0.3: B0.2 with its bedroom-by-bath ladder anchored on each bedroom level's usual bath count.

For row i, with y_i the log of its net-effective latest ask, dated at its latest ask's day t_i:

    y_i = alpha + Ladder_i + Half_i + T(t_i) + Season(t_i) + Flags_i + e_i,
    e_i ~ Student-t(nu, 0, sigma_g(i)), one sigma per bedroom group (studio, 1, 2, 3+).

Everything outside the ladder is B0.2's (`rentfrontier.b0_2`): the random-walk trend with
Student-t shocks, the half bath, season, flags and errors.

The ladder. B0.2 measured every bath step on studios, where a second full bath is rare (0.5%
of studio ads). I measure bath steps instead against the bath count most ads at each bedroom
level have. The modal count, from the 2026-10-19 off-market rows, is one full bath for
studios through 3 bedrooms and two for 4 and 5+ bedrooms (MODAL). A cell (b, f) has
bedrooms b (0 to 5, 5 or more capped at 5) and full baths f (1 to 4, 4 or more capped at 4,
none counted as 1). As in B0, an ad with no full-bath count goes into the 1-bath cell of its
bedroom level, with B0's `bath_unknown` step on top. A cell's mean comes in two parts:

    Ladder(b, f) = Spine(b) + Bath_b(f)

1. Spine(b) adds up the bedroom steps bed>=1 .. bed>=b along the modal path. bed>=i is the
   step from (i - 1) bedrooms at their usual bath count to i bedrooms at theirs, so bed>=4
   moves from 3 bedrooms with one bath to 4 bedrooms with two.
2. Bath_b(f) is zero at the modal count m(b). Above it I add up the steps theta_{b,j} for
   m(b) < j <= f, the column `bed=b:full>=j`, set to 1 for ads at b bedrooms with j or more
   full baths. Below it, at 4 and 5+ bedrooms with one bath, I subtract theta_{b,2}, the
   step up from one bath to two, so its column `bed=b:full>=2` is -1 for those ads. Every
   step keeps the step-up sign: a positive theta means the cell with more baths rents for
   more.

I pool the bath steps across bedroom levels by their position against the modal count:
`bath+1` for the first bath above it, `bath+2` and `bath+3` for the next, and `bath-1` for
the step up into the modal count from one below. Each step varies around its pool's shared
value, theta_{b,j} = phi_k + s_bath u_{b,j} with u_{b,j} ~ Normal(0, 1), non-centered, as
B0.2 sampled its interaction steps. The shared phi_k keep B0's bath prior, Normal(0.1, 0.2),
and s_bath ~ HalfNormal(0.1). When a level holds few ads off its modal count, its steps fall
back toward the shared ones, which every level informs in proportion to its ads.

The ladder still has 24 cells and 24 steps, so it can fit every cell's mean, and with flat
priors B0.2 and B0.3 would agree on every cell. They differ in what the shrinkage pulls
toward: B0.2 pulled its bath steps toward the studio's, and B0.3 pulls them toward a step
shared across bedroom levels, measured off the modal path.

    python -m rentfrontier.b0_3 prior DATASET [--rows N]
    python -m rentfrontier.run --model b0.3 --split latest --name NAME [--chains 16 ...]
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

from . import b0, b0_1, b0_2

NAME = "b0.3"
BEDS = b0_2.BEDS
BATHS = b0_2.BATHS
MODAL = {
    0: 1,
    1: 1,
    2: 1,
    3: 1,
    4: 2,
    5: 2,
}  # the most common full-bath count per level
POOLS = ("bath-1", "bath+1", "bath+2", "bath+3")


@dataclass(frozen=True)
class Priors:
    alpha: tuple = b0.Priors.alpha
    bed: tuple = b0.Priors.bed
    bath: tuple = b0.Priors.bath  # the shared bath steps phi_k
    half: tuple = b0.Priors.half
    bath_unknown: tuple = b0.Priors.bath_unknown
    season: tuple = b0.Priors.season
    flag: tuple = b0.Priors.flag
    s_bath: float = (
        0.1  # HalfNormal scale of the bath steps' spread across bedroom levels
    )
    g: tuple = b0.Priors.g
    tau_u: float = b0_2.Priors.tau_u
    tau_alpha: float = b0_2.Priors.tau_alpha
    nu: tuple = b0.Priors.nu
    nu_t: tuple = b0.Priors.nu_t
    nu_t_min: float = b0.Priors.nu_t_min
    sigma: float = b0.Priors.sigma

    def to_dict(self):
        return dataclasses.asdict(self)


def bath_step(b, j):
    """The column name of the step up to j full baths at b bedrooms."""
    return f"bed={b}:full>={j}"


def is_bath_step(name):
    return name.startswith("bed=")


def pool(name):
    """The shared step a bath step varies around, by its place against the modal count."""
    b, j = (int(p.split("=")[-1]) for p in name.split(":"))
    k = j - MODAL[b]
    return "bath-1" if k <= 0 else f"bath+{k}"


def design(frame: pd.DataFrame, start: pd.Timestamp | None = None) -> b0.Design:
    """B0's design of `frame` with its full>= columns replaced by the bath steps of each
    bedroom level, placed after the bedroom steps. I leave out a bath step no row sets."""
    d = b0.design(frame, start)
    beds = np.minimum(np.clip(np.round(frame.bedrooms.to_numpy(float)), 0, None), BEDS)
    full = frame.full_baths.to_numpy(float)
    known = ~np.isnan(full)
    full = np.clip(np.nan_to_num(full, nan=1.0), 1, BATHS)
    keep = [j for j, n in enumerate(d.names) if not n.startswith("full>=")]
    names = [d.names[j] for j in keep]
    count = {n: c for n, c in d.count.items() if not n.startswith("full>=")}
    at = 1 + max((j for j, n in enumerate(names) if n.startswith("bed>=")), default=0)
    new, new_names = [], []
    for b in range(BEDS + 1):
        at_b = known & (beds == b)
        for j in range(2, BATHS + 1):
            if j > MODAL[b]:
                col = (at_b & (full >= j)).astype(float)
            else:
                col = -((beds == b) & (~known | (full < j))).astype(float)
            n = bath_step(b, j)
            count[n] = int(np.abs(col).sum())
            if count[n] > 0:
                new.append(col)
                new_names.append(n)
    x = d.x[:, keep]
    new = np.stack(new, axis=1) if new else np.zeros((len(x), 0))
    x = np.hstack([x[:, :at], new, x[:, at:]])
    names = names[:at] + new_names + names[at:]
    return dataclasses.replace(d, x=x, names=names, count=count)


def prior_arrays(priors: Priors, names):
    """Means and sds of the coefficients outside the bath steps, in `names` order."""
    return b0.prior_arrays(priors, [n for n in names if not is_bath_step(n)])


def split_index(names):
    """Positions of the other coefficients and of the bath steps in `names`, and each bath
    step's pool as an index into POOLS."""
    steps = np.array([j for j, n in enumerate(names) if is_bath_step(n)], dtype=int)
    fixed = np.array([j for j, n in enumerate(names) if not is_bath_step(n)], dtype=int)
    pools = np.array([POOLS.index(pool(names[j])) for j in steps], dtype=int)
    return fixed, steps, pools


def model(d: b0.Design, priors: Priors):
    """The B0.3 model of design `d` as a NumPyro model function of no arguments."""
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
    log rent, the shared bath steps at their prior mean, and each level's bath steps near
    them."""
    rng = np.random.default_rng(seed)
    m_fix, _ = prior_arrays(priors, d.names)
    _, steps, _ = split_index(d.names)
    main = np.tile(m_fix, (chains, 1))
    main[:, 0] = np.mean(d.y)
    main += 0.01 * rng.standard_normal(main.shape)
    nu_t = 2.0 * np.exp(0.2 * rng.standard_normal(chains))
    return {
        "main": main,
        "phi": priors.bath[0] + 0.01 * rng.standard_normal((chains, len(POOLS))),
        "s_bath": np.log(0.1) + 0.3 * rng.standard_normal(chains),
        "bath_z": 0.1 * rng.standard_normal((chains, len(steps))),
        "g": np.full(chains, priors.g[0]),
        "tau": np.log(0.002) + 0.3 * rng.standard_normal(chains),
        "nu_t": np.log(nu_t - priors.nu_t_min),
        "nu": np.log(10) + 0.3 * rng.standard_normal(chains),
        "sigma": np.log(0.3) + 0.2 * rng.standard_normal((chains, 4)),
        "z": 0.1 * rng.standard_normal((chains, d.weeks)),
    }


KEPT = ("beta", "g", "L", "nu", "sigma", "tau", "nu_t", "eta", "phi", "s_bath")
TRACED = ("beta", "g", "nu", "sigma", "tau", "nu_t", "phi", "s_bath")
PROGRESS = ("nu", "tau", "nu_t", "s_bath")


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
    quantities |= {f"phi[{p}]": trace["phi"][..., k] for k, p in enumerate(POOLS)}
    quantities |= {k: trace[k] for k in ("g", "nu", "tau", "nu_t", "s_bath")}
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
    """Each ladder cell's log premium over a studio with one full bath, per draw: the spine
    up to its bedroom level plus its bath steps away from the modal count. A step the design
    left out counts as zero."""
    col = {n: j for j, n in enumerate(names)}

    def get(n):
        return beta[..., col[n]] if n in col else 0.0

    cells = {}
    for b in range(BEDS + 1):
        spine = sum(get(f"bed>={i}") for i in range(1, b + 1)) + np.zeros(
            beta.shape[:-1]
        )
        m = MODAL[b]
        for f in range(1, BATHS + 1):
            up = sum(get(bath_step(b, j)) for j in range(m + 1, f + 1))
            down = sum(get(bath_step(b, j)) for j in range(f + 1, m + 1))
            cells[(b, f)] = spine + up - down
    return cells


def modal_contrasts(cells: dict) -> dict:
    """Log contrasts along and off the modal path, per draw, from any model's cells: each
    bedroom step between modal cells, and one bath above or below the modal count at each
    bedroom level."""
    out = {}
    for b in range(1, BEDS + 1):
        out[f"bed {b - 1}->{b} on modal path"] = (
            cells[(b, MODAL[b])] - cells[(b - 1, MODAL[b - 1])]
        )
    for b in range(BEDS + 1):
        m = MODAL[b]
        if m + 1 <= BATHS:
            out[f"{b} bed: +1 full bath over {m}"] = cells[(b, m + 1)] - cells[(b, m)]
        if m - 1 >= 1:
            out[f"{b} bed: -1 full bath from {m}"] = cells[(b, m - 1)] - cells[(b, m)]
    return out


def summarize(kept: dict, names) -> dict:
    """Posterior medians and 95% intervals: coefficients and the shared bath steps as %
    premiums, every ladder cell as its % premium over a studio with one full bath, the
    modal-path contrasts in %, hyperparameters as they are."""

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
    phi = np.asarray(kept["phi"]).reshape(-1, len(POOLS))
    cells = cell_log_premiums(beta, names)
    hyper = {
        "nu": q(kept["nu"]),
        **{f"sigma[{i}]": q(kept["sigma"][..., i]) for i in range(4)},
        "g_yearly_pct": q(100 * np.expm1(52 * kept["g"])),
        "tau": q(kept["tau"]),
        "nu_t": q(kept["nu_t"]),
        "s_bath": q(kept["s_bath"]),
    }
    return {
        "coefficients": coef,
        "shared_bath_steps": {p: pct(phi[:, k]) for k, p in enumerate(POOLS)},
        "cells": {f"{b}bed_{f}bath": pct(v) for (b, f), v in cells.items()},
        "modal_contrasts": {k: pct(v) for k, v in modal_contrasts(cells).items()},
        "hyper": hyper,
    }


def scorecard(summary, season, trend) -> list:
    """The predictions written before B0.3's first full fit (PR #1149), each with the measured
    value and hit or miss. The rest (convergence, PSIS-LOO, coverage, fit time) are in the PR
    and the fit's notes."""
    c, shared, h = (
        summary["modal_contrasts"],
        summary["shared_bath_steps"],
        summary["hyper"],
    )
    rows = []

    def add(n, claim, value, hit):
        rows.append({"n": n, "claim": claim, "value": value, "hit": bool(hit)})

    one = c["bed 0->1 on modal path"]["median"]
    add(1, "1 bed is +15% to +25% over a studio", f"{one:+.1f}%", 15 <= one <= 25)
    two = c["bed 1->2 on modal path"]["median"]
    add(2, "2 beds is -5% to +8% over 1 bed, at 1 bath", f"{two:+.1f}%", -5 <= two <= 8)
    p1 = shared["bath+1"]["median"]
    add(3, "the shared step to one bath above the usual is +25% to +60%",
        f"{p1:+.1f}%", 25 <= p1 <= 60)  # fmt: skip
    r2 = c["2 bed: +1 full bath over 1"]["median"]
    add(4, "2 beds: a 2nd full bath adds +45% to +80%", f"{r2:+.1f}%", 45 <= r2 <= 80)
    r4 = c["4 bed: -1 full bath from 2"]["median"]
    add(5, "4 beds with 1 bath rent 10% to 35% below 4 beds with 2",
        f"{r4:+.1f}%", -35 <= r4 <= -10)  # fmt: skip
    s = h["s_bath"]["median"]
    add(6, "s_bath is 0.05 to 0.40", f"{s:.3f}", 0.05 <= s <= 0.40)
    drop = trend["covid_drop_pct"]["median"]
    add(
        7,
        "2020 trough is 20% to 32% below early 2020",
        f"{drop:.1f}%",
        -32 <= drop <= -20,
    )
    g, tau, nt = (h[k]["median"] for k in ("g_yearly_pct", "tau", "nu_t"))
    add(
        8,
        "g +1% to +4% a year, tau 0.0012 to 0.004, nu_T < 2",
        f"g {g:+.2f}%/yr, tau {tau:.4f}, nu_T {nt:.2f}",
        1 <= g <= 4 and 0.0012 <= tau <= 0.004 and nt < 2,
    )
    peak = float(season["days"][np.argmax(np.median(season["curve"], axis=0))])
    month = (pd.Timestamp("2001-01-01") + pd.Timedelta(days=peak)).month
    add(
        9,
        "season peaks May to July",
        f"peak day {peak:.0f} (month {month})",
        5 <= month <= 7,
    )
    return rows


def prior_draws(d: b0.Design, priors: Priors, draws: int, seed: int = 0) -> dict:
    """Parameters drawn from the priors, the trend simulated forward on the grid."""
    rng = np.random.default_rng(seed)
    m_fix, s_fix = prior_arrays(priors, d.names)
    fixed, steps, pools = split_index(d.names)
    beta = np.zeros((draws, len(d.names)))
    beta[:, fixed] = rng.normal(m_fix, s_fix, (draws, len(fixed)))
    phi = rng.normal(*priors.bath, (draws, len(POOLS)))
    s_bath = np.abs(rng.normal(0, priors.s_bath, draws))
    beta[:, steps] = (
        phi[:, pools] + rng.normal(0, 1, (draws, len(steps))) * s_bath[:, None]
    )
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
    return dict(beta=beta, g=g, tau=tau, nu_t=nu_t, L=L, nu=nu, sigma=sigma)


def prior_predictive(d: b0.Design, priors: Priors, draws=200, rows=50_000, seed=0):
    """B0's prior predictive check on B0.3's priors."""
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
    """B0.1's ChEES-HMC on B0.3's model."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model b0.3`: fit B0.3 on the split's training rows and save it."""
    parser = b0.run_parser()
    parser.prog = "rentfrontier.run --model b0.3"
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
