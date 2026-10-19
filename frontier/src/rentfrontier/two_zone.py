"""Two-zone location: the normal walk with a rent surface on each side of the East River.

I keep the normal walk (`rentfrontier.normal_walk`) as it is and add one term to each row's
mean, the surface F(s) at its building s. There is no borough intercept or offset.

The zones. I place each building at its registry coordinates (REGISTRY) and split the
buildings by the first digit of the lot's BBL: 1 is the Manhattan zone, and every other
located building (Brooklyn and the few Queens ones) is the outer zone. The zone only picks
which surface a building sits on. With the 2026-10-19 snapshot every building of the B0
rows has a lot and a point, so I give the model no term for an unlocated building, and the
design stops with an error on any row whose building lacks one.

The surfaces. Each zone has its own Gaussian process with a squared-exponential kernel of
amplitude a_z and length-scale 500 m, approximated with the Hilbert-space basis as in B0.4
(`rentfrontier.b0_4`). For a zone I:

1. project the buildings to kilometres east and north of LAT0, LON0;
2. turn them by the angle in [0, 90) degrees, on a half-degree grid, that gives the smallest
   box spanning the 0.1% to 99.9% quantiles of each axis;
3. widen that box by C = 1.5 and take B0.4's wave count on each axis, ceil(1.75 C S / l),
   so the resolution per kilometre stays B0.4's;
4. sample each coefficient directly, w_j ~ Normal(0, a_z sqrt(S(omega_j))), with sqrt(S)
   the kernel's spectral sd at unit amplitude. B0.4 sampled a_z sqrt(S) z with z standard
   normal, and its amplitudes stuck at 11.8 and 3.8 over surfaces of sd 0.18 and 0.19.

The level. With no intercept, a shift of both surfaces together would trade against the
walk's level. So I subtract from F its row-weighted mean over the located buildings of the
training rows. The walk then carries the overall level, and the gap between the zones'
row-weighted means of F carries Manhattan's level against the outer zone's.

I save the zones' row-weighted means of F (`zone_level`) and the spread of F across each
zone's buildings (`zone_sd`) with every kept draw.

    python -m rentfrontier.two_zone prior DATASET [--rows N]
    python -m rentfrontier.run --model two-zone --split latest --name NAME [--chains 16 ...]

`rentfrontier.loo` does not score these runs yet: its scoring reads the fixed design alone.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, b0_1, b0_3, b0_4, normal_walk
from .normal_walk import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    cell_log_premiums,
    modal_contrasts,
    prior_arrays,
    split_index,
)
from .registry import EXTERNAL_ROOT
from .total_walk import SEASON, grid_season

NAME = "two-zone"
REGISTRY = Path(
    os.environ.get(
        "FRONTIER_TWO_ZONE_REGISTRY",
        EXTERNAL_ROOT / "registry" / "20261019-bcfbb52-extend" / "registry.parquet",
    )
)
ZONES = ("manhattan", "outer")
LENGTHSCALE = b0_4.LENGTHSCALE
KEPT = normal_walk.KEPT + ("amp", "gp_w", "zone_level", "zone_sd")
TRACED = normal_walk.TRACED + ("amp", "zone_level")
PROGRESS = normal_walk.PROGRESS + ("amp",)
Design = b0_4.Design
subset = b0_4.subset


@dataclass(frozen=True)
class Priors(normal_walk.Priors):
    amp: float = 0.3  # HalfNormal scale of each zone's amplitude


def rotation(x: np.ndarray, y: np.ndarray, step: float = 0.5) -> float:
    """The angle in [0, 90) degrees that gives the smallest quantile box of the points."""
    best, angle = math.inf, 0.0
    for a in np.arange(0.0, 90.0, step):
        t = math.radians(a)
        u = x * math.cos(t) - y * math.sin(t)
        v = x * math.sin(t) + y * math.cos(t)
        area = np.ptp(np.quantile(u, [0.001, 0.999])) * np.ptp(
            np.quantile(v, [0.001, 0.999])
        )
        if area < best - 1e-12:
            best, angle = area, float(a)
    return angle


def box(u: np.ndarray, lengthscale: float) -> tuple[float, float, int]:
    """B0.4's box on one axis (`b0_4.box`) at the given length-scale: the centre, widened
    half-width L and wave count."""
    lo, hi = np.quantile(u, [0.001, 0.999])
    S = max((hi - lo) / 2, lengthscale)
    return (
        float((lo + hi) / 2),
        float(b0_4.C * S),
        int(math.ceil(1.75 * b0_4.C * S / lengthscale)),
    )


def zone_basis(x: np.ndarray, y: np.ndarray, lengthscale: float = LENGTHSCALE):
    """A zone's unscaled HSGP basis at its buildings, the spectral sd of each column, and the
    box it spans."""
    angle = rotation(x, y)
    t = math.radians(angle)
    u = x * math.cos(t) - y * math.sin(t)
    v = x * math.sin(t) + y * math.cos(t)
    cu, Lu, mu_ = box(u, lengthscale)
    cv, Lv, mv = box(v, lengthscale)
    u = np.clip(u - cu, -Lu, Lu)
    v = np.clip(v - cv, -Lv, Lv)
    clipped = int(np.sum((np.abs(u) >= Lu) | (np.abs(v) >= Lv)))
    pu, wu = b0_4.waves(u, Lu, mu_)
    pv, wv = b0_4.waves(v, Lv, mv)
    l2 = lengthscale**2
    w2 = wu[:, None] ** 2 + wv[None, :] ** 2
    sd = np.sqrt(2 * np.pi * l2 * np.exp(-l2 * w2 / 2)).reshape(-1)
    B = (pu[:, :, None] * pv[:, None, :]).reshape(len(u), -1)
    shape = {
        "angle": angle,
        "centre_km": [cu, cv],
        "half_width_km": [Lu, Lv],
        "box_km": [2 * Lu, 2 * Lv],
        "waves": [mu_, mv],
        "clipped": clipped,
        "lengthscale_km": lengthscale,
    }
    return B, sd, shape


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
    lengthscale: float = LENGTHSCALE,
) -> Design:
    """The normal walk's design of `frame`, with each row's building placed on its zone's
    surface."""
    d = b0_3.design(frame, start)
    if registry is None:
        registry = pd.read_parquet(
            REGISTRY, columns=["building", "bbl", "latitude", "longitude"]
        )
    sites = b0_4.sites_of(frame, registry)
    zone = pd.Series(
        np.where(sites.boro.isna(), None, np.where(sites.boro == "1", 0, 1)),
        index=sites.index,
        dtype=object,
    )
    unlocated = frame.building.map(zone).isna().to_numpy()
    if unlocated.any():
        lost = frame.building[unlocated].unique()
        raise ValueError(
            f"{unlocated.sum()} rows in {len(lost)} buildings have no registry point,"
            f" e.g. {list(lost[:5])}"
        )
    surfaces, first, index = [], 0, {}
    for k, name in enumerate(ZONES):
        on = sites[zone == k]
        if len(on) == 0:
            continue
        B, sd, shape = zone_basis(on.x.to_numpy(), on.y.to_numpy(), lengthscale)
        surfaces.append(
            {
                "name": name,
                "basis": B,
                "sd": sd,
                "first": first,
                "sites": len(on),
                **shape,
            }
        )
        index |= dict(zip(on.index, range(first, first + len(on))))
        first += len(on)
    site = frame.building.map(index).to_numpy().astype(np.int64)
    return Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(b0.Design)},
        site=site,
        surfaces=surfaces,
    )


def run_record(d: Design) -> dict:
    """The zones' boxes and basis sizes, for the run's result.json."""
    return {
        "surfaces": [
            {k: v for k, v in s.items() if k not in ("basis", "sd")}
            | {"basis": s["basis"].shape[1]}
            for s in d.surfaces
        ],
        "lengthscale_km": d.surfaces[0]["lengthscale_km"],
        "registry": str(REGISTRY),
    }


def site_share(d: Design) -> np.ndarray:
    """Each located building's share of the rows of `d` that sit on a surface."""
    n = sum(s["sites"] for s in d.surfaces)
    rows = np.bincount(d.site, minlength=n).astype(float)
    return rows / max(rows.sum(), 1.0)


def model(d: Design, priors: Priors):
    """The model of design `d` as a NumPyro model function of no arguments."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    W = d.weeks
    m_fix, s_fix = normal_walk.prior_arrays(priors, d.names)
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
    site = jnp.asarray(d.site)
    B = jnp.asarray(grid_season(d))
    season = jnp.asarray([d.names.index(n) for n in SEASON])
    bases = [jnp.asarray(s["basis"]) for s in d.surfaces]
    sds = jnp.concatenate([jnp.asarray(s["sd"]) for s in d.surfaces])
    which = jnp.asarray(
        np.concatenate([np.full(len(s["sd"]), k) for k, s in enumerate(d.surfaces)])
    )
    ends = np.cumsum([0] + [s["basis"].shape[1] for s in d.surfaces])
    share = site_share(d)
    zone_share = [
        share[s["first"] : s["first"] + s["sites"]]
        / max(share[s["first"] : s["first"] + s["sites"]].sum(), 1e-300)
        for s in d.surfaces
    ]
    share = jnp.asarray(share)
    zone_share = [jnp.asarray(z) for z in zone_share]

    def fn():
        main = numpyro.sample("main", dist.Normal(m_fix[keep], s_fix[keep]).to_event(1))
        theta = numpyro.sample(
            "bath", dist.Normal(*priors.bath).expand([len(steps)]).to_event(1)
        )
        amp = numpyro.sample(
            "amp", dist.HalfNormal(priors.amp).expand([len(bases)]).to_event(1)
        )
        w = numpyro.sample("gp_w", dist.Normal(0, amp[which] * sds).to_event(1))
        F = jnp.concatenate(
            [Bk @ w[ends[k] : ends[k + 1]] for k, Bk in enumerate(bases)]
        )
        F = F - share @ F
        parts = [F[s["first"] : s["first"] + s["sites"]] for s in d.surfaces]
        numpyro.deterministic(
            "zone_level", jnp.stack([z @ p for z, p in zip(zone_share, parts)])
        )
        numpyro.deterministic("zone_sd", jnp.stack([p.std() for p in parts]))
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
        mu = x @ beta + F[site] + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def initial_values(d: Design, priors: Priors, chains: int, seed: int) -> dict:
    """The normal walk's starting points, with each zone's amplitude near 0.1 and its
    coefficients near zero."""
    rng = np.random.default_rng(seed + 7)
    out = normal_walk.initial_values(d, priors, chains, seed)
    k = sum(s["basis"].shape[1] for s in d.surfaces)
    out["amp"] = np.log(0.1) + 0.3 * rng.standard_normal((chains, len(d.surfaces)))
    out["gp_w"] = 0.001 * rng.standard_normal((chains, k))
    return out


def log_density(d: Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def diagnostics(trace: dict, names) -> dict:
    """The normal walk's convergence table, with each zone's amplitude and level and the gap
    between the levels."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = normal_walk.diagnostics(trace, names)
    rows = out["per_quantity"]
    extra = {}
    for k in range(np.shape(trace["amp"])[-1]):
        extra[f"amp[{ZONES[k]}]"] = np.asarray(trace["amp"])[..., k]
        extra[f"zone_level[{ZONES[k]}]"] = np.asarray(trace["zone_level"])[..., k]
    if np.shape(trace["zone_level"])[-1] == 2:
        z = np.asarray(trace["zone_level"])
        extra["zone_gap"] = z[..., 0] - z[..., 1]
    for n, x in extra.items():
        if np.ptp(x) > 0:
            rows[n] = {"rhat": split_rhat(x), "ess": ess(x)}
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


def _q(v) -> dict:
    v = np.asarray(v).reshape(-1)
    lo, med, hi = np.quantile(v, [0.025, 0.5, 0.975])
    return {"median": float(med), "lo": float(lo), "hi": float(hi)}


def summarize(kept: dict, names) -> dict:
    """The normal walk's summary, with each zone's amplitude, level and spread, and
    Manhattan's level against the outer zone's as a % premium."""
    out = normal_walk.summarize(kept, names)
    amp, level, sd = (np.asarray(kept[k]) for k in ("amp", "zone_level", "zone_sd"))
    zones = {}
    for k in range(amp.shape[-1]):
        zones[ZONES[k]] = {
            "amp": _q(amp[..., k]),
            "level": _q(level[..., k]),
            "sd": _q(sd[..., k]),
        }
    out["zones"] = zones
    if level.shape[-1] == 2:
        out["manhattan_over_outer_pct"] = _q(
            100 * np.expm1(level[..., 0] - level[..., 1])
        )
    return out


def surface_draws(d: Design, kept: dict) -> np.ndarray:
    """F at every building per kept draw, (..., buildings), centred as in the model."""
    w = np.asarray(kept["gp_w"])
    parts, at = [], 0
    for s in d.surfaces:
        n = s["basis"].shape[1]
        parts.append(w[..., at : at + n] @ s["basis"].T)
        at += n
    F = np.concatenate(parts, axis=-1)
    return F - (F @ site_share(d))[..., None]


def prior_draws(d: Design, priors: Priors, draws: int, seed: int = 0) -> dict:
    """Parameters drawn from the priors, the walk simulated forward on the grid with Normal
    shocks, and the surfaces at every building."""
    rng = np.random.default_rng(seed)
    m_fix, s_fix = normal_walk.prior_arrays(priors, d.names)
    fixed, steps, _ = split_index(d.names)
    beta = np.zeros((draws, len(d.names)))
    beta[:, fixed] = rng.normal(m_fix, s_fix, (draws, len(fixed)))
    beta[:, steps] = rng.normal(*priors.bath, (draws, len(steps)))
    g = rng.normal(*priors.g, draws)
    tau = rng.exponential(priors.tau_u / -math.log(priors.tau_alpha), draws)
    shocks = g[:, None] + tau[:, None] * rng.standard_normal((draws, d.weeks))
    L = np.concatenate([np.zeros((draws, 1)), np.cumsum(shocks, axis=1)], axis=1)
    nu = rng.gamma(priors.nu[0], 1 / priors.nu[1], draws)
    sigma = np.abs(rng.normal(0, priors.sigma, (draws, 4)))
    amp = np.abs(rng.normal(0, priors.amp, (draws, len(d.surfaces))))
    w = np.concatenate(
        [
            rng.normal(0, 1, (draws, len(s["sd"]))) * s["sd"] * amp[:, k, None]
            for k, s in enumerate(d.surfaces)
        ],
        axis=1,
    )
    F = surface_draws(d, {"gp_w": w})
    return dict(beta=beta, g=g, tau=tau, L=L, nu=nu, sigma=sigma, amp=amp, F=F)


def prior_predictive(d: Design, priors: Priors, draws=200, rows=50_000, seed=0):
    """Rent quantiles under the priors on a sample of rows, and the spread of each zone's
    surface across its buildings and the gap between the zones' levels."""
    rng = np.random.default_rng(seed)
    pr = prior_draws(d, priors, draws, seed)
    pick = rng.choice(len(d.y), size=min(rows, len(d.y)), replace=False)
    s = subset(d, np.isin(np.arange(len(d.y)), pick))
    trend = (1 - s.frac) * pr["L"][:, s.week] + s.frac * pr["L"][:, s.week + 1]
    mu = pr["beta"] @ s.x.T + trend + pr["F"][:, s.site]
    rent = np.exp(
        mu + rng.standard_t(pr["nu"][:, None], mu.shape) * pr["sigma"][:, s.group]
    )
    q = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    quant = lambda v, r=3: dict(zip(map(str, q), np.quantile(v, q).round(r).tolist()))  # noqa: E731
    share = site_share(d)
    spread, level = {}, []
    for surf in d.surfaces:
        on = slice(surf["first"], surf["first"] + surf["sites"])
        spread[surf["name"]] = quant(pr["F"][:, on].std(1))
        level.append(pr["F"][:, on] @ share[on] / share[on].sum())
    out = {
        "draws": draws,
        "rows": len(s.y),
        "rent_quantiles": quant(rent, 0),
        "share_1000_30000": float(np.mean((rent >= 1000) & (rent <= 30000))),
        "surface_sd_quantiles": spread,
        "surfaces": run_record(d)["surfaces"],
    }
    if len(level) == 2:
        out["manhattan_over_outer_pct_quantiles"] = quant(
            100 * np.expm1(level[0] - level[1]), 1
        )
    return out


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the two-zone model."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model two-zone`: fit on the split's training rows and save."""
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
