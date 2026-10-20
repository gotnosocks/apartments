"""Building zones: whitened zones with a level for every building, centred on its zone's surface.

Whitened zones gives every ad in a building the surface's value F(s) at the building's point.
Here I give each building s its own level eta_s and let its ads see eta_s in place of F(s):

    eta_s ~ Normal(F(s), b_z)        b_z ~ HalfNormal(BLD_SD_PRIOR), one per zone
    y ~ StudentT(nu, x beta + eta_site + L(t), sigma_group)

The building effect is b_s = eta_s - F(s), saved as `bld`. The model is the same as adding
b_s ~ Normal(0, b_z) to whitened zones' mean (`plain_model`): the map from (b, w) to (eta, w)
shifts b by F, so the two log densities differ by a constant.

I sample the levels centred on the surface because a building with many ads pins eta_s and
leaves b_s and F(s) free to trade against each other. With eta_s sampled, the waves meet the
data only through the 73k levels, each weighted by 1 / b_z^2.

The coordinates the sampler moves in:

1. eta_s = eta0_s + u_s / sqrt(p_s), with p_s = n_s info + 1 / BLD_SD_REF^2, n_s the
   building's training rows and info the Student-t information at whitened zones' reference
   sigma and nu. eta0_s is a starting guess (`building_offset`): the building's mean
   residual from a least-squares fit of the fixed terms, shrunk toward zero. The shift and
   the scale are constants, so the posterior is unchanged.
2. The wave coefficients are w = T z, as in whitened zones, but T comes from the precision of
   the centred waves at the buildings, each building weighted by 1 / BLD_SD_REF^2 in place
   of its rows' information.

    python -m rentfrontier.building_zones prior DATASET [--rows N]
    python -m rentfrontier.run --model building-zones --split latest --name NAME [--chains 16 ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from . import b0, b0_1, normal_walk, two_zone, whitened_zones
from .total_walk import SEASON, grid_season
from .whitened_zones import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AMP_REF,
    NU_REF,
    PROGRESS,
    SIGMA_REF,
    ZONES,
    Design,
    Priors,
    cell_log_premiums,
    design,
    modal_contrasts,
    prior_arrays,
    site_share,
    split_index,
    subset,
    surface_draws,
)

NAME = "building-zones"
KEPT = whitened_zones.KEPT + ("bld_sd", "bld", "zone_var_f", "zone_var_b")
TRACED = whitened_zones.TRACED + ("bld_sd",)
# The building spread's prior scale, and the spread the sampler's coordinates assume.
BLD_SD_PRIOR = 0.3
BLD_SD_REF = 0.2


def site_zone(d: Design) -> np.ndarray:
    """Each building's zone number, in the order of the design's sites."""
    return np.concatenate([np.full(s["sites"], k) for k, s in enumerate(d.surfaces)])


def site_rows(d: Design) -> np.ndarray:
    """Each building's number of rows in `d`."""
    n = sum(s["sites"] for s in d.surfaces)
    return np.bincount(d.site, minlength=n).astype(float)


def building_scale(d: Design) -> np.ndarray:
    """1 / sqrt(p_s): each building level's posterior sd at the reference point, from its rows
    and the spread's reference value."""
    info = (NU_REF + 1) / (NU_REF + 3) / SIGMA_REF**2
    return 1 / np.sqrt(site_rows(d) * info + 1 / BLD_SD_REF**2)


def building_offset(d: Design) -> np.ndarray:
    """eta0: each building's mean residual from a least-squares fit of the fixed terms, shrunk
    toward zero as a Normal(0, BLD_SD_REF) prior would shrink it at noise SIGMA_REF."""
    xtx = d.x.T @ d.x
    coef = np.linalg.lstsq(xtx, d.x.T @ d.y, rcond=None)[0]
    r = d.y - d.x @ coef
    n = site_rows(d)
    total = np.bincount(d.site, weights=r, minlength=len(n))
    return total / (n + (SIGMA_REF / BLD_SD_REF) ** 2)


def wave_matrix(d: Design) -> tuple[np.ndarray, np.ndarray]:
    """Every zone's waves at every building, each zone's columns zero off the zone, minus their
    row-weighted mean, with the waves' spectral sds."""
    share = site_share(d)
    ends = np.cumsum([0] + [s["basis"].shape[1] for s in d.surfaces])
    B = np.zeros((len(share), ends[-1]))
    for k, s in enumerate(d.surfaces):
        B[s["first"] : s["first"] + s["sites"], ends[k] : ends[k + 1]] = s["basis"]
    B -= share @ B
    return B, np.concatenate([s["sd"] for s in d.surfaces])


def whitening(d: Design) -> np.ndarray:
    """The map T from whitened coordinates z to the wave coefficients w = T z, from the
    precision the levels' prior gives the centred waves at the reference spread."""
    B, sd = wave_matrix(d)
    H = B.T @ B / BLD_SD_REF**2 + np.diag(1 / (AMP_REF * sd) ** 2)
    return np.linalg.inv(np.linalg.cholesky(H)).T


def run_record(d: Design) -> dict:
    """Whitened zones' record, with the building spread's prior and reference."""
    return whitened_zones.run_record(d) | {
        "buildings": {
            "count": int(sum(s["sites"] for s in d.surfaces)),
            "sd_prior": BLD_SD_PRIOR,
            "sd_ref": BLD_SD_REF,
        }
    }


def _parts(d: Design, priors: Priors, T: np.ndarray):
    """The pieces the centred and plain models share: the fixed terms, walk and noise, and the
    surface from whitened coefficients. Returns (sample, prepared constants)."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    W = d.weeks
    m_fix, s_fix = normal_walk.prior_arrays(priors, d.names)
    fixed, steps, _ = split_index(d.names)
    alpha = d.names.index("alpha")
    rest = fixed[fixed != alpha]
    keep = fixed != alpha
    tau_rate = -np.log(priors.tau_alpha) / priors.tau_u
    Bs = jnp.asarray(grid_season(d))
    season = jnp.asarray([d.names.index(n) for n in SEASON])
    bases = [jnp.asarray(s["basis"]) for s in d.surfaces]
    Tj = jnp.asarray(T)
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

    def sample():
        """Draw every site but the buildings', and return (beta, L, F, nu, sigma)."""
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
        w = Tj @ z
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
        M = D - Bs @ beta[season]
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
        return beta, L, F, nu, sigma

    return sample, zone_share


def _buildings(d: Design, F, b):
    """Record the building effects and each zone's row-weighted variance of F and of b."""
    import jax.numpy as jnp
    import numpyro

    numpyro.deterministic("bld", b.astype(jnp.float32))
    var_f, var_b = [], []
    for s in d.surfaces:
        on = slice(s["first"], s["first"] + s["sites"])
        wgt = jnp.asarray(site_rows(d)[on] / max(site_rows(d)[on].sum(), 1.0))
        for v, out in ((F[on], var_f), (b[on], var_b)):
            m = wgt @ v
            out.append(wgt @ (v - m) ** 2)
    numpyro.deterministic("zone_var_f", jnp.stack(var_f))
    numpyro.deterministic("zone_var_b", jnp.stack(var_b))


def model(d: Design, priors: Priors):
    """The model of design `d` as a NumPyro model function of no arguments, with each
    building's level sampled around its surface value."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    sample, _ = _parts(d, priors, whitening(d))
    x = jnp.asarray(d.x)
    y = jnp.asarray(d.y)
    group = jnp.asarray(d.group)
    week = jnp.asarray(d.week)
    frac = jnp.asarray(d.frac)
    site = jnp.asarray(d.site)
    zone = jnp.asarray(site_zone(d))
    eta0 = jnp.asarray(building_offset(d))
    scale = jnp.asarray(building_scale(d))
    nz = len(d.surfaces)

    def fn():
        beta, L, F, nu, sigma = sample()
        bsd = numpyro.sample(
            "bld_sd", dist.HalfNormal(BLD_SD_PRIOR).expand([nz]).to_event(1)
        )
        u = numpyro.sample(
            "bld_u", dist.ImproperUniform(constraints.real_vector, (), (len(scale),))
        )
        level = eta0 + u * scale
        numpyro.factor("bld_prior", dist.Normal(F, bsd[zone]).log_prob(level).sum())
        _buildings(d, F, level - F)
        mu = x @ beta + level[site] + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def plain_model(d: Design, priors: Priors):
    """The same model with the building effects b_s ~ Normal(0, b_z) sampled directly, as
    b_s = u_s / sqrt(p_s), beside whitened zones' surface and whitening."""
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.distributions import constraints

    sample, _ = _parts(d, priors, whitened_zones.whitening(d))
    x = jnp.asarray(d.x)
    y = jnp.asarray(d.y)
    group = jnp.asarray(d.group)
    week = jnp.asarray(d.week)
    frac = jnp.asarray(d.frac)
    site = jnp.asarray(d.site)
    zone = jnp.asarray(site_zone(d))
    scale = jnp.asarray(building_scale(d))
    nz = len(d.surfaces)

    def fn():
        beta, L, F, nu, sigma = sample()
        bsd = numpyro.sample(
            "bld_sd", dist.HalfNormal(BLD_SD_PRIOR).expand([nz]).to_event(1)
        )
        u = numpyro.sample(
            "bld_u", dist.ImproperUniform(constraints.real_vector, (), (len(scale),))
        )
        b = u * scale
        numpyro.factor("bld_prior", dist.Normal(0, bsd[zone]).log_prob(b).sum())
        _buildings(d, F, b)
        mu = x @ beta + F[site] + b[site] + (1 - frac) * L[week] + frac * L[week + 1]
        with numpyro.plate("rows", len(d.y)):
            numpyro.sample("y", dist.StudentT(nu, mu, sigma[group]), obs=y)

    return fn


def initial_values(d: Design, priors: Priors, chains: int, seed: int) -> dict:
    """Whitened zones' starting points, with each building's level near eta0 and the spreads
    near BLD_SD_REF."""
    rng = np.random.default_rng(seed + 11)
    out = whitened_zones.initial_values(d, priors, chains, seed)
    n = sum(s["sites"] for s in d.surfaces)
    out["bld_sd"] = np.log(BLD_SD_REF) + 0.1 * rng.standard_normal(
        (chains, len(d.surfaces))
    )
    out["bld_u"] = 0.01 * rng.standard_normal((chains, n))
    return out


def log_density(d: Design, priors: Priors):
    """The model's log density on the unconstrained scale, and the map from an unconstrained
    point to every site and deterministic on its own scale."""
    jax, _ = b0._jax()
    from numpyro.infer.util import initialize_model

    info = initialize_model(jax.random.PRNGKey(0), model(d, priors))
    return (lambda p: -info.potential_fn(p)), info.postprocess_fn


def _extras(trace: dict) -> dict:
    """Whitened zones' extras, with each zone's building spread."""
    out = whitened_zones._extras(trace)
    bsd = np.asarray(trace["bld_sd"])
    for k in range(bsd.shape[-1]):
        out[f"bld_sd[{ZONES[k]}]"] = bsd[..., k]
    return out


def diagnostics(trace: dict, names) -> dict:
    """Whitened zones' convergence table, with each zone's building spread."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = whitened_zones.diagnostics(trace, names)
    rows = out["per_quantity"]
    for n, x in _extras(trace).items():
        if n.startswith("bld_sd") and np.ptp(x) > 0:
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
    """Whitened zones' summary, with each zone's building spread and the buildings' share of
    the zone's location variance, var(b) / (var(F) + var(b)) over its rows."""
    out = whitened_zones.summarize(kept, names)
    bsd, vf, vb = (np.asarray(kept[k]) for k in ("bld_sd", "zone_var_f", "zone_var_b"))
    for k in range(bsd.shape[-1]):
        out["zones"][ZONES[k]] |= {
            "bld_sd": two_zone._q(bsd[..., k]),
            "bld_share": two_zone._q(vb[..., k] / (vf[..., k] + vb[..., k])),
        }
    return out


def building_quantiles(kept: dict) -> np.ndarray:
    """Each building effect's 5%, 50% and 95% quantiles over the kept draws, (sites, 3)."""
    b = np.asarray(kept["bld"])
    return np.quantile(b.reshape(-1, b.shape[-1]), [0.05, 0.5, 0.95], axis=0).T


def prior_predictive(d: Design, priors: Priors, draws=200, rows=50_000, seed=0):
    """Whitened zones' prior predictive check, with the building effects added to each row's
    surface value."""
    out = whitened_zones.prior_predictive(d, priors, draws, rows, seed)
    rng = np.random.default_rng(seed + 3)
    bsd = np.abs(rng.normal(0, BLD_SD_PRIOR, (draws, len(d.surfaces))))
    n = sum(s["sites"] for s in d.surfaces)
    b = rng.standard_normal((draws, n)) * bsd[:, site_zone(d)]
    q = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    out["bld_sd_quantiles"] = dict(
        zip(map(str, q), np.quantile(bsd, q).round(3).tolist())
    )
    out["bld_effect_pct_quantiles"] = dict(
        zip(
            map(str, q),
            np.quantile(100 * np.expm1(b[:, d.site[:rows]]), q).round(1).tolist(),
        )
    )
    return out


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the building zones."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones`: fit on the split's training rows and save."""
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
                indent=1,
            )
        )


if __name__ == "__main__":
    main()
