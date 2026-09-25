"""The model ladder: the simplest models first, one term more per rung, fit by
independent NUTS implementations and scored like the Gibbs line.

    uv run --extra pymc python -m rentfrontier.ladder --backend pymc L0-mean L1-drift
    uv run --extra gpu  python -m rentfrontier.ladder --backend numpyro L6-units

Rungs (log rent minus the training mean; Student-t noise throughout):

    L0-mean      intercept only
    L1-drift     + one shared linear drift per year
    L2-trend     a shared market trend: random walk over quarterly knots
                 (replaces the linear drift, which it contains)
    L3-season    + calendar season
    L4-features  + the base-v1 listing features
    L5-building  + building levels
    L6-units     + unit effects: the same model as the Gibbs line's m0q
    L7-walk      + each building's random walk over half-year knots (m1q)

Priors mirror `model.build_model` (m0q, m1q): alpha ~ N(0, 1); trend and season
scales ~ HalfNormal(0.05); building scale ~ HalfNormal(0.5); unit scale ~
HalfNormal(0.2); walk scale ~ HalfNormal(0.1) per half-year step, the walk
anchored at 0 at the first knot; beta ~ N(0, 0.5 x feature prior scale); sigma ~
HalfNormal(0.2); nu ~ Gamma(2, rate 0.1). The linear drift (new, L1 only) ~
N(0, 0.1) per year.

Parameterization (it changes how NUTS moves, not the model) follows the Gibbs
line's NUTS reference: trend steps, season, building and unit effects are
centred, because each is informed by many rows (12 seasons of ~4,000 rows,
quarterly knots of ~700), where non-centring makes NUTS diverge at the scales
(3c26c4a: 1 and 6 divergences on L2 and L3). The building walk is non-centred:
most building half-years have no rows, so its steps are prior-dominated.

Backends:
- pymc: PyMC model sampled by nutpie (4 chains x 1,000 tune + 1,000 draws,
  CPU). Its fit time counts on the thelio CPU class.
- numpyro: NumPyro NUTS (vectorized chains) on whatever JAX device is
  present (the RTX 2060 or the CPU).

Each fit writes a run record in the Gibbs line's format under
/data1/apartments/frontier/runs/<rung>-<backend>-rows-<commit>[-<label>]/ (line =
"pymc" or "numpyro", so the board and dashboard list it), plus
- PSIS-LOO over the row split's 47,374 training rows (for L6 with the unit
  effect integrated exactly per row, as `rentfrontier.loo`);
- the variance decomposition (`rentfrontier.variance` groups);
- held-out log density on the 5,264 row-split held-out rows, paired against
  the promoted reference.
The gate is the board's: split R-hat < 1.01, bulk ESS > 400, no
divergences, R-hat < 1.05 over every element of every effect.
Refuses a dirty tree.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time

import numpy as np

from . import data, features, loo, model, splits, variance
from .run import RUNS, contention, cpu_clock, ess, feature_sources, git, hardware, score

RUNGS = {
    "L0-mean": (),
    "L1-drift": ("drift",),
    "L2-trend": ("trend",),
    "L3-season": ("trend", "season"),
    "L4-features": ("trend", "season", "features"),
    "L5-building": ("trend", "season", "features", "building"),
    "L6-units": ("trend", "season", "features", "building", "units"),
    "L7-walk": ("trend", "season", "features", "building", "units", "walk"),
}
TREND_KNOT_MONTHS = 3
WALK_SCALE_SD = 0.1  # model.ModelConfig.walk_scale_sd
# Per-draw arrays too large to keep in posterior.npz (means and sds are kept).
LARGE = ("unit", "walk_z")
CHAINS, TUNE, DRAWS = 4, 1000, 1000
SEED = 20260925


# ----------------------------------------------------------------- inputs
def inputs():
    frame = data.load()
    heldout = splits.row_split(frame)
    feats = features.build("base-v1", frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    n_months = len(prep.periods)
    mean_month = float(np.mean(prep.train.month))
    return {
        "frame": frame,
        "heldout": heldout,
        "feats": feats,
        "prep": prep,
        "basis": model.knot_basis(n_months, TREND_KNOT_MONTHS),
        "beta_sd": 0.5 * np.asarray(feats.prior_scale),
        "mean_month": mean_month,
    }


def years(a, mean_month):
    return (np.asarray(a.month, float) - mean_month) / 12.0


# ----------------------------------------------------------------- models
def numpyro_model(terms, a, inp):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    prep = inp["prep"]
    basis = jnp.asarray(inp["basis"])
    t = jnp.asarray(years(a, inp["mean_month"]))
    x = jnp.asarray(a.x)
    month, cal = jnp.asarray(a.month), jnp.asarray(a.calendar)
    bld, unit = jnp.asarray(a.building), jnp.asarray(a.unit)
    y = jnp.asarray(a.y)
    knot, frac = jnp.asarray(a.knot), jnp.asarray(a.knot_frac)
    n_walk = model.n_knots(len(prep.periods)) - 1

    def f():
        mu = numpyro.sample("alpha", dist.Normal(0.0, 1.0)) * jnp.ones_like(y)
        if "drift" in terms:
            mu = mu + numpyro.sample("drift", dist.Normal(0.0, 0.1)) * t
        if "trend" in terms:
            ts = numpyro.sample("trend_scale", dist.HalfNormal(0.05))
            step = numpyro.sample(
                "trend_step", dist.Normal(0, ts).expand([basis.shape[1]])
            )
            mu = mu + (basis @ jnp.cumsum(step))[month]
        if "season" in terms:
            ss = numpyro.sample("season_scale", dist.HalfNormal(0.05))
            s = numpyro.sample("season_raw", dist.Normal(0, ss).expand([12]))
            mu = mu + (s - s.mean())[cal]
        if "features" in terms:
            beta = numpyro.sample("beta", dist.Normal(0.0, jnp.asarray(inp["beta_sd"])))
            mu = mu + x @ beta
        if "building" in terms:
            bs = numpyro.sample("building_scale", dist.HalfNormal(0.5))
            b = numpyro.sample(
                "building", dist.Normal(0, bs).expand([len(prep.buildings)])
            )
            mu = mu + b[bld]
        if "units" in terms:
            us = numpyro.sample("unit_scale", dist.HalfNormal(0.2))
            u = numpyro.sample("unit", dist.Normal(0, us).expand([len(prep.units)]))
            mu = mu + u[unit]
        if "walk" in terms:
            ws = numpyro.sample("walk_scale", dist.HalfNormal(WALK_SCALE_SD))
            z = numpyro.sample(
                "walk_z", dist.Normal(0, 1).expand([len(prep.buildings), n_walk])
            )
            w = jnp.pad(jnp.cumsum(ws * z, axis=1), ((0, 0), (1, 0)))
            mu = mu + (1 - frac) * w[bld, knot] + frac * w[bld, knot + 1]
        sigma = numpyro.sample("sigma", dist.HalfNormal(0.2))
        nu = numpyro.sample("nu", dist.Gamma(2.0, 0.1))
        numpyro.sample("y", dist.StudentT(nu, mu, sigma), obs=y)

    return f


def pymc_model(terms, a, inp):
    import pymc as pm
    import pytensor.tensor as pt

    prep = inp["prep"]
    basis = inp["basis"]
    t = years(a, inp["mean_month"])
    with pm.Model() as m:
        mu = pm.Normal("alpha", 0.0, 1.0) * np.ones(len(a.y))
        if "drift" in terms:
            mu = mu + pm.Normal("drift", 0.0, 0.1) * t
        if "trend" in terms:
            ts = pm.HalfNormal("trend_scale", 0.05)
            step = pm.Normal("trend_step", 0, ts, shape=basis.shape[1])
            mu = mu + pt.dot(basis, pt.cumsum(step))[a.month]
        if "season" in terms:
            ss = pm.HalfNormal("season_scale", 0.05)
            s = pm.Normal("season_raw", 0, ss, shape=12)
            mu = mu + (s - s.mean())[a.calendar]
        if "features" in terms:
            beta = pm.Normal("beta", 0.0, inp["beta_sd"], shape=a.x.shape[1])
            mu = mu + pt.dot(a.x, beta)
        if "building" in terms:
            bs = pm.HalfNormal("building_scale", 0.5)
            b = pm.Normal("building", 0, bs, shape=len(prep.buildings))
            mu = mu + b[a.building]
        if "units" in terms:
            us = pm.HalfNormal("unit_scale", 0.2)
            u = pm.Normal("unit", 0, us, shape=len(prep.units))
            mu = mu + u[a.unit]
        if "walk" in terms:
            ws = pm.HalfNormal("walk_scale", WALK_SCALE_SD)
            n_walk = model.n_knots(len(prep.periods)) - 1
            z = pm.Normal("walk_z", 0, 1, shape=(len(prep.buildings), n_walk))
            w = pt.concatenate(
                [pt.zeros((len(prep.buildings), 1)), pt.cumsum(ws * z, axis=1)], axis=1
            )
            mu = (
                mu
                + (1 - a.knot_frac) * w[a.building, a.knot]
                + a.knot_frac * w[a.building, a.knot + 1]
            )
        sigma = pm.HalfNormal("sigma", 0.2)
        nu = pm.Gamma("nu", alpha=2.0, beta=0.1)
        pm.StudentT("y", nu=nu, mu=mu, sigma=sigma, observed=a.y)
    return m


def sample(backend, terms, inp):
    """Draws as {name: (chains, draws, ...)} numpy arrays, plus divergences."""
    a = inp["prep"].train
    if backend == "numpyro":
        import jax
        from numpyro.infer import MCMC, NUTS

        jax.config.update("jax_enable_x64", True)
        mcmc = MCMC(
            NUTS(numpyro_model(terms, a, inp)),
            num_warmup=TUNE,
            num_samples=DRAWS,
            num_chains=CHAINS,
            chain_method="vectorized",
            progress_bar=False,
        )
        mcmc.run(jax.random.PRNGKey(SEED), extra_fields=("diverging",))
        draws = {
            k: np.asarray(v) for k, v in mcmc.get_samples(group_by_chain=True).items()
        }
        div = int(
            np.asarray(mcmc.get_extra_fields(group_by_chain=True)["diverging"]).sum()
        )
        return draws, div
    import nutpie

    compiled = nutpie.compile_pymc_model(pymc_model(terms, a, inp))
    trace = nutpie.sample(
        compiled, chains=CHAINS, tune=TUNE, draws=DRAWS, seed=SEED, progress_bar=False
    )
    post = trace.posterior
    draws = {k: np.asarray(post[k].values) for k in post.data_vars}
    div = int(np.asarray(trace.sample_stats["diverging"].values).sum())
    return draws, div


# ------------------------------------------------------------- effects
def effects(draws, terms, inp):
    """Constrained effects, each flattened to (S, ...) with S = chains x draws."""
    flat = {k: v.reshape(-1, *v.shape[2:]) for k, v in draws.items()}
    e = {"alpha": flat["alpha"], "sigma": flat["sigma"], "nu": flat["nu"]}
    if "drift" in terms:
        e["drift"] = flat["drift"]
    if "trend" in terms:
        e["trend"] = (
            np.cumsum(flat["trend_step"], axis=1) @ inp["basis"].T
        )  # (S, months)
        e["trend_scale"] = flat["trend_scale"]
    if "season" in terms:
        s = flat["season_raw"]
        e["season"] = s - s.mean(axis=1, keepdims=True)
        e["season_scale"] = flat["season_scale"]
    if "features" in terms:
        e["beta"] = flat["beta"]
    if "building" in terms:
        e["building"] = flat["building"]
        e["building_scale"] = flat["building_scale"]
    if "units" in terms:
        e["unit"] = flat["unit"]
        e["unit_scale"] = flat["unit_scale"]
    if "walk" in terms:
        steps = flat["walk_scale"][:, None, None] * flat["walk_z"]
        e["walk"] = np.pad(np.cumsum(steps, axis=2), ((0, 0), (0, 0), (1, 0)))
        e["walk_scale"] = flat["walk_scale"]
    return e


def terms_for(e, a, inp):
    """Named additive terms (S, rows) for arrays `a` (log rent minus offset)."""
    s = e["alpha"].shape[0]
    n = len(a.y)
    market = np.broadcast_to(e["alpha"][:, None], (s, n)).copy()
    if "drift" in e:
        market += e["drift"][:, None] * years(a, inp["mean_month"])[None]
    if "trend" in e:
        market += e["trend"][:, a.month]
    if "season" in e:
        market += e["season"][:, a.calendar]
    out = {"market and time": market}
    if "beta" in e:
        out["features"] = e["beta"] @ np.asarray(a.x).T
    if "building" in e:
        out["building"] = e["building"][:, a.building]
    if "walk" in e:
        w = e["walk"]
        out["building over time"] = (1 - a.knot_frac)[None] * w[
            :, a.building, a.knot
        ] + a.knot_frac[None] * w[:, a.building, a.knot + 1]
    if "unit" in e:
        out["unit"] = np.where(
            a.unit[None] >= 0, e["unit"][:, np.maximum(a.unit, 0)], 0.0
        )
    return out


def t_logpdf(r, nu, sigma):
    from scipy.special import gammaln

    z = r / sigma
    return (
        gammaln((nu + 1) / 2)
        - gammaln(nu / 2)
        - 0.5 * np.log(nu * math.pi)
        - np.log(sigma)
        - (nu + 1) / 2 * np.log1p(z * z / nu)
    )


# ---------------------------------------------------------- diagnostics
def split_rhat_vec(x):
    """Split R-hat per element for x of shape (chains, draws, k)."""
    n = x.shape[1]
    h = n // 2
    x = np.concatenate([x[:, :h], x[:, h : 2 * h]], axis=0)
    n = x.shape[1]
    within = x.var(axis=1, ddof=1).mean(axis=0)
    between = n * x.mean(axis=1).var(axis=0, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.sqrt(((n - 1) / n * within + between / n) / within)
    return np.where(within > 0, r, 1.0)


def diagnose(draws, divergences):
    scalars = {k: v for k, v in draws.items() if v.ndim == 2}
    table = {
        k: {"rhat": float(split_rhat_vec(v[..., None])[0]), "ess": ess(v)}
        for k, v in scalars.items()
    }
    if "beta" in draws:
        for j in range(draws["beta"].shape[2]):
            v = draws["beta"][:, :, j]
            table[f"beta[{j}]"] = {
                "rhat": float(split_rhat_vec(v[..., None])[0]),
                "ess": ess(v),
            }
    group = {}
    for k, v in draws.items():
        if v.ndim >= 3:
            r = split_rhat_vec(v.reshape(*v.shape[:2], -1))
            group[k] = {
                "max": float(r.max()),
                "argmax": int(r.argmax()),
                "over_1_05": int((r > 1.05).sum()),
                "size": int(r.size),
            }
    max_rhat_name = max(table, key=lambda k: table[k]["rhat"])
    min_ess_name = min(table, key=lambda k: table[k]["ess"])
    group_max = max([g["max"] for g in group.values()], default=1.0)
    d = {
        "quantities": len(table),
        "max_rhat": table[max_rhat_name]["rhat"],
        "max_rhat_name": max_rhat_name,
        "min_ess": table[min_ess_name]["ess"],
        "min_ess_name": min_ess_name,
        "scalars": {k: v for k, v in table.items() if not k.startswith("beta[")},
        "divergences": divergences,
        "group_rhat": group,
        "group_rhat_max": group_max,
    }
    d["passes"] = bool(
        d["max_rhat"] < 1.01
        and d["min_ess"] > 400
        and divergences == 0
        and group_max < 1.05
    )
    return d


# ------------------------------------------------------------- scoring
def heldout_lpd(e, inp, chains):
    from scipy.special import logsumexp

    a = inp["prep"].test
    mu = sum(terms_for(e, a, inp).values())
    ll = t_logpdf(a.y[None] - mu, e["nu"][:, None], e["sigma"][:, None])
    s = ll.shape[0]
    lpd = logsumexp(ll, axis=0) - math.log(s)
    per = ll.reshape(chains, s // chains, -1)
    lpd_chain = logsumexp(per, axis=1) - math.log(s // chains)
    return lpd, lpd_chain


def psis_training(e, terms, inp):
    """PSIS-LOO over the training rows; the unit effect integrated (L6)."""
    prep, frame, heldout = inp["prep"], inp["frame"], inp["heldout"]
    train_idx = np.flatnonzero(~heldout)
    s = e["alpha"].shape[0]
    if "unit" not in e:
        parts = []
        for chunk in np.array_split(
            train_idx, max(1, len(train_idx) // max(500, 4_000_000 // s))
        ):
            mask = np.zeros(len(frame), dtype=bool)
            mask[chunk] = True
            a = model.row_arrays(prep, frame, mask)
            mu = sum(terms_for(e, a, inp).values())
            ll = t_logpdf(a.y[None] - mu, e["nu"][:, None], e["sigma"][:, None])
            parts.append((frame.audit_id.to_numpy()[chunk], *loo.psis_loo(ll)))
        audit = np.concatenate([p[0] for p in parts])
        out = [np.concatenate([p[i] for p in parts]) for i in (1, 2, 3)]
        return audit, *out, "none"
    import jax

    jax.config.update("jax_enable_x64", True)
    unit_of = np.asarray(model.row_arrays(prep, frame, ~heldout).unit)
    order = np.argsort(unit_of, kind="stable")
    rows_sorted = train_idx[order]
    units_sorted = unit_of[order]
    size = loo.chunk_rows(s)
    params = {"nu": e["nu"], "sigma": e["sigma"], "unit_scale": e["unit_scale"]}
    audit_parts, parts = [], []
    for lo, hi in loo.unit_chunks(units_sorted, size):
        mask = np.zeros(len(frame), dtype=bool)
        mask[rows_sorted[lo:hi]] = True
        a = model.row_arrays(prep, frame, mask)
        pos = np.argsort(np.argsort(rows_sorted[lo:hi]))
        t = terms_for(e, a, inp)
        mu = sum(v for k, v in t.items() if k != "unit")[:, pos]
        y, unit = a.y[pos], a.unit[pos]
        _, seg = np.unique(unit, return_inverse=True)
        n, pad = hi - lo, size - (hi - lo)
        ll = loo.integrated_loglik(
            np.r_[y, np.zeros(pad)],
            np.concatenate([mu, np.zeros((s, pad))], axis=1),
            np.r_[seg, seg.max() + 1 + np.arange(pad)],
            size,
            np.zeros(size),
            params,
            t_units=False,
            drift=False,
        )
        parts.append(loo.psis_loo(np.asarray(ll)[:, :n]))
        audit_parts.append(frame.audit_id.to_numpy()[rows_sorted[lo:hi]])
    audit = np.concatenate(audit_parts)
    out = [np.concatenate([p[i] for p in parts]) for i in range(3)]
    return audit, *out, "unit level"


def variance_shares(e, inp):
    prep, frame, heldout = inp["prep"], inp["frame"], inp["heldout"]
    s = e["alpha"].shape[0]
    m = variance.Moments(s)
    train_idx = np.flatnonzero(~heldout)
    for chunk in np.array_split(
        train_idx, max(1, len(train_idx) // max(500, 4_000_000 // s))
    ):
        mask = np.zeros(len(frame), dtype=bool)
        mask[chunk] = True
        a = model.row_arrays(prep, frame, mask)
        t = terms_for(e, a, inp)
        groups = {g: np.zeros((s, len(a.y))) for g in variance.GROUPS}
        for k, v in t.items():
            groups[k] += v
        m.add(groups, a.y)
    return variance.summarize(m.shares()), m.n


# ----------------------------------------------------------------- main
def fit(rung, backend, commit, name, log=print):
    terms = RUNGS[rung]
    t0 = time.perf_counter()
    started = time.time()
    inp = inputs()
    prep_seconds = time.perf_counter() - t0
    t0 = time.perf_counter()
    clock = cpu_clock()
    draws, div = sample(backend, terms, inp)
    fit_seconds = time.perf_counter() - t0
    load = contention(clock)
    diag = diagnose(draws, div)
    log(
        f"{rung}/{backend}: fit {fit_seconds:.0f} s; max R-hat {diag['max_rhat']:.4f} ({diag['max_rhat_name']}), "
        f"min ESS {diag['min_ess']:.0f} ({diag['min_ess_name']}), divergences {div}, all-effects R-hat {diag['group_rhat_max']:.3f}"
    )
    e = effects(draws, terms, inp)
    lpd, lpd_chain = heldout_lpd(e, inp, CHAINS)
    prep = inp["prep"]
    scores = score("rows", prep.test_audit_id, lpd, lpd_chain)
    hw = hardware()
    if backend == "pymc":
        hw["jax_devices"] = ["cpu:0"]  # nutpie samples on the CPU
    frame = inp["frame"]
    result = {
        "name": name,
        "reportable": True,
        "line": backend,
        "commit": commit,
        "dirty": False,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "dataset": frame.attrs["dataset"],
        "dataset_observations_sha256": frame.attrs["source_sha256"],
        "split": "rows",
        "split_seed": splits.SEED,
        "feature_set": "base-v1" if "features" in terms else "none",
        "feature_sources": feature_sources("base-v1"),
        "model": {
            "name": rung,
            "terms": list(terms),
            "trend_knot_months": TREND_KNOT_MONTHS,
            "backend": backend,
        },
        "sampler": f"nuts-{backend}",
        "sampler_settings": {
            "chains": CHAINS,
            "warmup": TUNE,
            "draws": DRAWS,
            "seed": SEED,
            "backend": "nutpie"
            if backend == "pymc"
            else "numpyro NUTS (vectorized chains)",
        },
        "dtype": "float64",
        "sizes": prep.sizes,
        "hardware": hw,
        "seconds": {
            "prepare": prep_seconds,
            "fit_total": fit_seconds,
            "sampling": fit_seconds,
        },
        "contention": load,
        "cost_usd": None,
        "diagnostics": diag,
        "score": scores,
        "interpretability": {
            "named_additive_contributions": True,
            "per_apartment_residuals": True,
            "uncertainty": "posterior draws",
        },
    }
    out_dir = RUNS / name
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_dir / "heldout.npz",
        audit_id=prep.test_audit_id,
        lpd=lpd,
        lpd_chain=lpd_chain.astype(np.float32),
    )
    np.savez_compressed(
        out_dir / "posterior.npz",
        **{
            f"draws/{k}": v.astype(np.float32)
            for k, v in draws.items()
            if k not in LARGE
        },
        **{
            f"{k}/{stat}": f(e[k], axis=0)
            for k in ("unit", "walk")
            if k in e
            for stat, f in (("mean", np.mean), ("sd", np.std))
        },
    )
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=float))

    t1 = time.perf_counter()
    audit, elpd, k, mcse, integrated = psis_training(e, terms, inp)
    s = e["alpha"].shape[0]
    thr = loo.k_threshold(s)
    loo_record = {
        "source_run": name,
        "source_commit": commit,
        "model": rung,
        "feature_set": result["feature_set"],
        "rows": len(elpd),
        "draws": s,
        "integrated": integrated,
        "unit_prior": "normal",
        "elpd_loo": float(elpd.sum()),
        "elpd_loo_se": float(elpd.std(ddof=1) * math.sqrt(len(elpd))),
        "elpd_loo_mcse": float(math.sqrt(np.sum(mcse**2))),
        "pareto_k": {
            "threshold": thr,
            "over_threshold": int((k > thr).sum()),
            "over_0_7": int((k > 0.7).sum()),
            "max": float(np.nanmax(k)),
            "share_over_threshold": float((k > thr).mean()),
        },
        "validation": {
            "note": "mean held-out lpd vs mean PSIS-LOO over all training rows",
            "heldout_rows": len(lpd),
            "heldout_mean_lpd": float(np.mean(lpd)),
            "psis_mean_lpd_multi_row_units": float(np.mean(elpd)),
        },
        "fit_seconds": fit_seconds,
        "hardware_fit": hw.get("gpu"),
        "commit": commit,
        "dirty": False,
        "seconds": time.perf_counter() - t1,
        "hardware": hw,
    }
    ldir = loo.LOO_ROOT / f"{name}-{commit[:7]}"
    ldir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        ldir / "pointwise.npz", audit_id=audit, elpd_loo=elpd, pareto_k=k, mcse=mcse
    )
    (ldir / "result.json").write_text(json.dumps(loo_record, indent=2))

    shares, rows = variance_shares(e, inp)
    vdir = variance.VARIANCE_ROOT / f"{name}-{commit[:7]}"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "result.json").write_text(
        json.dumps(
            {
                "source_run": name,
                "source_commit": commit,
                "model": rung,
                "feature_set": result["feature_set"],
                "rows": rows,
                "draws": s,
                "groups": list(variance.GROUPS),
                "shares": shares,
                "method": "covariance attribution of Var(mu) + Var(y - mu) over training rows, per draw",
                "commit": commit,
                "dirty": False,
                "hardware": hw,
            },
            indent=2,
        )
    )
    log(
        f"{name}: held-out dELPD {scores.get('vs_promoted', {}).get('delta_elpd', float('nan')):+.1f}; "
        f"PSIS-LOO {loo_record['elpd_loo']:.1f} ± {loo_record['elpd_loo_se']:.1f} (mcse {loo_record['elpd_loo_mcse']:.2f}, "
        f"k>{thr:.2f}: {loo_record['pareto_k']['over_threshold']}); residual share {100 * shares['residual']['mean']:.1f}%"
    )
    return name


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--backend", choices=("pymc", "numpyro"), required=True)
    parser.add_argument("rungs", nargs="+", choices=sorted(RUNGS))
    parser.add_argument(
        "--label",
        help="run-name suffix, e.g. the device when one backend runs on several",
    )
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    for rung in args.rungs:
        name = f"{rung}-{args.backend}-rows-{commit[:7]}"
        if args.label:
            name += f"-{args.label}"
        if (RUNS / name / "result.json").exists():
            print(f"skip {name}: exists", flush=True)
            continue
        fit(rung, args.backend, commit, name, log=lambda m: print(m, flush=True))
    print(f"done {dt.datetime.now(dt.UTC):%H:%M:%S} UTC", flush=True)


if __name__ == "__main__":
    main()
