"""Page-ready summary outputs of a recorded run, for the app's summary reader.

    JAX_PLATFORMS=cpu python -m rentfrontier.summary <run-name>

Reads the run's kept joint draws (posterior.npz) and the dataset it was fit
on; never fits. Refuses a dirty tree and records the commit, like `run.py`.
For every row of the dataset (in the fit or not) and every kept draw, the log
predictor splits into the named additive terms of `explain.log_terms`.
Writes /data1/apartments/frontier/summaries/<run>-<commit>/:

rows.parquet, one row per observation:
    identity     audit_id, unit_id, building, source_listing_id, period,
                 asking_rent, price_basis, in_fit
    fitted       fitted_rent (posterior median of exp(mu): the latent
                 conditional median ask), latent_rent_lower_95/upper_95,
                 residual_dollars (ask - fitted_rent), residual_log
    leave-own-row-out
                 loo_fitted_rent, loo_latent_rent_lower_95/upper_95,
                 loo_residual_log, loo_method, loo_pareto_k:
                 - "heldout": the row is not in the fit; its fitted value
                   already excludes its own ask;
                 - "psis": Pareto-smoothed importance weights proportional to
                   1 / p(y_i | draw) (k > 0.7 marks an unreliable estimate);
                 - "unit_prior": a unit with one row in the fit is informed
                   about its own effect only by that row, so leaving it out
                   returns the unit effect to its prior; drawn exactly
                   (Student-t level; the drift is 0 at the unit's own date);
    terms        <term>_log mean and 95% interval (additive log terms that
                 sum to the mean predictor) and <term>_usd mean and 95%
                 interval (LMDI dollar contributions against the market
                 reference; they sum to fitted - reference in every draw).
                 Rows of units with no fitted rows draw the unit level and
                 drift from their prior.
group-effects.jsonl  building levels and unit effects (log and percent: median,
                   95% interval, probability positive), in the schema of the
                   PyMC fits' group-effects.jsonl.
coefficients.csv   posterior summaries of feature coefficients (log scale and
                   percent) and scalar parameters.
terms.json         term names, descriptions and order.
complete.json      provenance (run, run commit, summary commit, dataset,
                   feature sources, gate diagnostics, score) and sha256 of
                   every file; written last.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time

import numpy as np
import pandas as pd

from . import data, explain, features, model, splits
from .run import git

SUMMARIES = data.OUTPUT_ROOT / "summaries"
VERSION = "frontier-summary-v1"
SEED = 20260924
CHUNK = 4000
TERM_TEXT = {
    "market": "offset + intercept + month trend + calendar season (reference apartment)",
    "bedroom_market_curve": "the bedroom group's own market-curve deviation",
    "building": "the building's level",
    "building_drift": "the building's half-year time walk at this month",
    "building_bedroom_premium": "the building's bedroom slope x (bedrooms - 1)",
    "building_feature_slopes": "the building's own slopes on size and baths",
    "unit": "the unit's own effect",
    "unit_drift": "the unit's own linear drift at this date",
}


def _t_logpdf(x, nu, scale):
    from scipy.special import gammaln

    z = x / scale
    return (
        gammaln((nu + 1) / 2)
        - gammaln(nu / 2)
        - 0.5 * np.log(nu * math.pi)
        - np.log(scale)
        - (nu + 1) / 2 * np.log1p(z * z / nu)
    )


def _weighted_quantiles(values, log_weights, probabilities):
    """values, log_weights: rows x draws -> (len(probabilities), rows)."""
    weights = np.exp(log_weights - log_weights.max(1, keepdims=True))
    order = np.argsort(values, axis=1)
    sorted_values = np.take_along_axis(values, order, axis=1)
    cumulative = np.cumsum(np.take_along_axis(weights, order, axis=1), axis=1)
    cumulative /= cumulative[:, -1:]
    out = np.empty((len(probabilities), values.shape[0]))
    for q, p in enumerate(probabilities):
        index = (cumulative < p).sum(1)
        out[q] = sorted_values[
            np.arange(values.shape[0]), np.minimum(index, values.shape[1] - 1)
        ]
    return out


def _q(x, axis=0):
    return np.quantile(x, [0.025, 0.5, 0.975], axis=axis)


def summarize(name: str):
    from arviz_stats.base import array_stats

    run_dir, result, kept = explain.load_run(name)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load()
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    for key, src in result.get("feature_sources", {}).items():
        now = features_source_sha(result["feature_set"]).get(key, {}).get("sha256")
        if now != src["sha256"]:
            raise SystemExit(f"feature source {key} differs from the run's record")
    heldout = splits.SPLITS[result["split"]](frame)
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    if not np.array_equal(
        prep.test_audit_id,
        np.load(run_dir / "heldout.npz", allow_pickle=True)["audit_id"],
    ):
        raise SystemExit("held-out rows differ from the run's recorded rows")
    names = [str(n) for n in feats.names]
    fslope_index = [names.index(n) for n in config.feature_slopes]
    draws = kept["alpha"].shape[0]
    rng = np.random.default_rng(SEED)
    unit_nu = kept.get("unit_nu", np.zeros(draws))
    t_units = bool((unit_nu > 0).all())
    fit_rows_per_unit = np.bincount(prep.train.unit, minlength=len(prep.units))
    single = fit_rows_per_unit == 1
    # Exact prior draws of the unit level, one per draw for each unit that
    # needs one: units listed once in the fit (leave-own-row-out) and units
    # with no fitted rows (their level and drift are unknown).
    level_z = (
        rng.standard_t(np.broadcast_to(unit_nu[:, None], (draws, len(prep.units))))
        if t_units
        else rng.standard_normal((draws, len(prep.units)))
    )
    unseen_ids = sorted(set(frame.unit_id[heldout]) - set(prep.units))
    unseen_index = {u: i for i, u in enumerate(unseen_ids)}
    unseen_level = (
        rng.standard_t(np.broadcast_to(unit_nu[:, None], (draws, len(unseen_ids))))
        if t_units
        else rng.standard_normal((draws, len(unseen_ids)))
    )
    unseen_drift = rng.standard_normal((draws, len(unseen_ids)))
    drift_scale = kept.get("unit_drift_scale", np.zeros(draws))

    tables, terms_order = [], None
    for chunk in np.array_split(np.arange(len(frame)), max(1, len(frame) // CHUNK)):
        mask = np.zeros(len(frame), dtype=bool)
        mask[chunk] = True
        a = model.row_arrays(prep, frame, mask)
        terms = explain.log_terms(
            kept,
            a,
            feats.groups,
            config.building_walk,
            config.bedroom_time,
            config.bedroom_slope,
            prep.offset,
            fslope_index,
        )
        sub = frame.loc[mask]
        new = a.unit < 0
        if new.any():
            col = np.array([unseen_index[u] for u in sub.unit_id[new]])
            terms["unit"][:, new] = kept["unit_scale"][:, None] * unseen_level[:, col]
            if "unit_drift" in terms:
                terms["unit_drift"][:, new] = (
                    drift_scale[:, None] * unseen_drift[:, col] * a.unit_time[new]
                )
        if terms_order is None:
            terms_order = list(terms)
        total = sum(terms.values())  # draws x rows, log rent
        log_ask = sub.log_rent.to_numpy()
        in_fit = ~heldout[mask]
        q = _q(total)
        out = pd.DataFrame(
            {
                "audit_id": sub.audit_id.to_numpy(),
                "unit_id": sub.unit_id.to_numpy(),
                "building": sub.building.to_numpy(),
                "source_listing_id": sub.source_listing_id.to_numpy(),
                "period": sub.period.dt.strftime("%Y-%m-%d").to_numpy(),
                "asking_rent": sub.asking_rent.to_numpy(),
                "price_basis": sub.price_basis.to_numpy(),
                "in_fit": in_fit,
                "fitted_rent": np.exp(q[1]),
                "latent_rent_lower_95": np.exp(q[0]),
                "latent_rent_upper_95": np.exp(q[2]),
                "residual_dollars": sub.asking_rent.to_numpy() - np.exp(q[1]),
                "residual_log": log_ask - q[1],
                "mean_log_rent": total.mean(0),
            }
        )
        # Leave-own-row-out.
        loo = q.copy()
        method = np.where(in_fit, "psis", "heldout").astype(object)
        pareto_k = np.full(len(sub), np.nan)
        fit_idx = np.flatnonzero(in_fit)
        if len(fit_idx):
            loglik = _t_logpdf(
                log_ask[None, fit_idx] - total[:, fit_idx],
                kept["nu"][:, None],
                kept["sigma"][:, None],
            )
            log_w, k = array_stats.psislw(loglik.T, axis=-1)
            loo[:, fit_idx] = _weighted_quantiles(
                total[:, fit_idx].T, np.asarray(log_w), (0.025, 0.5, 0.975)
            )
            pareto_k[fit_idx] = np.asarray(k, dtype=float)
        once = in_fit & (a.unit >= 0)
        once[once] = single[a.unit[once]]
        if once.any():
            u = a.unit[once]
            replaced = (
                total[:, once]
                - terms["unit"][:, once]
                + kept["unit_scale"][:, None] * level_z[:, u]
            )
            if "unit_drift" in terms:
                # A unit's only fitted row sits at its own mean date: drift 0.
                replaced = replaced - terms["unit_drift"][:, once]
            loo[:, once] = _q(replaced)
            method[once] = "unit_prior"
            pareto_k[once] = np.nan
        cols = {
            "loo_fitted_rent": np.exp(loo[1]),
            "loo_latent_rent_lower_95": np.exp(loo[0]),
            "loo_latent_rent_upper_95": np.exp(loo[2]),
            "loo_residual_log": log_ask - loo[1],
            "loo_method": method,
            "loo_pareto_k": pareto_k,
        }
        dollars, _ = explain.decompose(terms)
        for term in terms_order:
            tq = np.quantile(terms[term], [0.025, 0.975], axis=0)
            cols[f"{term}_log"] = terms[term].mean(0)
            cols[f"{term}_log_lower_95"], cols[f"{term}_log_upper_95"] = tq
            dq = np.quantile(dollars[term], [0.025, 0.975], axis=0)
            cols[f"{term}_usd"] = dollars[term].mean(0)
            cols[f"{term}_usd_lower_95"], cols[f"{term}_usd_upper_95"] = dq
        out = pd.concat([out, pd.DataFrame(cols)], axis=1)
        tables.append(out)
    rows = pd.concat(tables, ignore_index=True)

    coef = []
    beta = kept["beta"]
    for j, (n, g) in enumerate(zip(names, feats.groups)):
        b = beta[:, j]
        lo, med, hi = _q(b)
        coef.append(
            {
                "name": n,
                "group": str(g),
                "kind": "feature",
                "mean": b.mean(),
                "sd": b.std(ddof=1),
                "median": med,
                "lower_95": lo,
                "upper_95": hi,
                "percent_median": 100 * math.expm1(med),
                "percent_lower_95": 100 * math.expm1(lo),
                "percent_upper_95": 100 * math.expm1(hi),
            }
        )
    for n, v in kept.items():
        if v.ndim == 1:
            lo, med, hi = _q(v)
            coef.append(
                {
                    "name": n,
                    "group": "scalar",
                    "kind": "scalar",
                    "mean": v.mean(),
                    "sd": v.std(ddof=1),
                    "median": med,
                    "lower_95": lo,
                    "upper_95": hi,
                }
            )
    effects = []
    for kind, ids, values in (
        ("building", prep.buildings, kept["building"]),
        ("unit", prep.units, kept["unit"]),
    ):
        lo, med, hi = _q(values)
        pos = (values > 0).mean(0)
        for j, ident in enumerate(ids):
            log = {
                "lower_95": float(lo[j]),
                "median": float(med[j]),
                "probability_positive": float(pos[j]),
                "upper_95": float(hi[j]),
            }
            effects.append(
                {
                    "id": str(ident),
                    "kind": kind,
                    "log_effect": log,
                    "percent_effect": {
                        k: (100 * math.expm1(v) if k != "probability_positive" else v)
                        for k, v in log.items()
                    },
                }
            )
    terms_meta = {
        "order": terms_order,
        "feature_groups": list(dict.fromkeys(str(g) for g in feats.groups)),
        "descriptions": {
            t: TERM_TEXT.get(t, f"sum of x * beta over the {t} feature columns")
            for t in terms_order
        },
        "reference": "market: a reference-level apartment (all features at their reference level) in an average building that month",
    }
    meta = {
        "run": name,
        "run_commit": result["commit"],
        "model": result["model"]["name"],
        "feature_set": result["feature_set"],
        "split": result["split"],
        "dataset": frame.attrs["dataset"],
        "dataset_observations_sha256": frame.attrs["source_sha256"],
        "feature_sources": result.get("feature_sources", {}),
        "rows": len(rows),
        "rows_in_fit": int(rows.in_fit.sum()),
        "draws": {
            "kept": draws,
            "chains": result["sampler_settings"]["chains"],
            "kept_per_chain": draws // result["sampler_settings"]["chains"],
        },
        "sampler": result["sampler"],
        "sampler_settings": result["sampler_settings"],
        "hardware": result["hardware"],
        "fit_seconds": result["seconds"]["fit_total"],
        "diagnostics": {
            k: result["diagnostics"].get(k)
            for k in (
                "max_rhat",
                "max_rhat_name",
                "min_ess",
                "min_ess_name",
                "passes",
                "group_rhat",
            )
            if k in result["diagnostics"]
        },
        "score": result["score"],
        "loo": {
            "methods": rows.loo_method.value_counts().to_dict(),
            "psis_pareto_k_above_0_7": int((rows.loo_pareto_k > 0.7).sum()),
            "psis_pareto_k_max": float(np.nanmax(rows.loo_pareto_k))
            if rows.loo_pareto_k.notna().any()
            else None,
            "note": f"PSIS over {draws} kept draws; Pareto k is less reliable at this draw count than at full draw counts",
        },
        "seed": SEED,
        "uncertainty": "Conditional posterior uncertainty of the latent conditional-median ask; source errors, omitted features and incomplete market coverage remain separate.",
    }
    return rows, pd.DataFrame(coef), effects, terms_meta, meta


def features_source_sha(feature_set):
    from .run import feature_sources

    return feature_sources(feature_set)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    out_dir = SUMMARIES / f"{args.run}-{commit[:7]}"
    if (out_dir / "complete.json").exists():
        raise SystemExit(f"{out_dir} is already complete")
    t0 = time.perf_counter()
    rows, coef, effects, terms_meta, meta = summarize(args.run)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(out_dir / "rows.parquet", index=False)
    coef.to_csv(out_dir / "coefficients.csv", index=False)
    (out_dir / "terms.json").write_text(json.dumps(terms_meta, indent=2))
    (out_dir / "group-effects.jsonl").write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in effects)
    )
    files = ("rows.parquet", "coefficients.csv", "group-effects.jsonl", "terms.json")
    meta.update(
        version=VERSION,
        summary_commit=commit,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        seconds=time.perf_counter() - t0,
        files={f: sha256(out_dir / f) for f in files},
    )
    (out_dir / "complete.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps({k: meta[k] for k in ("rows", "rows_in_fit", "loo", "seconds")}))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
