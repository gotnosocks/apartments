"""Integrated PSIS-LOO over a recorded run's training rows, from its kept draws.

    uv run --extra gpu python -m rentfrontier.loo <run-name> [<run-name> ...]

No refit. The score is the expected log predictive density of each training
row given all the other training rows,

    elpd_loo = sum_i log p(y_i | y_-i),

estimated by Pareto-smoothed importance sampling (PSIS, Vehtari, Gelman and
Gabry 2017; Vehtari et al. 2024) over the run's kept joint draws.

Integrated over the unit effect. A row strongly informs its own unit's
effect (most units have one to three rows), which makes plain PSIS unstable
(high Pareto k). For every draw of the other parameters theta, the row's
unit effect is integrated exactly given that unit's other rows:

    p(y_i | theta, y_{u,-i}) = p(y_u | theta) / p(y_{u,-i} | theta),
    p(y_S | theta) = int prod_{j in S} p(y_j | theta, a) p(a | theta) da,

with the unit level on a fixed grid over its prior (Gaussian or Student-t)
and, in designs with unit drift, the drift by 8-node Gauss-Hermite: the same
quadrature as the unseen-unit scoring in `collect` (tested against SciPy).
PSIS then reweights draws of theta by 1 / p(y_i | theta, y_{u,-i}). A unit
listed once gets its prior-predictive density; the level grid carries the
prior density times the spacing without renormalization, so Student-t prior
mass beyond +/-40 unit scales (about 6e-4 at unit_nu = 2) is dropped rather
than redistributed onto the grid, where the likelihood is negligible anyway. Building-level terms
are not integrated; rows of small buildings can still have high k, which is
reported.

Reliability. Pareto k is reported per row, with the sample-size-dependent
threshold min(1 - 1/log10(S), 0.7) for S draws; rows above it are counted.

Comparability. Every row-split run is fit on the same 47,374 training rows
(seed 20260922), so scores pair row by row across all row-split runs. The
run's own held-out rows (a genuine leave-out of repeat-listed units) give an
independent check: `validation` compares their mean held-out lpd with the
mean PSIS-LOO over training rows of the same kind of unit.

Writes /data1/apartments/frontier/loo/<run>-<commit>/{result.json,
pointwise.npz}. Refuses a dirty tree.
"""

from __future__ import annotations

import argparse
import json
import math
import time

import numpy as np

from . import data, explain, features, model, splits
from .run import git, hardware

LOO_ROOT = data.OUTPUT_ROOT / "loo"
CHUNK = 4096  # rows per device batch (whole units only)
GRID = (-40.0, 40.0, 401)  # unit-level grid in units of unit_scale (spacing 0.2)
DRIFT_NODES = 8
UNIT_TERMS = ("unit", "unit_drift")


def k_threshold(draws: int) -> float:
    return min(1.0 - 1.0 / math.log10(draws), 0.7)


def integrated_loglik(y, mu, seg, n_seg, unit_time, params, *, t_units, drift):
    """(draws, rows) log p(y_j | theta_s, y_{u(j),-j}) with the unit effect integrated.

    y: (rows,); mu: (draws, rows) predictor without unit terms; seg: (rows,)
    unit segment ids in [0, n_seg); unit_time: (rows,) years from the unit's
    mean training date; params: dict of (draws,) arrays nu, sigma,
    unit_scale, and unit_nu (t_units) / unit_drift_scale (drift).
    """
    import jax
    import jax.numpy as jnp
    from jax.scipy.special import logsumexp

    from .collect import student_t_logpdf

    z = jnp.linspace(*GRID[:2], GRID[2], dtype=jnp.float64)
    xd, wd = np.polynomial.hermite.hermgauss(DRIFT_NODES if drift else 1)
    xd = jnp.asarray(xd if drift else [0.0])
    # Drift: Gauss-Hermite weights normalized to 1 (exact for the normal drift).
    log_wd = jnp.log(jnp.asarray(wd) / math.sqrt(math.pi)) if drift else jnp.zeros(1)
    log_dz = math.log((GRID[1] - GRID[0]) / (GRID[2] - 1))
    ones = jnp.ones(y.shape[0])
    y = jnp.asarray(y)
    seg = jnp.asarray(seg)
    unit_time = jnp.asarray(unit_time)

    def one(args):
        mu_s, p = args
        # Level: prior density x grid spacing, not renormalized over the grid,
        # so prior mass beyond the grid's range (heavy Student-t tails) is not
        # redistributed onto it.
        if t_units:
            log_wz = student_t_logpdf(z, jnp.maximum(p["unit_nu"], 1e-3), 1.0)
        else:
            log_wz = -0.5 * z * z - 0.5 * math.log(2 * math.pi)
        w = log_wd[:, None] + log_wz[None, :] + log_dz
        drift_off = (
            math.sqrt(2.0) * p["unit_drift_scale"] * unit_time[:, None] * xd[None]
            if drift
            else jnp.zeros((y.shape[0], 1))
        )
        resid = y - mu_s
        ll = student_t_logpdf(
            resid[:, None, None]
            - p["unit_scale"] * z[None, None, :]
            - drift_off[:, :, None],
            p["nu"],
            p["sigma"],
        )  # (rows, D, G)
        total = jax.ops.segment_sum(ll, seg, num_segments=n_seg)  # (units, D, G)
        count = jax.ops.segment_sum(ones, seg, num_segments=n_seg)
        log_unit = logsumexp(total + w[None], axis=(1, 2))
        log_rest = logsumexp(total[seg] - ll + w[None], axis=(1, 2))
        # A unit's only row: p(y_{u,-i}) is the empty product, exactly 1.
        log_rest = jnp.where(count[seg] == 1, 0.0, log_rest)
        return log_unit[seg] - log_rest

    names = ["nu", "sigma", "unit_scale"] + (["unit_nu"] if t_units else [])
    names += ["unit_drift_scale"] if drift else []
    p = {k: jnp.asarray(params[k]) for k in names}
    return jax.lax.map(one, (jnp.asarray(mu), p))


def psis_loo(loglik, block=4000):
    """PSIS-LOO from (draws, rows) log densities: pointwise elpd, k, MCSE.

    Rows are processed in blocks so memory stays bounded at large draw counts."""
    loglik = np.asarray(loglik, float)
    parts = [
        _psis_block(loglik[:, lo : lo + block])
        for lo in range(0, loglik.shape[1], block)
    ]
    return tuple(np.concatenate(p) for p in zip(*parts))


def _psis_block(loglik):
    from arviz_stats.base import array_stats
    from scipy.special import logsumexp

    ll = loglik.T  # (rows, draws)
    # arviz_stats' psislw takes the log-likelihood and negates it internally.
    lw, k = array_stats.psislw(ll, axis=-1)
    lw = np.asarray(lw) - logsumexp(lw, axis=1, keepdims=True)
    elpd = logsumexp(lw + ll, axis=1)
    # Delta-method Monte Carlo error of each log estimate (kept draws are
    # thinned far apart, so relative efficiency is taken as 1).
    w = np.exp(lw)
    ratio = np.exp(ll - elpd[:, None])
    mcse = np.sqrt(np.sum(w * w * (ratio - 1.0) ** 2, axis=1))
    return elpd, np.asarray(k, float), mcse


def chunk_rows(draws: int) -> int:
    """Rows per device batch: bounded so draws x rows x terms stays ~1 GB."""
    return int(min(CHUNK, max(1024, 6_000_000 // draws)))


def unit_chunks(unit_sorted: np.ndarray, size: int = CHUNK):
    """Split positions of a unit-sorted row array into chunks of whole units."""
    starts = np.flatnonzero(np.r_[True, unit_sorted[1:] != unit_sorted[:-1]])
    bounds = np.r_[starts, len(unit_sorted)]
    chunks, lo = [], 0
    for i in range(1, len(bounds)):
        if bounds[i] - lo > size and bounds[i - 1] > lo:
            chunks.append((lo, bounds[i - 1]))
            lo = bounds[i - 1]
        if bounds[i] - lo > size:
            raise ValueError("a unit has more rows than the chunk size")
    chunks.append((lo, len(unit_sorted)))
    return chunks


def score_run(name: str):
    import jax

    jax.config.update("jax_enable_x64", True)
    run_dir, result, kept = explain.load_run(name)
    if result["split"] != "rows":
        raise SystemExit("PSIS-LOO is scored on row-split runs (shared training rows)")
    config = model.MODELS[result["model"]["name"]]
    frame = data.load()
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    heldout = splits.SPLITS[result["split"]](frame)
    frame = data.apply_rules(frame, result.get("data_rules", ()))
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    names = [str(n) for n in feats.names]
    fslope_index = [names.index(n) for n in config.feature_slopes]
    draws = kept["alpha"].shape[0]
    t_units = "unit_nu" in kept and bool((kept["unit_nu"] > 0).all())
    # Designs without unit drift keep a (draws, 1) placeholder.
    drift = "unit_drift" in kept and kept["unit_drift"].shape[1] > 1
    params = {
        k: kept[k]
        for k in ("nu", "sigma", "unit_scale", "unit_nu", "unit_drift_scale")
        if k in kept
    }

    train_idx = np.flatnonzero(~heldout)
    unit_of = pd_index(prep.units, frame.unit_id.to_numpy()[train_idx])
    order = np.argsort(unit_of, kind="stable")
    rows_sorted = train_idx[order]
    units_sorted = unit_of[order]
    loglik = np.empty((draws, len(rows_sorted)))
    size = chunk_rows(draws)
    for lo, hi in unit_chunks(units_sorted, size):
        mask = np.zeros(len(frame), dtype=bool)
        mask[rows_sorted[lo:hi]] = True
        a = model.row_arrays(prep, frame, mask)
        # row_arrays keeps frame order; map it to this chunk's unit order.
        pos = np.argsort(np.argsort(rows_sorted[lo:hi]))
        terms = explain.log_terms(
            kept,
            a,
            feats.groups,
            model.walk_spacing(config),
            config.bedroom_time,
            config.bedroom_slope,
            prep.offset,
            fslope_index,
            unit_line=model.line_index(prep, config),
        )
        mu = sum(v for k, v in terms.items() if k not in UNIT_TERMS) - prep.offset
        mu, y, ut, unit = mu[:, pos], a.y[pos], a.unit_time[pos], a.unit[pos]
        _, seg = np.unique(unit, return_inverse=True)
        n = hi - lo
        pad = size - n
        # Pad to a fixed shape (one compile); padded rows are their own units.
        y_p = np.r_[y, np.zeros(pad)]
        mu_p = np.concatenate([mu, np.zeros((draws, pad))], axis=1)
        seg_p = np.r_[seg, seg.max() + 1 + np.arange(pad)]
        ut_p = np.r_[ut, np.zeros(pad)]
        ll = integrated_loglik(
            y_p, mu_p, seg_p, size, ut_p, params, t_units=t_units, drift=drift
        )
        loglik[:, lo:hi] = np.asarray(ll)[:, :n]

    elpd, k, mcse = psis_loo(loglik)
    audit = frame.audit_id.to_numpy()[rows_sorted]
    # Back to frame order of the training rows.
    back = np.argsort(rows_sorted)
    audit, elpd, k, mcse = audit[back], elpd[back], k[back], mcse[back]
    unit_rows = np.bincount(prep.train.unit, minlength=len(prep.units))
    train_unit = pd_index(prep.units, frame.unit_id.to_numpy()[train_idx])
    held = np.load(run_dir / "heldout.npz", allow_pickle=True)
    thr = k_threshold(draws)
    record = {
        "source_run": name,
        "source_commit": result["commit"],
        "model": result["model"]["name"],
        "feature_set": result["feature_set"],
        "rows": len(elpd),
        "draws": int(draws),
        "integrated": "unit level" + (" and drift" if drift else ""),
        "unit_prior": "student-t" if t_units else "normal",
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
            "note": "mean held-out lpd (repeat-listed units, genuinely left out) vs mean PSIS-LOO over training rows of units with 2+ training rows",
            "heldout_rows": len(held["lpd"]),
            "heldout_mean_lpd": float(np.mean(held["lpd"])),
            "psis_mean_lpd_multi_row_units": float(
                np.mean(elpd[unit_rows[train_unit] >= 2])
            ),
        },
        "fit_seconds": result["seconds"]["fit_total"],
        "hardware_fit": (result.get("remote") or {}).get("gpu_reported")
        or result["hardware"].get("gpu"),
    }
    return record, {"audit_id": audit, "elpd_loo": elpd, "pareto_k": k, "mcse": mcse}


def pd_index(values, keys):
    import pandas as pd

    idx = pd.Index(values).get_indexer(keys)
    if (idx < 0).any():
        raise ValueError("training row outside the fit's units")
    return idx


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    for name in args.runs:
        out_dir = LOO_ROOT / f"{name}-{commit[:7]}"
        if (out_dir / "result.json").exists():
            print(f"skip {name}: {out_dir} exists")
            continue
        t0 = time.perf_counter()
        record, pointwise = score_run(name)
        record.update(
            commit=commit,
            dirty=False,
            seconds=time.perf_counter() - t0,
            hardware=hardware(),
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out_dir / "pointwise.npz", **pointwise)
        (out_dir / "result.json").write_text(json.dumps(record, indent=2))
        k = record["pareto_k"]
        print(
            f"{name}: elpd_loo {record['elpd_loo']:.1f} ± {record['elpd_loo_se']:.1f} "
            f"(mcse {record['elpd_loo_mcse']:.2f}), k>{k['threshold']:.2f}: "
            f"{k['over_threshold']} rows, {record['seconds']:.0f} s",
            flush=True,
        )


if __name__ == "__main__":
    main()
