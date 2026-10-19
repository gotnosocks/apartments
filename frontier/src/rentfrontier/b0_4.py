"""B0.4: B0.3 with a borough intercept and a smooth rent surface over each borough.

For row i, in building s(i), with y_i the log of its net-effective latest ask, dated at its
latest ask's day t_i:

    y_i = alpha + Borough_i + F_b(s(i)) + Ladder_i + Half_i + T(t_i) + Season(t_i) + Flags_i
          + e_i,
    e_i ~ Student-t(nu, 0, sigma_g(i)), one sigma per bedroom group (studio, 1, 2, 3+).

Everything but Borough and F is B0.3's (`rentfrontier.b0_3`), with one prior loosened: the
spread of the bath steps across bedroom levels, s_bath, goes from HalfNormal(0.1) to
HalfNormal(0.3), since B0.3 put it at 0.60.

Location. I place each building at its registry coordinates (REGISTRY, the lot's latitude and
longitude) and its borough at the first digit of its BBL.

1. Borough_i is an offset from Manhattan: `boro:brooklyn` for Brooklyn, `boro:queens` for the
   few Queens buildings, and `boro:unlocated` for buildings the registry gives no coordinates.
   Each has the prior Normal(0, 0.5).
2. F_b is a Gaussian process over borough b's buildings, with mean zero and a
   squared-exponential kernel of amplitude a_b and length-scale LENGTHSCALE (500 m, fixed in
   this fit). Manhattan and Brooklyn each get their own, so no correlation crosses the East
   River. Queens and unlocated buildings get none.

I approximate each GP with the Hilbert-space basis (HSGP; Solin and Sarkka 2020, Riutort-Mayol
et al. 2023). For a borough I:

1. project the buildings to kilometres east and north of LAT0, LON0, and turn Manhattan by
   ANGLE degrees so its box runs along the avenues;
2. take the box spanning the 0.1% to 99.9% quantiles of each axis, with half-width S, and
   widen it by C = 1.5 to L = C S, clipping any building beyond it onto its edge;
3. use m = ceil(1.75 C S / LENGTHSCALE) sine waves per axis (Riutort-Mayol et al.'s rule of
   thumb), sin(pi j (u + L) / 2L) / sqrt(L) for j = 1..m, and every product of one wave from
   each axis;
4. scale each product by the square root of the kernel's spectral density at its frequency,
   2 pi l^2 exp(-l^2 w^2 / 2) with unit amplitude, so F_b(s) = a_b B_b(s) z_b with the
   coefficients z_b ~ Normal(0, 1), non-centered;
5. subtract from each column of B_b its average over the borough's rows, so F_b averages zero
   over the borough's ads and the borough offset carries the borough's level.

The amplitudes a_b have the prior HalfNormal(0.3). I evaluate F at each building and gather it
to the rows, so the cost grows with the buildings (about 68,000), not the 1.9 million rows.

    python -m rentfrontier.b0_4 prior DATASET [--rows N]
    python -m rentfrontier.run --model b0.4 --split latest --name NAME [--chains 16 ...]

`rentfrontier.loo` does not score B0.4 runs yet: its scoring reads the fixed design alone.
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

from . import b0, b0_1, b0_3
from .registry import EXTERNAL_ROOT

NAME = "b0.4"
REGISTRY = Path(
    os.environ.get(
        "FRONTIER_B04_REGISTRY",
        EXTERNAL_ROOT / "registry" / "20261017-2c61ff1-all-lots4" / "registry.parquet",
    )
)
LAT0, LON0 = 40.73, -73.95
KM_PER_LAT = 110.57
KM_PER_LON = 111.32 * math.cos(math.radians(LAT0))
LENGTHSCALE = 0.5  # km
C = 1.5
# BBL borough digit -> surface name and rotation in degrees. Turning Manhattan by 29 degrees
# lays its avenues along the box's long axis.
SURFACES = {"1": ("manhattan", 29.0), "3": ("brooklyn", 0.0)}
OFFSETS = {"3": "boro:brooklyn", "4": "boro:queens", None: "boro:unlocated"}


@dataclass(frozen=True)
class Priors(b0_3.Priors):
    s_bath: float = 0.3
    boro: tuple = (0.0, 0.5)
    amp: float = 0.3  # HalfNormal scale of each surface's amplitude


@dataclass
class Design(b0.Design):
    site: np.ndarray = (
        None  # (rows,) index into the stacked buildings; the last is no surface
    )
    surfaces: list = None  # one dict per borough surface: name, basis, first site, box


def sites_of(frame: pd.DataFrame, registry: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per building in `frame`: its borough digit (None without coordinates) and its
    position in km east and north of LAT0, LON0."""
    if registry is None:
        registry = pd.read_parquet(
            REGISTRY, columns=["building", "bbl", "latitude", "longitude"]
        )
    reg = registry.drop_duplicates("building").set_index("building")
    out = pd.DataFrame(index=pd.Index(frame.building.unique(), name="building"))
    out = out.join(reg[["bbl", "latitude", "longitude"]])
    located = out.latitude.notna() & out.longitude.notna() & out.bbl.notna()
    out["boro"] = np.where(
        located, out.bbl.astype("string").str[0].fillna("").to_numpy(object), None
    )
    out.loc[~located, "boro"] = None
    out["x"] = (out.longitude - LON0) * KM_PER_LON
    out["y"] = (out.latitude - LAT0) * KM_PER_LAT
    return out[["boro", "x", "y"]]


def box(u: np.ndarray) -> tuple[float, float, int]:
    """The centre, widened half-width L and wave count of one axis of a surface's box."""
    lo, hi = np.quantile(u, [0.001, 0.999])
    S = max((hi - lo) / 2, LENGTHSCALE)
    return (
        float((lo + hi) / 2),
        float(C * S),
        int(math.ceil(1.75 * C * S / LENGTHSCALE)),
    )


def waves(u: np.ndarray, L: float, m: int) -> tuple[np.ndarray, np.ndarray]:
    """The m sine waves on [-L, L] at the points u, and their angular frequencies."""
    w = np.pi * np.arange(1, m + 1) / (2 * L)
    return np.sin(np.outer(u + L, w)) / math.sqrt(L), w


def basis(x, y, angle, weight=None):
    """The scaled HSGP basis of a surface at its buildings, centred on the mean of each column
    under `weight` when given, and the box it spans."""
    t = math.radians(angle)
    u = x * math.cos(t) - y * math.sin(t)
    v = x * math.sin(t) + y * math.cos(t)
    cu, Lu, mu_ = box(u)
    cv, Lv, mv = box(v)
    u = np.clip(u - cu, -Lu, Lu)
    v = np.clip(v - cv, -Lv, Lv)
    clipped = int(np.sum((np.abs(u) >= Lu) | (np.abs(v) >= Lv)))
    pu, wu = waves(u, Lu, mu_)
    pv, wv = waves(v, Lv, mv)
    w2 = wu[:, None] ** 2 + wv[None, :] ** 2
    l2 = LENGTHSCALE**2
    sd = np.sqrt(2 * np.pi * l2 * np.exp(-l2 * w2 / 2))  # (mu_, mv)
    B = (pu[:, :, None] * pv[:, None, :] * sd[None]).reshape(len(u), -1)
    if weight is not None:
        B -= (weight @ B) / weight.sum()
    shape = {
        "angle": angle,
        "centre_km": [cu, cv],
        "half_width_km": [Lu, Lv],
        "waves": [mu_, mv],
        "clipped": clipped,
    }
    return B, shape


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
) -> Design:
    """B0.3's design of `frame` with the borough offsets appended, and each row's building
    placed on its borough's surface."""
    d = b0_3.design(frame, start)
    sites = sites_of(frame, registry)
    boro = frame.building.map(sites.boro).to_numpy(object)
    cols, names, count = [], [], dict(d.count)
    for digit, n in OFFSETS.items():
        col = np.array([b == digit for b in boro], dtype=float)
        if digit is None:
            col = np.array([b is None or b not in ("1", "3", "4") for b in boro], float)
        count[n] = int(col.sum())
        if count[n] > 0:
            cols.append(col)
            names.append(n)
    x = np.hstack([d.x, np.stack(cols, axis=1)]) if cols else d.x
    rows_per = frame.building.value_counts()
    surfaces, first, index = [], 0, {}
    for digit, (name, angle) in SURFACES.items():
        on = sites[sites.boro == digit]
        if len(on) == 0:
            continue
        weight = rows_per.reindex(on.index).to_numpy(float)
        B, shape = basis(on.x.to_numpy(), on.y.to_numpy(), angle, weight)
        surfaces.append(
            {"name": name, "basis": B, "first": first, "sites": len(on), **shape}
        )
        index |= dict(zip(on.index, range(first, first + len(on))))
        first += len(on)
    site = frame.building.map(index).fillna(first).to_numpy().astype(np.int64)
    return Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(b0.Design)}
        | {"x": x, "names": d.names + names, "count": count},
        site=site,
        surfaces=surfaces,
    )


def subset(d: Design, mask: np.ndarray) -> Design:
    return dataclasses.replace(b0.subset(d, mask), site=d.site[mask])


def run_record(d: Design) -> dict:
    """The surfaces' boxes and sizes, for the run's result.json."""
    return {
        "surfaces": [
            {k: v for k, v in s.items() if k != "basis"}
            | {"basis": s["basis"].shape[1]}
            for s in d.surfaces
        ],
        "lengthscale_km": LENGTHSCALE,
        "registry": str(REGISTRY),
    }


def prior_arrays(priors: Priors, names):
    """Means and sds of the coefficients outside the bath steps, in `names` order."""
    keep = [n for n in names if not b0_3.is_bath_step(n)]
    mean, sd = b0.prior_arrays(priors, keep)
    for j, n in enumerate(keep):
        if n.startswith("boro:"):
            mean[j], sd[j] = priors.boro
    return mean, sd


def model(d: Design, priors: Priors):
    """The B0.4 model of design `d` as a NumPyro model function of no arguments."""
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
    sizes = [s["basis"].shape[1] for s in d.surfaces]
    ends = np.cumsum([0] + sizes)

    def fn():
        main = numpyro.sample("main", dist.Normal(m_fix, s_fix).to_event(1))
        phi = numpyro.sample(
            "phi", dist.Normal(*priors.bath).expand([len(b0_3.POOLS)]).to_event(1)
        )
        s_bath = numpyro.sample("s_bath", dist.HalfNormal(priors.s_bath))
        u = numpyro.sample("bath_z", dist.Normal(0, 1).expand([len(steps)]).to_event(1))
        beta = jnp.zeros(len(d.names)).at[fixed].set(main)
        beta = beta.at[steps].set(phi[pools] + s_bath * u)
        numpyro.deterministic("beta", beta)
        amp = numpyro.sample(
            "amp", dist.HalfNormal(priors.amp).expand([len(bases)]).to_event(1)
        )
        gz = numpyro.sample(
            "gp_z", dist.Normal(0, 1).expand([int(ends[-1])]).to_event(1)
        )
        F = jnp.concatenate(
            [amp[k] * (B @ gz[ends[k] : ends[k + 1]]) for k, B in enumerate(bases)]
            + [jnp.zeros(1)]
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
        z = numpyro.sample("z", dist.StudentT(nu_t, 0, 1).expand([W]).to_event(1))
        L = jnp.concatenate([jnp.zeros(1), jnp.cumsum(g + tau * z)])
        numpyro.deterministic("L", L)
        numpyro.deterministic("eta", tau * z)
        mu = x @ beta + F[site] + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def initial_values(d: Design, priors: Priors, chains: int, seed: int) -> dict:
    """B0.3's starting points, with each surface's amplitude near 0.1 and its coefficients
    near zero."""
    rng = np.random.default_rng(seed)
    out = b0_3.initial_values(d, priors, chains, seed)
    m_fix, _ = prior_arrays(priors, d.names)
    main = np.tile(m_fix, (chains, 1))
    main[:, 0] = np.mean(d.y)
    out["main"] = main + 0.01 * rng.standard_normal(main.shape)
    k = sum(s["basis"].shape[1] for s in d.surfaces)
    out["amp"] = np.log(0.1) + 0.3 * rng.standard_normal((chains, len(d.surfaces)))
    out["gp_z"] = 0.1 * rng.standard_normal((chains, k))
    return out


KEPT = b0_3.KEPT + ("amp", "gp_z")
TRACED = b0_3.TRACED + ("amp",)
PROGRESS = b0_3.PROGRESS


def log_density(d: Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def diagnostics(trace: dict, names) -> dict:
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = b0_3.diagnostics(trace, names)
    rows = out["per_quantity"]
    for k in range(trace["amp"].shape[-1]):
        x = np.asarray(trace["amp"][..., k])
        if np.ptp(x) > 0:
            rows[f"amp[{k}]"] = {"rhat": split_rhat(x), "ess": ess(x)}
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


def surface_draws(d: Design, kept: dict) -> np.ndarray:
    """F at every building per kept draw, (chains, draws, buildings + 1); the last column is
    the zero of buildings with no surface."""
    amp = np.asarray(kept["amp"])
    gz = np.asarray(kept["gp_z"])
    parts, at = [], 0
    for k, s in enumerate(d.surfaces):
        n = s["basis"].shape[1]
        parts.append(amp[..., k, None] * (gz[..., at : at + n] @ s["basis"].T))
        at += n
    parts.append(np.zeros(amp.shape[:-1] + (1,)))
    return np.concatenate(parts, axis=-1)


def summarize(kept: dict, names) -> dict:
    """B0.3's summary, with the borough offsets as % premiums over Manhattan and the surface
    amplitudes."""
    out = b0_3.summarize(kept, names)

    def q(x):
        lo, med, hi = np.quantile(np.asarray(x).reshape(-1), [0.025, 0.5, 0.975])
        return {"median": float(med), "lo": float(lo), "hi": float(hi)}

    amp = np.asarray(kept["amp"])
    out["hyper"] |= {f"amp[{k}]": q(amp[..., k]) for k in range(amp.shape[-1])}
    return out


def prior_draws(d: Design, priors: Priors, draws: int, seed: int = 0) -> dict:
    """B0.3's prior draws, with the surfaces drawn at every building."""
    rng = np.random.default_rng(seed + 1)
    out = b0_3.prior_draws(d, priors, draws, seed)
    m_fix, s_fix = prior_arrays(priors, d.names)
    fixed, steps, _ = b0_3.split_index(d.names)
    out["beta"][:, fixed] = np.random.default_rng(seed + 2).normal(
        m_fix, s_fix, (draws, len(fixed))
    )
    kept = {
        "amp": np.abs(rng.normal(0, priors.amp, (draws, len(d.surfaces)))),
        "gp_z": rng.normal(0, 1, (draws, sum(s["basis"].shape[1] for s in d.surfaces))),
    }
    out["F"] = surface_draws(d, kept)
    return out


def prior_predictive(d: Design, priors: Priors, draws=200, rows=50_000, seed=0):
    """B0's prior predictive check on B0.4's priors, with the spread of each surface across
    its buildings."""
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
    spread = {
        surf["name"]: dict(
            zip(
                map(str, q),
                np.quantile(
                    pr["F"][:, surf["first"] : surf["first"] + surf["sites"]].std(1), q
                )
                .round(3)
                .tolist(),
            )
        )
        for surf in s.surfaces
    }
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
    """B0.1's ChEES-HMC on B0.4's model."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model b0.4`: fit B0.4 on the split's training rows and save it."""
    parser = b0.run_parser()
    parser.prog = "rentfrontier.run --model b0.4"
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
