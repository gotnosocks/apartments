"""Per-listing estimates of a recorded run: the input of the listings site.

    uv run --extra gpu python -m rentfrontier.summary <run-name>

Reads the run's kept joint draws and the dataset it was fit on; never fits.
Refuses a dirty tree, a changed dataset or feature source (the files the
feature set reads now, against the run's record), a unit-split run (rows of
unseen units would lose their unit prior), and a run that fails the
convergence gate (`--allow-failing` for experiments; the gate status is
recorded either way).

For every row of the dataset, in the fit or held out:

estimate      leave-own-row-out estimate of the row's latent rent exp(mu):
              the median ask of this apartment, in this building, that
              month, given every other row in the fit but not the row's
              own ask.
              - held-out rows (not in the fit): the posterior as is;
              - rows in the fit: the unit level is integrated given the
                unit's other rows, as in `loo`; per draw, a level is drawn
                from that conditional (on `loo`'s grid, uniform within the
                cell) and the draws are reweighted by Pareto-smoothed
                importance weights 1 / p(y_i | theta, y_{u,-i}). A unit
                listed once in the fit gets a draw from the unit prior.
                pareto_k above `loo.k_threshold` marks an unreliable
                estimate.
              Weighted mean, median and 95% interval; residual_usd is the
              ask less the mean, residual_pct the ask over the mean, less 1.
pit           where the ask falls in the leave-own-row-out predictive
              distribution (Student-t noise included): about 0.5 is typical,
              below 0.025 or above 0.975 unusual.
fitted_rent   the in-sample posterior of exp(mu), mean and 95% interval (the
              fit saw the row's ask; a review signal, not an out-of-sample
              error).
<term>_usd    dollar contributions of the estimate: the LMDI decomposition of
              `explain`, per draw, against the market reference (a reference
              apartment in an average building that month). Weighted means
              add up to the estimate exactly; 95% intervals.
inputs        the row's nonzero model inputs, JSON {feature name: value}.

Writes /data1/apartments/frontier/summaries/<run>-<commit>/:

rows.parquet          one row per dataset row (the columns above plus
                      audit_id, unit_id after the run's data rules, building,
                      period, asking_rent, in_fit, unit_fit_rows).
market.parquet        per month: the market reference rent (with and without
                      the calendar season), mean and 95% interval.
buildings.parquet     per building: level and yearly trend as percentages,
                      mean, 95% interval, training rows and units.
coefficients.parquet  per feature column: exp(beta) - 1, mean, 95% interval
                      and probability positive.
terms.json            the contribution terms in display order, with labels.
complete.json         provenance (run, commits, dataset and feature-source
                      sha256, gate, PSIS-LOO score, draws) and the sha256 of
                      every file; written last.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, explain, features, leaderboard, loo, model, splits
from . import run as run_module
from .run import git, hardware

SUMMARIES = data.OUTPUT_ROOT / "summaries"
VERSION = "frontier-summary-v1"
SEED = 20260926
SPLITS = ("rows", "all")  # every held-out row's unit has rows in the fit
PROBABILITIES = (0.025, 0.5, 0.975)

# Display labels of the non-feature terms (feature groups are labelled by name).
TERM_LABELS = {
    "market": "Market reference",
    "bedroom_market_curve": "Bedroom-group market curve",
    "building": "Building",
    "building_drift": "Building over time",
    "line": "Line within building",
    "building_bedroom_premium": "Building bedroom premium",
    "building_feature_slopes": "Building size and bath slopes",
    "unit": "This unit",
    "price_basis": "Price basis",
    "unit label": "Unit label",
    "hvac": "HVAC",
}
TERM_TEXT = {
    "market": "A reference apartment (one bedroom, one bath, every attribute at "
    "its reference level) in an average building that month: offset, "
    "intercept, market trend and calendar season.",
    "bedrooms": "Bedroom count, against a one-bedroom.",
    "bathrooms": "Full and half bathrooms, against one full bath.",
    "size": "Square feet against the typical size for the bedroom count, or "
    "size not stated.",
    "floor": "The floor, with steps above the 6th and 15th floors, and walk-up "
    "floors in buildings without an elevator.",
    "elevator": "Elevator in the building (or not stated).",
    "doorman": "Doorman: full-time, part-time, virtual, none or not stated.",
    "laundry": "Laundry in the unit (or not stated), against laundry in the "
    "building or none.",
    "hvac": "Central air or other heating and cooling, against not stated.",
    "pets": "The pet policy.",
    "views": "Views the listing states (city, park, water, skyline, ...).",
    "windows": "Window exposures the listing states.",
    "unit label": "Penthouse, garden and lower-level units, from the unit label.",
    "price_basis": "A current capture's gross ask, against the first ask of a "
    "past advertisement.",
    "description": "Flags from the advertisement's own text (renovated, "
    "dishwasher, no fee, rent stabilized, ...), or no text.",
    "bedroom_market_curve": "The bedroom group's own market-curve deviation.",
    "building": "The building's level against an average building.",
    "building_drift": "The building's own movement over time (walk or trend).",
    "line": "The unit's line (column) within its building.",
    "building_bedroom_premium": "The building's own bedroom slope.",
    "building_feature_slopes": "The building's own slopes on size and baths.",
    "unit": "The unit's own effect, from the unit's other listings only.",
}


def present_terms(config: model.ModelConfig, groups, line: bool) -> list[str]:
    """Contribution terms of a design in display order (terms the design does
    not have are identically zero and are left out)."""
    names = ["market", *dict.fromkeys(groups)]
    names += ["bedroom_market_curve"] if config.bedroom_time else []
    names += ["building"]
    names += ["building_drift"] if config.building_walk or config.building_trend else []
    names += ["line"] if line else []
    names += ["building_bedroom_premium"] if config.bedroom_slope else []
    names += ["building_feature_slopes"] if config.feature_slopes else []
    names += ["unit"] if config.units else []
    return names


def normalized_weights(log_w: np.ndarray) -> np.ndarray:
    """(draws, rows) log weights -> weights summing to 1 over draws."""
    w = np.exp(log_w - log_w.max(0, keepdims=True))
    return w / w.sum(0, keepdims=True)


def psis_log_weights(loglik):
    """(draws, rows) log densities -> Pareto-smoothed log importance weights
    proportional to 1 / p(y_i | draw), (draws, rows), and Pareto k per row."""
    from arviz_stats.base import array_stats

    # arviz_stats' psislw takes the log-likelihood and negates it internally.
    log_w, k = array_stats.psislw(np.asarray(loglik, float).T, axis=-1)
    return np.asarray(log_w).T, np.asarray(k, float)


def weighted_quantiles(values, weights, probabilities=PROBABILITIES):
    """values, weights: (draws, rows) -> (len(probabilities), rows): the
    smallest value whose cumulative weight reaches each probability."""
    order = np.argsort(values, axis=0)
    ordered = np.take_along_axis(values, order, axis=0)
    cumulative = np.cumsum(np.take_along_axis(weights, order, axis=0), axis=0)
    cumulative /= cumulative[-1:]
    cols = np.arange(values.shape[1])
    out = np.empty((len(probabilities), values.shape[1]))
    for q, p in enumerate(probabilities):
        index = np.minimum((cumulative < p).sum(0), values.shape[0] - 1)
        out[q] = ordered[index, cols]
    return out


def loo_unit_levels(y, rest, seg, n_seg, params, key, *, t_units):
    """Leave-own-row-out unit levels for rows sorted into whole units.

    y: (rows,) log rent less offset; rest: (draws, rows) predictor without the
    unit terms; seg: (rows,) unit segments in [0, n_seg); params: dict of
    (draws,) arrays nu, sigma, unit_scale (and unit_nu for t_units).

    Returns (loglik, level), each (draws, rows): loglik is
    log p(y_i | theta_s, y_{u,-i}) with the unit level integrated, exactly as
    `loo.integrated_loglik`, and level one draw of the unit level from
    p(a | theta_s, y_{u,-i}) on the same grid, uniform within its cell.
    """
    import jax
    import jax.numpy as jnp
    from jax.scipy.special import logsumexp

    from .collect import student_t_logpdf

    lo, hi, n = loo.GRID
    z = jnp.linspace(lo, hi, n, dtype=jnp.float64)
    step = (hi - lo) / (n - 1)
    log_dz = math.log(step)
    ones = jnp.ones(y.shape[0])
    y = jnp.asarray(y)
    seg = jnp.asarray(seg)

    def one(args):
        rest_s, p, k = args
        if t_units:
            log_wz = student_t_logpdf(z, jnp.maximum(p["unit_nu"], 1e-3), 1.0)
        else:
            log_wz = -0.5 * z * z - 0.5 * math.log(2 * math.pi)
        w = log_wz + log_dz
        ll = student_t_logpdf(
            (y - rest_s)[:, None] - p["unit_scale"] * z[None, :], p["nu"], p["sigma"]
        )  # (rows, grid)
        total = jax.ops.segment_sum(ll, seg, num_segments=n_seg)
        count = jax.ops.segment_sum(ones, seg, num_segments=n_seg)
        log_unit = logsumexp(total + w[None], axis=1)
        # The unit's other rows (none for a unit's only row: the prior).
        others = total[seg] - ll + w[None]
        log_rest = jnp.where(count[seg] == 1, 0.0, logsumexp(others, axis=1))
        k_cell, k_jitter = jax.random.split(k)
        cell = jax.random.categorical(k_cell, others, axis=1)
        jitter = jax.random.uniform(
            k_jitter, cell.shape, minval=-step / 2, maxval=step / 2
        )
        return log_unit[seg] - log_rest, p["unit_scale"] * (z[cell] + jitter)

    names = ["nu", "sigma", "unit_scale"] + (["unit_nu"] if t_units else [])
    p = {k: jnp.asarray(params[k]) for k in names}
    keys = jax.random.split(key, rest.shape[0])
    loglik, level = jax.lax.map(one, (jnp.asarray(rest), p, keys))
    return np.asarray(loglik), np.asarray(level)


def _stats(prefix, values, weights, table):
    mean = (values * weights).sum(0)
    q = weighted_quantiles(values, weights)
    table[prefix] = mean
    table[f"{prefix}_lower_95"], table[f"{prefix}_upper_95"] = q[0], q[2]
    return mean, q


def row_table(sub, terms, log_w, pareto_k, fitted, sigma, nu, names, inputs):
    """One chunk's output rows. terms: the leave-own-row-out log terms
    (draws, rows); log_w: (draws, rows) log importance weights (0 = the
    posterior as is); fitted: (draws, rows) in-sample exp(mu)."""
    from scipy import stats

    weights = normalized_weights(log_w)
    dollars, rent = explain.decompose(terms)
    total = sum(terms.values())
    log_ask = np.log(sub.asking_rent.to_numpy())
    table = {
        "audit_id": sub.audit_id.to_numpy(),
        "unit_id": sub.unit_id.to_numpy(),
        "building": sub.building.to_numpy(),
        "period": sub.period.dt.strftime("%Y-%m-%d").to_numpy(),
        "asking_rent": sub.asking_rent.to_numpy(),
    }
    mean, q = _stats("estimate", rent, weights, table)
    table["estimate_median"] = q[1]
    table["residual_usd"] = table["asking_rent"] - mean
    table["residual_pct"] = table["asking_rent"] / mean - 1.0
    table["pareto_k"] = pareto_k
    cdf = stats.t.cdf((log_ask[None] - total) / sigma[:, None], nu[:, None])
    table["pit"] = (cdf * weights).sum(0)
    flat = np.full_like(fitted, 1.0 / fitted.shape[0])
    _stats("fitted_rent", fitted, flat, table)
    for name in names:
        _stats(f"{name}_usd", dollars[name], weights, table)
    table["inputs"] = inputs
    return pd.DataFrame(table, index=sub.index)


def row_inputs(feats: features.Features, rows: np.ndarray) -> list[str]:
    values = feats.values[rows]
    return [
        json.dumps(
            {feats.names[j]: round(float(v[j]), 4) for j in np.flatnonzero(v)},
            separators=(",", ":"),
        )
        for v in values
    ]


def chunk_rows(draws: int) -> int:
    """Rows per batch of whole units, so draws x rows x terms stays near 1 GB."""
    return int(min(1024, max(256, 2_250_000 // draws)))


def check_run(result):
    """Refuse runs whose held-out rows could belong to units with no rows in
    the fit, and feature sources that differ now from the run's record: the
    files the feature set reads today (`run.feature_sources`), not the paths
    recorded then."""
    if result["split"] not in SPLITS:
        raise SystemExit(
            f"{result['split']}-split runs are not summarized (splits: {SPLITS})"
        )
    now = run_module.feature_sources(result["feature_set"])
    for key, src in result.get("feature_sources", {}).items():
        if key not in now or now[key]["sha256"] != src["sha256"]:
            raise SystemExit(f"feature source {key} differs from the run's record")


def verify_run(result, frame, heldout, prep, run_dir, post_units, post_buildings):
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    recorded = np.load(run_dir / "heldout.npz", allow_pickle=True)["audit_id"]
    if not np.array_equal(frame.audit_id.to_numpy()[heldout], recorded):
        raise SystemExit("held-out rows differ from the run's recorded rows")
    if not (
        np.array_equal(prep.units, post_units)
        and np.array_equal(prep.buildings, post_buildings)
    ):
        raise SystemExit("units or buildings differ from the run's saved draws")


def gate(result, run_dir) -> dict:
    g_max, g_pass, g_method = leaderboard.group_gate(dict(result, _dir=run_dir))
    d = result["diagnostics"]
    return {
        "passes": bool(d["passes"] and g_pass),
        "max_rhat": d["max_rhat"],
        "min_ess": d["min_ess"],
        "divergences": d.get("divergences"),
        "group_rhat_max": g_max,
        "group_rhat_method": g_method,
    }


def summarize(name: str, allow_failing: bool = False):
    import jax

    jax.config.update("jax_enable_x64", True)
    run_dir, result, kept = explain.load_run(name)
    gate_status = gate(result, run_dir)
    if not gate_status["passes"] and not allow_failing:
        raise SystemExit(f"{name} fails the convergence gate: {gate_status}")
    if "unit_drift" in kept and kept["unit_drift"].shape[1] > 1:
        raise SystemExit("unit-drift designs are not supported (drift not integrated)")
    check_run(result)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load(Path(result["dataset"]))
    heldout = splits.SPLITS[result["split"]](frame)
    frame = data.apply_rules(frame, result.get("data_rules", ()))
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    post = np.load(run_dir / "posterior.npz", allow_pickle=True)
    verify_run(result, frame, heldout, prep, run_dir, post["units"], post["buildings"])
    draws = kept["alpha"].shape[0]
    t_units = bool((kept.get("unit_nu", np.zeros(draws)) > 0).all())
    line = bool(np.any(kept.get("line_scale", 0) > 0))
    names = present_terms(config, feats.groups, line)
    fslope_index = [feats.names.index(n) for n in config.feature_slopes]
    params = {k: kept[k] for k in ("nu", "sigma", "unit_scale", "unit_nu") if k in kept}
    sigma, nu = kept["sigma"], kept["nu"]
    key = jax.random.PRNGKey(SEED)

    def terms_for(mask):
        a = model.row_arrays(prep, frame, mask)
        terms = explain.log_terms(
            kept,
            a,
            feats.groups,
            model.walk_spacing(config),
            config.bedroom_time,
            config.bedroom_slope,
            prep.offset,
            fslope_index,
            unit_line=prep.unit_line,
        )
        return a, terms

    tables = []
    # Rows in the fit, sorted into whole units.
    train_idx = np.flatnonzero(~heldout)
    unit_of = pd.Index(prep.units).get_indexer(frame.unit_id.to_numpy()[train_idx])
    order = np.argsort(unit_of, kind="stable")
    rows_sorted, units_sorted = train_idx[order], unit_of[order]
    chunk = chunk_rows(draws)
    for lo, hi in loo.unit_chunks(units_sorted, chunk):
        rows = np.sort(rows_sorted[lo:hi])  # frame order, as row_arrays returns
        mask = np.zeros(len(frame), dtype=bool)
        mask[rows] = True
        a, terms = terms_for(mask)
        fitted = np.exp(sum(terms.values()))
        rest = sum(v for k, v in terms.items() if k not in loo.UNIT_TERMS)
        _, seg = np.unique(a.unit, return_inverse=True)
        pad = chunk - len(rows)
        # Pad to a fixed shape (one compile); padded rows are their own units.
        key, sub_key = jax.random.split(key)
        loglik, level = loo_unit_levels(
            np.r_[a.y, np.zeros(pad)],
            np.concatenate([rest - prep.offset, np.zeros((draws, pad))], axis=1),
            np.r_[seg, seg.max() + 1 + np.arange(pad)],
            chunk,
            params,
            sub_key,
            t_units=t_units,
        )
        loglik, level = loglik[:, : len(rows)], level[:, : len(rows)]
        terms["unit"] = level
        log_w, k = psis_log_weights(loglik)
        tables.append(
            row_table(
                frame.loc[mask],
                terms,
                log_w,
                k,
                fitted,
                sigma,
                nu,
                names,
                row_inputs(feats, rows),
            )
        )
    # Held-out rows: the fit never saw them; the posterior is the estimate.
    held_idx = np.flatnonzero(heldout)
    for rows in np.array_split(held_idx, max(1, math.ceil(len(held_idx) / chunk))):
        if not len(rows):
            continue
        mask = np.zeros(len(frame), dtype=bool)
        mask[rows] = True
        _, terms = terms_for(mask)
        fitted = np.exp(sum(terms.values()))
        tables.append(
            row_table(
                frame.loc[mask],
                terms,
                np.zeros((draws, len(rows))),
                np.full(len(rows), np.nan),
                fitted,
                sigma,
                nu,
                names,
                row_inputs(feats, rows),
            )
        )
    table = pd.concat(tables).sort_index()
    if len(table) != len(frame) or table.audit_id.duplicated().any():
        raise AssertionError("every dataset row must appear exactly once")
    table.insert(5, "in_fit", ~heldout)
    fit_rows = np.bincount(prep.train.unit, minlength=len(prep.units))
    unit_index = pd.Index(prep.units).get_indexer(table.unit_id)
    table.insert(6, "unit_fit_rows", np.where(unit_index >= 0, fit_rows[unit_index], 0))
    table.insert(
        8, "estimate_method", np.where(heldout, "heldout", "psis").astype(object)
    )
    return {
        "result": result,
        "run_dir": run_dir,
        "gate": gate_status,
        "draws": draws,
        "names": names,
        "rows": table,
        "market": market_table(kept, prep),
        "buildings": building_table(kept, prep),
        "coefficients": coefficient_table(kept, feats),
        "k_threshold": loo.k_threshold(draws),
    }


def _summary(x, axis=0):
    q = np.quantile(x, [PROBABILITIES[0], PROBABILITIES[2]], axis=axis)
    return x.mean(axis), q[0], q[1]


def market_table(kept, prep) -> pd.DataFrame:
    """The market reference rent per month: a reference apartment in an
    average building (the `market` term), with and without the season."""
    months = np.arange(len(prep.periods))
    calendar = prep.periods.month.to_numpy() - 1
    trend = prep.offset + kept["alpha"][:, None] + kept["trend"][:, months]
    out = {"period": prep.periods.strftime("%Y-%m-%d")}
    for label, log_rent in (
        ("reference_rent", trend + kept["season"][:, calendar]),
        ("reference_rent_deseasoned", trend),
    ):
        mean, lo, hi = _summary(np.exp(log_rent))
        out[label], out[f"{label}_lower_95"], out[f"{label}_upper_95"] = mean, lo, hi
    return pd.DataFrame(out)


def building_table(kept, prep) -> pd.DataFrame:
    rows = np.bincount(prep.train.building, minlength=len(prep.buildings))
    first_unit_building = (
        pd.Series(prep.train.building).groupby(prep.train.unit).first()
    )
    units = np.bincount(first_unit_building.to_numpy(), minlength=len(prep.buildings))
    out = {"building": prep.buildings, "fit_rows": rows, "fit_units": units}
    for label, log_value in (
        ("level_pct", kept["building"]),
        ("trend_pct_per_year", kept.get("building_trend")),
    ):
        if log_value is None or log_value.shape[1] != len(prep.buildings):
            continue
        pct = 100.0 * np.expm1(log_value)
        mean, lo, hi = _summary(pct)
        out[label], out[f"{label}_lower_95"], out[f"{label}_upper_95"] = mean, lo, hi
    return pd.DataFrame(out)


def coefficient_table(kept, feats: features.Features) -> pd.DataFrame:
    pct = 100.0 * np.expm1(kept["beta"])
    mean, lo, hi = _summary(pct)
    return pd.DataFrame(
        {
            "feature": feats.names,
            "group": feats.groups,
            "pct": mean,
            "pct_lower_95": lo,
            "pct_upper_95": hi,
            "probability_positive": (kept["beta"] > 0).mean(0),
        }
    )


def terms_record(names) -> list[dict]:
    return [
        {
            "name": n,
            "label": TERM_LABELS.get(n, n.replace("_", " ").capitalize()),
            "description": TERM_TEXT.get(n, f"Listing attributes ({n})."),
        }
        for n in names
    ]


def loo_score(run: str) -> dict | None:
    """The run's recorded PSIS-LOO score (the newest), if any."""
    found = sorted(
        loo.LOO_ROOT.glob(f"{run}-*/result.json"), key=lambda p: p.stat().st_mtime
    )
    records = [json.loads(p.read_text()) for p in found]
    records = [r for r in records if r.get("source_run") == run]
    if not records:
        return None
    r = records[-1]
    return {
        "commit": r["commit"],
        "elpd_loo": r["elpd_loo"],
        "elpd_loo_se": r["elpd_loo_se"],
        "pareto_k": r["pareto_k"],
    }


def write(out: dict, out_dir: Path, commit: str, seconds: float) -> Path:
    tmp = out_dir.with_name(out_dir.name + ".tmp")
    tmp.mkdir(parents=True, exist_ok=False)
    out["rows"].to_parquet(tmp / "rows.parquet", index=False)
    out["market"].to_parquet(tmp / "market.parquet", index=False)
    out["buildings"].to_parquet(tmp / "buildings.parquet", index=False)
    out["coefficients"].to_parquet(tmp / "coefficients.parquet", index=False)
    (tmp / "terms.json").write_text(json.dumps(terms_record(out["names"]), indent=2))
    result = out["result"]
    rows = out["rows"]
    k = rows.pareto_k.to_numpy()
    record = {
        "version": VERSION,
        "run": result["name"],
        "run_commit": result["commit"],
        "commit": commit,
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "seconds": seconds,
        "hardware": hardware(),
        "dataset": result["dataset"],
        "dataset_observations_sha256": result["dataset_observations_sha256"],
        "data_rules": result.get("data_rules", []),
        "feature_set": result["feature_set"],
        "feature_sources": result.get("feature_sources", {}),
        "model": result["model"],
        "split": result["split"],
        "sampler": result.get("sampler"),
        "fit_seconds": result["seconds"]["fit_total"],
        "fit_hardware": result["hardware"].get("gpu") or result["hardware"]["cpu"],
        "fit_started_at": result.get("started_at"),
        "draws": out["draws"],
        "gate": out["gate"],
        "psis_loo": loo_score(result["name"]),
        "rows": len(rows),
        "rows_in_fit": int(rows.in_fit.sum()),
        "estimate_pareto_k": {
            "threshold": out["k_threshold"],
            "over_threshold": int(np.nansum(k > out["k_threshold"])),
            "max": float(np.nanmax(k)),
        },
        "terms": out["names"],
        "files": {p.name: data.sha256(p) for p in sorted(tmp.iterdir()) if p.is_file()},
    }
    (tmp / "complete.json").write_text(json.dumps(record, indent=2))
    tmp.rename(out_dir)
    return out_dir


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run")
    parser.add_argument(
        "--allow-failing",
        action="store_true",
        help="summarize a run that fails the convergence gate (recorded)",
    )
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    out_dir = SUMMARIES / f"{args.run}-{commit[:7]}"
    if (out_dir / "complete.json").exists():
        raise SystemExit(f"{out_dir} exists")
    t0 = time.perf_counter()
    out = summarize(args.run, args.allow_failing)
    path = write(out, out_dir, commit, time.perf_counter() - t0)
    rows = out["rows"]
    print(
        f"wrote {path}: {len(rows)} rows ({int(rows.in_fit.sum())} in the fit), "
        f"{out['draws']} draws, {time.perf_counter() - t0:.0f} s",
        flush=True,
    )


if __name__ == "__main__":
    main()
