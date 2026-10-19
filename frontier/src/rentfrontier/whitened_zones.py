"""Whitened zones: two-zone-1k with its wave coefficients sampled in whitened coordinates, and
a third zone for Hoboken and Jersey City.

The two-zone-1k fit (`two-zone-1k-b0-latest-8c51149b-dense-w1500`) stalled at step size
0.0026. I took the linearised posterior at its medians and found the cause in the waves. On
the buildings' footprint the waves of a zone are close to collinear, so the posterior over a
zone's coefficients is a long thin ellipse whose axes run across the coefficients, and a
diagonal mass matrix can only stretch it along the coordinate axes. Scaled by the ideal
diagonal mass, the precision had largest eigenvalue 805,000, which caps the leapfrog step at
2 / sqrt(805,000) = 0.0022. The coefficients are well identified: on the diagonal their data
precision is a median 77,000 (Manhattan) and 211,000 (outer) times their prior precision, so
this is no funnel.

So I change the coordinates the sampler moves in and leave the model alone. For each zone k
I build, once from the design, the precision the coefficients would have at reference noise
and amplitude:

    H_k = Bc_k' diag(c) Bc_k + diag(1 / (A sd_k)^2)

1. Bc_k holds the zone's waves at every located building, zero off the zone, minus their
   row-weighted mean over all buildings, the centring of `two_zone.model`;
2. c holds each building's row count times the Student-t information (nu + 1) / (nu + 3) /
   sigma^2 at SIGMA_REF and NU_REF;
3. A is AMP_REF and sd_k the waves' spectral sds at unit amplitude.

With H_k = L_k L_k' (Cholesky), I set T_k = inverse(L_k)' and sample z_k with a flat density.
The model's coefficients are w_k = T_k z_k, saved as `gp_w`, and I add the coefficients'
Normal(0, a_k sd_k) prior on w as a factor. The posterior of w is then that of two-zone-1k,
and the log density in z differs from it by the constant log |det T|. At the stalled fit's
medians the whitened precision's largest scaled eigenvalue is 12.8, a step bound of 0.56,
against the normal walk's 0.57 with no surface at all.

The zones. A building whose BBL starts with 1 sits on the Manhattan surface and any other
building in the NYC registry (REGISTRY) on the outer one, as in `two_zone`. A building in the
NJ lot registry (NJ_REGISTRY, `rentfrontier.njregistry`) sits on the NJ surface, at the
lot's point. The two registries share no building; the design stops on any building found
in both or in neither. In pipeline build rows-30b3edae310c2fae the 5,480 buildings tagged
with region nj-jersey-city-hoboken are exactly the buildings of the NJ registry, so the
registry stands in for the region tag, which the frontier datasets do not carry. A design
with no NJ buildings has the two NYC zones alone.

The NJ surface is built as the others: its own minimum-area rotated box, widened by 1.5, at
the 1 km length-scale and B0.4's wave density, with its own amplitude and its own whitening.

    python -m rentfrontier.whitened_zones prior DATASET [--rows N]
    python -m rentfrontier.run --model whitened-zones --split latest --name NAME [--chains 16 ...]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, b0_1, b0_3, b0_4, normal_walk, two_zone
from .registry import EXTERNAL_ROOT
from .total_walk import SEASON, grid_season
from .two_zone import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    KEPT,
    PROGRESS,
    REGISTRY,
    TRACED,
    Design,
    Priors,
    cell_log_premiums,
    modal_contrasts,
    prior_arrays,
    prior_draws,
    site_share,
    split_index,
    subset,
    surface_draws,
)

NAME = "whitened-zones"
LENGTHSCALE = 1.0  # km
NJ_REGISTRY = Path(
    os.environ.get(
        "FRONTIER_NJ_REGISTRY",
        EXTERNAL_ROOT / "registry-nj" / "20261019-2d485c6" / "registry.parquet",
    )
)
ZONES = ("manhattan", "outer", "nj")
# The reference point of the whitening: about the two-zone-1k fit's medians of the noise
# scales (0.178 to 0.194) and nu (7.3), and an amplitude of 1 for every zone. The data
# precision of the waves is thousands of times their prior's, so the amplitude matters little.
SIGMA_REF = 0.19
NU_REF = 7.0
AMP_REF = 1.0


def sites_of(
    frame: pd.DataFrame, registry: pd.DataFrame, nj_registry: pd.DataFrame
) -> pd.DataFrame:
    """One row per building in `frame`: its zone number (None without a point) and its
    position in km east and north of B0.4's origin."""
    nyc = registry.drop_duplicates("building").set_index("building")
    nyc = nyc[nyc.bbl.notna()]
    nj = nj_registry.drop_duplicates("building").set_index("building")
    both = nyc.index.intersection(nj.index)
    if len(both):
        raise ValueError(
            f"{len(both)} buildings are in both registries, e.g. {list(both[:5])}"
        )
    out = pd.DataFrame(index=pd.Index(frame.building.unique(), name="building"))
    out = out.join(nyc[["bbl", "latitude", "longitude"]])
    on_nj = out.index.isin(nj.index)
    out.loc[on_nj, "latitude"] = nj.latitude.reindex(out.index[on_nj]).to_numpy()
    out.loc[on_nj, "longitude"] = nj.longitude.reindex(out.index[on_nj]).to_numpy()
    located = out.latitude.notna() & out.longitude.notna() & (out.bbl.notna() | on_nj)
    boro = out.bbl.astype("string").str[0].fillna("").to_numpy(object)
    zone = np.where(on_nj, 2, np.where(boro == "1", 0, 1)).astype(object)
    zone[~located.to_numpy()] = None
    out["zone"] = zone
    out["x"] = (out.longitude - b0_4.LON0) * b0_4.KM_PER_LON
    out["y"] = (out.latitude - b0_4.LAT0) * b0_4.KM_PER_LAT
    return out[["zone", "x", "y"]]


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
    nj_registry: pd.DataFrame | None = None,
) -> Design:
    """The normal walk's design of `frame`, with each row's building placed on its zone's
    1 km surface."""
    d = b0_3.design(frame, start)
    if registry is None:
        registry = pd.read_parquet(
            REGISTRY, columns=["building", "bbl", "latitude", "longitude"]
        )
    if nj_registry is None:
        nj_registry = pd.read_parquet(
            NJ_REGISTRY, columns=["building", "latitude", "longitude"]
        )
    sites = sites_of(frame, registry, nj_registry)
    unlocated = frame.building.map(sites.zone).isna().to_numpy()
    if unlocated.any():
        lost = frame.building[unlocated].unique()
        raise ValueError(
            f"{unlocated.sum()} rows in {len(lost)} buildings have no registry point,"
            f" e.g. {list(lost[:5])}"
        )
    surfaces, first, index = [], 0, {}
    for k, name in enumerate(ZONES):
        on = sites[sites.zone == k]
        if len(on) == 0:
            continue
        B, sd, shape = two_zone.zone_basis(
            on.x.to_numpy(), on.y.to_numpy(), LENGTHSCALE
        )
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


def whitening(d: Design) -> list[np.ndarray]:
    """Each zone's map T from whitened coordinates z to wave coefficients w = T z, from the
    precision of its centred waves on the rows of `d` at the reference point."""
    share = site_share(d)
    n = len(share)
    info = (NU_REF + 1) / (NU_REF + 3) / SIGMA_REF**2
    c = info * np.bincount(d.site, minlength=n).astype(float)
    out = []
    for s in d.surfaces:
        B = np.zeros((n, s["basis"].shape[1]))
        B[s["first"] : s["first"] + s["sites"]] = s["basis"]
        B -= share @ B
        H = (B * c[:, None]).T @ B + np.diag(1 / (AMP_REF * s["sd"]) ** 2)
        L = np.linalg.cholesky(H)
        out.append(np.linalg.inv(L).T)
    return out


def run_record(d: Design) -> dict:
    """The zones' boxes and basis sizes and the whitening's reference point, for the run's
    result.json."""
    return two_zone.run_record(d) | {
        "nj_registry": str(NJ_REGISTRY),
        "whitening": {"sigma": SIGMA_REF, "nu": NU_REF, "amp": AMP_REF},
    }


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
    tau_rate = -np.log(priors.tau_alpha) / priors.tau_u
    x = jnp.asarray(d.x)
    y = jnp.asarray(d.y)
    group = jnp.asarray(d.group)
    week = jnp.asarray(d.week)
    frac = jnp.asarray(d.frac)
    site = jnp.asarray(d.site)
    B = jnp.asarray(grid_season(d))
    season = jnp.asarray([d.names.index(n) for n in SEASON])
    bases = [jnp.asarray(s["basis"]) for s in d.surfaces]
    whiten = [jnp.asarray(t) for t in whitening(d)]
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
        z = numpyro.sample(
            "gp_z", dist.ImproperUniform(constraints.real_vector, (), (int(ends[-1]),))
        )
        w = jnp.concatenate(
            [T @ z[ends[k] : ends[k + 1]] for k, T in enumerate(whiten)]
        )
        numpyro.deterministic("gp_w", w)
        numpyro.factor("gp_w_prior", dist.Normal(0, amp[which] * sds).log_prob(w).sum())
        F = jnp.concatenate(
            [Bk @ w[ends[k] : ends[k + 1]] for k, Bk in enumerate(bases)]
        )
        F = F - share @ F
        parts = [F[s["first"] : s["first"] + s["sites"]] for s in d.surfaces]
        numpyro.deterministic(
            "zone_level", jnp.stack([zs @ p for zs, p in zip(zone_share, parts)])
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
    """Two-zone's starting points, with the whitened coordinates near zero in place of the
    coefficients."""
    out = two_zone.initial_values(d, priors, chains, seed)
    out["gp_z"] = out.pop("gp_w")
    return out


def log_density(d: Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def _extras(trace: dict) -> dict:
    """Each zone's amplitude and level, and each other zone's level against the outer zone's."""
    amp = np.asarray(trace["amp"])
    level = np.asarray(trace["zone_level"])
    out = {}
    for k in range(amp.shape[-1]):
        out[f"amp[{ZONES[k]}]"] = amp[..., k]
        out[f"zone_level[{ZONES[k]}]"] = level[..., k]
    if level.shape[-1] >= 2:
        out["zone_gap"] = level[..., 0] - level[..., 1]
    if level.shape[-1] == 3:
        out["zone_gap[nj]"] = level[..., 2] - level[..., 1]
    return out


def diagnostics(trace: dict, names) -> dict:
    """The normal walk's convergence table, with each zone's amplitude and level and the gaps
    between the levels."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = normal_walk.diagnostics(trace, names)
    rows = out["per_quantity"]
    for n, x in _extras(trace).items():
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


def summarize(kept: dict, names) -> dict:
    """The normal walk's summary, with each zone's amplitude, level and spread, and the
    Manhattan and NJ levels against the outer zone's as % premiums."""
    out = normal_walk.summarize(kept, names)
    amp, level, sd = (np.asarray(kept[k]) for k in ("amp", "zone_level", "zone_sd"))
    out["zones"] = {
        ZONES[k]: {
            "amp": two_zone._q(amp[..., k]),
            "level": two_zone._q(level[..., k]),
            "sd": two_zone._q(sd[..., k]),
        }
        for k in range(amp.shape[-1])
    }
    out["manhattan_over_outer_pct"] = two_zone._q(
        100 * np.expm1(level[..., 0] - level[..., 1])
    )
    if level.shape[-1] == 3:
        out["nj_over_outer_pct"] = two_zone._q(
            100 * np.expm1(level[..., 2] - level[..., 1])
        )
    return out


def prior_predictive(d: Design, priors: Priors, draws=200, rows=50_000, seed=0):
    """Two-zone's prior predictive check, with the NJ level against the outer zone's when the
    design has an NJ zone."""
    out = two_zone.prior_predictive(d, priors, draws, rows, seed)
    pr = prior_draws(d, priors, draws, seed)
    share = site_share(d)
    level = []
    for s in d.surfaces:
        on = slice(s["first"], s["first"] + s["sites"])
        level.append(pr["F"][:, on] @ share[on] / share[on].sum())
    q = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    gap = lambda a, b: dict(  # noqa: E731
        zip(map(str, q), np.quantile(100 * np.expm1(a - b), q).round(1).tolist())
    )
    out["surfaces"] = run_record(d)["surfaces"]
    out["manhattan_over_outer_pct_quantiles"] = gap(level[0], level[1])
    if len(level) == 3:
        out["nj_over_outer_pct_quantiles"] = gap(level[2], level[1])
    return out


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the whitened zones."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model whitened-zones`: fit on the split's training rows and save."""
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
