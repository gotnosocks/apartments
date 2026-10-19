"""B0.5: B0.4 with its three hierarchical scales centred.

The model is B0.4's (`rentfrontier.b0_4`), with the same priors and the same data. Only the
parameterization changes, so the prior predictive matches B0.4's. In B0.4's fit, each of the
three scales below sat far above the spread of the coefficients it scales (tau about 0.033
against weekly shocks of sd 0.0045, the surface amplitudes 11.8 and 3.8 against surfaces of
sd 0.18 and 0.19, s_bath 1.26), and the chains could not move it back: lowering a scale under
the non-centred form means scaling all its standard-normal coefficients up together. With
1.9 million rows the data pin down each coefficient, so here I sample the coefficients
themselves and let each scale see them directly:

1. The trend. I sample the weekly levels L_1..L_W (L_0 = 0) and score their steps,
   L_w - L_{w-1} ~ Student-t(nu_t, g, tau). This is B0.4's random walk with drift written on
   the levels; the map from B0.4's z is linear with unit Jacobian. eta = L_w - L_{w-1} - g
   is kept as before.
2. The surfaces. I keep each surface's basis unscaled, Phi_b (sines, centred on the
   borough's row-weighted mean), and sample its coefficients w_bk ~ Normal(0, a_b sqrt(S_k)),
   with sqrt(S_k) the kernel's spectral sd at wave pair k. F_b = Phi_b w_b, the same F as
   B0.4's a_b B_b z_b.
3. The bath steps. Each bedroom level's bath step is sampled directly,
   beta_step ~ Normal(phi_pool, s_bath).

Starting points: the levels start along the prior drift's path, the surface coefficients near
zero and the bath steps at their pool means. The scales start where B0.4's did, except tau,
which starts near 0.005 (B0.4's draws imply about 0.004).

    python -m rentfrontier.b0_5 prior DATASET [--rows N]
    python -m rentfrontier.run --model b0.5 --split latest --name NAME [--chains 16 ...]

`rentfrontier.loo` does not score B0.5 runs yet, for the same reason as B0.4.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
from pathlib import Path

import numpy as np

from . import b0, b0_1, b0_3, b0_4

NAME = "b0.5"
Priors = b0_4.Priors
Design = b0_4.Design
subset = b0_4.subset
prior_arrays = b0_4.prior_arrays
summarize = b0_4.summarize


def spectral_sd(shape: dict) -> np.ndarray:
    """sqrt(S_k) at each of a surface's wave pairs, in its basis's column order."""
    (Lu, Lv), (mu_, mv) = shape["half_width_km"], shape["waves"]
    wu = np.pi * np.arange(1, mu_ + 1) / (2 * Lu)
    wv = np.pi * np.arange(1, mv + 1) / (2 * Lv)
    l2 = b0_4.LENGTHSCALE**2
    w2 = wu[:, None] ** 2 + wv[None, :] ** 2
    return np.sqrt(2 * np.pi * l2 * np.exp(-l2 * w2 / 2)).reshape(-1)


def design(frame, start=None, registry=None) -> Design:
    """B0.4's design, with each surface's basis divided back by its spectral sd and the sd
    kept beside it."""
    d = b0_4.design(frame, start, registry)
    surfaces = []
    for s in d.surfaces:
        sd = spectral_sd(s)
        surfaces.append(s | {"basis": s["basis"] / sd, "sd": sd})
    return dataclasses.replace(d, surfaces=surfaces)


def run_record(d: Design) -> dict:
    """B0.4's record of the surfaces, without the spectral sds."""
    out = b0_4.run_record(
        dataclasses.replace(
            d, surfaces=[{k: v for k, v in s.items() if k != "sd"} for s in d.surfaces]
        )
    )
    return out


def model(d: Design, priors: Priors):
    """The B0.5 model of design `d` as a NumPyro model function of no arguments."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    W = d.weeks
    m_fix, s_fix = prior_arrays(priors, d.names)
    fixed, steps, pools = b0_3.split_index(d.names)
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    x = jnp.asarray(d.x)
    y = jnp.asarray(d.y)
    group = jnp.asarray(d.group)
    week = jnp.asarray(d.week)
    frac = jnp.asarray(d.frac)
    site = jnp.asarray(d.site)
    pools = jnp.asarray(pools)
    bases = [jnp.asarray(s["basis"]) for s in d.surfaces]
    sds = jnp.concatenate([jnp.asarray(s["sd"]) for s in d.surfaces])
    which = jnp.asarray(
        np.concatenate([np.full(len(s["sd"]), k) for k, s in enumerate(d.surfaces)])
    )
    ends = np.cumsum([0] + [s["basis"].shape[1] for s in d.surfaces])

    def fn():
        main = numpyro.sample("main", dist.Normal(m_fix, s_fix).to_event(1))
        phi = numpyro.sample(
            "phi", dist.Normal(*priors.bath).expand([len(b0_3.POOLS)]).to_event(1)
        )
        s_bath = numpyro.sample("s_bath", dist.HalfNormal(priors.s_bath))
        bath = numpyro.sample("bath", dist.Normal(phi[pools], s_bath).to_event(1))
        beta = jnp.zeros(len(d.names)).at[fixed].set(main).at[steps].set(bath)
        numpyro.deterministic("beta", beta)
        amp = numpyro.sample(
            "amp", dist.HalfNormal(priors.amp).expand([len(bases)]).to_event(1)
        )
        w = numpyro.sample("gp_w", dist.Normal(0, amp[which] * sds).to_event(1))
        F = jnp.concatenate(
            [B @ w[ends[k] : ends[k + 1]] for k, B in enumerate(bases)] + [jnp.zeros(1)]
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
        level = numpyro.sample(
            "level", dist.ImproperUniform(constraints.real, (), (W,))
        )
        L = jnp.concatenate([jnp.zeros(1), level])
        numpyro.factor("walk", dist.StudentT(nu_t, g, tau).log_prob(jnp.diff(L)).sum())
        numpyro.deterministic("L", L)
        numpyro.deterministic("eta", jnp.diff(L) - g)
        mu = x @ beta + F[site] + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def initial_values(d: Design, priors: Priors, chains: int, seed: int) -> dict:
    """B0.4's starting points moved to the centred sites: the levels near the drift's path,
    the surface coefficients and bath steps near zero and their pool means, tau near 0.005."""
    rng = np.random.default_rng(seed)
    out = b0_4.initial_values(d, priors, chains, seed)
    _, steps, pools = b0_3.split_index(d.names)
    del out["z"], out["gp_z"], out["bath_z"]
    out["bath"] = out["phi"][:, pools] + 0.01 * rng.standard_normal(
        (chains, len(steps))
    )
    out["gp_w"] = 0.001 * rng.standard_normal(
        (chains, sum(len(s["sd"]) for s in d.surfaces))
    )
    out["tau"] = np.log(0.005) + 0.3 * rng.standard_normal(chains)
    path = priors.g[0] * np.arange(1, d.weeks + 1)
    out["level"] = path + 0.001 * rng.standard_normal((chains, d.weeks))
    return out


KEPT = b0_3.KEPT + ("amp", "gp_w")
TRACED = b0_4.TRACED
PROGRESS = b0_3.PROGRESS + ("amp",)


def log_density(d: Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


diagnostics = b0_4.diagnostics


def surface_draws(d: Design, kept: dict) -> np.ndarray:
    """F at every building per kept draw, (..., buildings + 1); the last column is the zero
    of buildings with no surface."""
    w = np.asarray(kept["gp_w"])
    parts, at = [], 0
    for s in d.surfaces:
        n = s["basis"].shape[1]
        parts.append(w[..., at : at + n] @ s["basis"].T)
        at += n
    parts.append(np.zeros(w.shape[:-1] + (1,)))
    return np.concatenate(parts, axis=-1)


def prior_draws(d: Design, priors: Priors, draws: int, seed: int = 0) -> dict:
    """B0.4's prior draws, with the surface coefficients drawn on the centred scale."""
    rng = np.random.default_rng(seed + 1)
    out = b0_4.prior_draws(dataclasses.replace(d, surfaces=[]), priors, draws, seed)
    amp = np.abs(rng.normal(0, priors.amp, (draws, len(d.surfaces))))
    w = np.concatenate(
        [
            rng.normal(0, 1, (draws, len(s["sd"]))) * s["sd"] * amp[:, k, None]
            for k, s in enumerate(d.surfaces)
        ],
        axis=1,
    )
    out["F"] = surface_draws(d, {"gp_w": w})
    return out


def prior_predictive(d: Design, priors: Priors, draws=200, rows=50_000, seed=0):
    """B0.4's prior predictive check on B0.5's prior draws: rent quantiles, and the spread of
    each surface across its buildings."""
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(d.y), size=min(rows, len(d.y)), replace=False)
    s = subset(d, np.isin(np.arange(len(d.y)), pick))
    pr = prior_draws(s, priors, draws, seed)
    trend = (1 - s.frac) * pr["L"][:, s.week] + s.frac * pr["L"][:, s.week + 1]
    mu = pr["beta"] @ s.x.T + trend + pr["F"][:, s.site]
    rent = np.exp(
        mu + rng.standard_t(pr["nu"][:, None], mu.shape) * pr["sigma"][:, s.group]
    )
    q = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    spread = {}
    for surf in s.surfaces:
        sd = pr["F"][:, surf["first"] : surf["first"] + surf["sites"]].std(1)
        spread[surf["name"]] = dict(
            zip(map(str, q), np.quantile(sd, q).round(3).tolist())
        )
    return {
        "draws": draws,
        "rows": len(s.y),
        "rent_quantiles": dict(
            zip(map(str, q), np.quantile(rent, q).round(0).tolist())
        ),
        "share_1000_30000": float(np.mean((rent >= 1000) & (rent <= 30000))),
        "surface_sd_quantiles": spread,
        "surfaces": run_record(s)["surfaces"],
    }


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on B0.5's model."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model b0.5`: fit B0.5 on the split's training rows and save it."""
    parser = b0.run_parser()
    parser.prog = "rentfrontier.run --model b0.5"
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
