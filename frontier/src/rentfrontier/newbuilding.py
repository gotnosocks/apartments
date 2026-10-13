"""How well a fit prices an apartment in a building it has never seen.

    python -m rentfrontier.newbuilding <run-name> [<run-name> ...]

No refit. For every training row, the ask is predicted as if the row's
building (or only its unit) had no rows in the fit, from the run's kept draws:

    new building   the building terms (level, half-year walk, bedroom
                   premium, feature slopes, trend) and the unit terms (unit
                   effect, drift, line) are redrawn from their population
                   distributions under each draw's own scales; the walk
                   starts at 0 at the building's first half-year with
                   training rows and steps from there
    new unit       only the unit terms are redrawn, in the fitted building

Market, time, the feature coefficients (with the neighbourhood curves) and
the noise stay as fitted. Each row's predictive is the mixture over draws of
the Student-t noise around that draw's redrawn mean. Rows of the same
building were in the fit, so the population scales saw them: a slight
optimism the grouped-building holdout refit measures.

Reported per rung, overall, by size stated or unknown, and by the
building's training-row count: the median absolute % miss of the
predictive median against the ask, and the shares of asks inside the
central 80% and 95% predictive intervals.

Writes /data1/apartments/frontier/newbuilding/<run>-<commit>/result.json.
Refuses a dirty tree.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import stdtr

from . import data, explain, features, model, summary
from .run import git, hardware

NEWBUILDING_ROOT = data.OUTPUT_ROOT / "newbuilding"
SEED = 20261013
BUILDING_TERMS = (
    "building",
    "building_drift",
    "building_bedroom_premium",
    "building_feature_slopes",
)
UNIT_TERMS = ("unit", "unit_drift", "line")
RUNGS = ("new building", "new unit")
# The "new unit" rung keeps the building terms the fit learned from the row's
# own asks, so it is in-sample for the building; the out-of-sample new-unit
# figure is the row split's held-out rows (`summary.new_unit_coverage`).
IN_SAMPLE = {"new unit": "in-sample: building terms fitted with the row's own asks"}
# The building's training rows, as (label, low, high) inclusive.
BUILDING_ROWS = (
    ("1-5", 1, 5),
    ("6-20", 6, 20),
    ("21-100", 21, 100),
    ("101+", 101, None),
)


def _scale(kept, name):
    v = kept.get(name)
    return np.zeros(kept["alpha"].shape[0]) if v is None else np.asarray(v)


def building_variance(kept, a, walk_origin, fslope_x, trend_center, spacing):
    """(draws, rows) prior variance of a new building's terms at each row: the
    level, a walk that is 0 at knot `walk_origin` (the panel's first knot, as in
    `model._walk`, or the building's first knot for anchored walks), the bedroom
    premium, the feature slopes and the trend, all independent Normals."""
    var = _scale(kept, "building_scale")[:, None] ** 2 + 0.0 * a.y[None]
    if spacing:
        knot, frac = model.walk_position(a, spacing)
        steps = np.maximum(knot - walk_origin, 0) + frac**2
        var = var + _scale(kept, "walk_scale")[:, None] ** 2 * steps[None]
    var = var + _scale(kept, "bedroom_slope_scale")[:, None] ** 2 * (
        a.beds_centered[None] ** 2
    )
    if fslope_x.shape[1]:
        var = var + (kept["fslope_scales"] ** 2) @ (fslope_x**2).T
    if "building_trend_scale" in kept:
        years = (a.month - trend_center) / 12.0
        var = var + kept["building_trend_scale"][:, None] ** 2 * years[None] ** 2
    return var


def walk_origin(config, first_knot):
    """The knot where a new building's walk is 0. `model._walk` pins every
    walk at the panel's first knot; with `walk_anchor_data` it pins it at the
    building's most-weighted knot, which for a new building is taken as its
    first. Student-t and sum-to-zero walks are not handled."""
    if config.walk_t or config.walk_zero_sum:
        raise ValueError("new-building score: Normal walks only")
    if config.walk_anchor_data:
        return first_knot
    return np.zeros_like(first_knot)


def unit_draws(kept, a, has_line, rng):
    """(draws, rows) unit terms of a new apartment: the unit effect (Student-t,
    clipped as `summary.new_unit_levels`), drift and line."""
    d, n = kept["alpha"].shape[0], len(a.y)
    nu = kept.get("unit_nu")
    if nu is not None and (nu > 0).all():
        z = rng.standard_t(np.maximum(nu, 1e-3)[:, None], (d, n))
    else:
        z = rng.standard_normal((d, n))
    out = _scale(kept, "unit_scale")[:, None] * np.clip(
        z, -summary.UNIT_CLIP, summary.UNIT_CLIP
    )
    drift = kept.get("unit_drift")
    if drift is not None and drift.shape[1] > 1:
        out = (
            out
            + kept["unit_drift_scale"][:, None]
            * rng.standard_normal((d, n))
            * a.unit_time[None]
        )
    line = _scale(kept, "line_scale")
    if np.any(line > 0):
        out = out + line[:, None] * rng.standard_normal((d, n)) * has_line[None]
    return out


def scores(y, mean, sd_extra, sigma, nu, rng):
    """Per row: the predictive median and the PIT of y, for the mixture over
    draws of Student-t(nu) noise of scale `sigma` around `mean` plus a
    Normal(0, sd_extra) draw (sd_extra None: none). (draws, rows) arrays; y
    (rows,); nu (draws,)."""
    total = mean
    if sd_extra is not None:
        total = mean + sd_extra * rng.standard_normal(mean.shape)
    d = total.shape[0]
    weights = np.full(total.shape, 1.0 / d)
    median = summary.predictive_quantiles(total, sigma, nu, weights, (0.5,))[0]
    pit = stdtr(nu[:, None], (y[None] - total) / sigma).mean(axis=0)
    return median, pit


def summarize_rows(y, median, pit, groups):
    """{group: {rows, median_abs_pct_miss, cover_80, cover_95}} for boolean masks."""
    miss = np.abs(np.exp(median - y) - 1.0)
    out = {}
    for g, m in groups.items():
        if not m.any():
            continue
        p = pit[m]
        out[g] = {
            "rows": int(m.sum()),
            "median_abs_pct_miss": float(100 * np.median(miss[m])),
            "cover_80": float(np.mean((p > 0.10) & (p < 0.90))),
            "cover_95": float(np.mean((p > 0.025) & (p < 0.975))),
        }
    return out


def _load(name: str, rules=None):
    """(run_dir, result, kept, config, frame, heldout) for a run,
    rebuilt under its recorded rules (or `rules`)."""
    run_dir, result, kept = explain.load_run(name)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load(Path(result["dataset"]))
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    recorded = data.recorded_rules(result)
    frame, heldout = data.split_and_rules(
        frame, result["split"], recorded if rules is None else rules
    )
    return run_dir, result, kept, config, frame, heldout


def _check_draws(run_dir, prep):
    post = np.load(run_dir / "posterior.npz", allow_pickle=True)
    if not (
        np.array_equal(prep.units, post["units"])
        and np.array_equal(prep.buildings, post["buildings"])
    ):
        raise SystemExit("units or buildings differ from the run's saved draws")


def _first_rows(a, spacing, n_b):
    """Each building's first walk knot, row count and mean month over rows `a`."""
    knot, _ = model.walk_position(a, spacing) if spacing else (a.month, 0)
    first_knot = np.full(n_b, np.iinfo(np.int64).max)
    np.minimum.at(first_knot, a.building, np.asarray(knot, np.int64))
    rows = np.bincount(a.building, minlength=n_b)
    center = np.bincount(a.building, weights=a.month, minlength=n_b) / np.maximum(
        rows, 1
    )
    return first_knot, rows, center


def _score_chunk(kept, config, prep, a, building, rungs, ctx, rng):
    """{rung: (median, pit)} for rows `a`; `building` indexes `ctx`'s per-building
    first knot and mean month (the fit's own index for a seen building)."""
    terms = explain.log_terms(
        kept,
        a,
        prep.features.groups,
        ctx["spacing"],
        config.bedroom_time,
        config.bedroom_slope,
        prep.offset,
        ctx["fslope_index"],
        unit_line=prep.unit_line,
    )
    total = sum(terms.values()) - prep.offset
    b_part = sum(terms[k] for k in BUILDING_TERMS if k in terms)
    u_part = sum(terms[k] for k in UNIT_TERMS if k in terms)
    sigma_all = kept["sigma"]
    sigma = (
        sigma_all[:, model.noise_group(sigma_all.shape[1], a)]
        if sigma_all.ndim == 2
        else sigma_all[:, None]
    )
    has_line = (
        (np.asarray(prep.unit_line)[np.maximum(a.unit, 0)] >= 0) & (a.unit >= 0)
        if prep.unit_line is not None
        else np.zeros(len(a.y), bool)
    )
    units = unit_draws(kept, a, has_line, rng)
    rest = total - b_part - u_part
    out = {}
    for rung in rungs:
        if rung == "new building":
            b_var = building_variance(
                kept,
                a,
                walk_origin(config, ctx["first_knot"][building]),
                a.x[:, ctx["fslope_index"]],
                ctx["center"][building],
                ctx["spacing"],
            )
            out[rung] = scores(
                a.y, rest + units, np.sqrt(b_var), sigma, kept["nu"], rng
            )
        elif rung == "new unit":
            out[rung] = scores(a.y, rest + b_part + units, None, sigma, kept["nu"], rng)
        else:  # "held out": the fit as is, a new unit's terms drawn
            mean = total + np.where(a.unit[None] < 0, units, 0.0)
            out[rung] = scores(a.y, mean, None, sigma, kept["nu"], rng)
    return out


def _groups(names, x, b_count):
    """The reported row groups: all, size stated or unknown, building rows."""
    groups = {"all": np.ones(len(b_count), bool)}
    if "sqft_unknown" in names:
        unknown = x[:, names.index("sqft_unknown")] > 0.5
        groups |= {"size stated": ~unknown, "size unknown": unknown}
    for label, lo, hi in BUILDING_ROWS:
        groups[f"building rows {label}"] = (b_count >= lo) & (
            b_count <= (hi if hi is not None else b_count.max())
        )
    return groups


# What a forked worker reads: set by `_score` before its pool starts, so the
# draws and the frame are shared with the workers rather than pickled.
_JOB: dict = {}


def _chunk_job(i):
    """Chunk i of `_JOB`: ({rung: (median, pit)}, y, x, building row counts).
    Its random stream is seeded by (seed, i), so a score doesn't depend on how
    many workers ran it."""
    j = _JOB
    m = np.zeros(len(j["frame"]), dtype=bool)
    m[j["chunks"][i]] = True
    a, building = j["building_of"](m)
    out = _score_chunk(
        j["kept"],
        j["config"],
        j["prep"],
        a,
        building,
        j["rungs"],
        j["ctx"],
        np.random.default_rng([j["seed"], i]),
    )
    return out, a.y, a.x, j["ctx"]["rows"][building]


def _score(kept, config, prep, frame, mask, rungs, ctx, building_of, seed, workers=1):
    """Score rows `mask` of `frame` in chunks, on `workers` forked processes;
    returns (per-rung summaries, rows). `building_of(a)` maps a chunk's rows to
    `ctx`'s building index and sets the index the draws are read at."""
    parts = {r: {"median": [], "pit": [], "y": []} for r in rungs}
    xs, counts = [], []
    idx = np.flatnonzero(mask)
    chunk = summary.chunk_rows(kept["alpha"].shape[0])
    chunks = np.array_split(idx, max(1, len(idx) // chunk))
    _JOB.update(
        kept=kept,
        config=config,
        prep=prep,
        frame=frame,
        rungs=rungs,
        ctx=ctx,
        building_of=building_of,
        seed=seed,
        chunks=chunks,
    )
    try:
        if workers > 1:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(
                workers, mp_context=multiprocessing.get_context("fork")
            ) as pool:
                results = list(pool.map(_chunk_job, range(len(chunks))))
        else:
            results = [_chunk_job(i) for i in range(len(chunks))]
    finally:
        _JOB.clear()
    for out, y, x, count in results:
        for rung, (median, pit) in out.items():
            parts[rung]["median"].append(median)
            parts[rung]["pit"].append(pit)
            parts[rung]["y"].append(y)
        xs.append(x)
        counts.append(count)
    groups = _groups(
        [str(n) for n in prep.features.names],
        np.concatenate(xs),
        np.concatenate(counts),
    )
    out = {}
    for rung in rungs:
        p = {k: np.concatenate(v) for k, v in parts[rung].items()}
        out[rung] = summarize_rows(p["y"], p["median"], p["pit"], groups)
    return out, len(idx)


def score_run(name: str, only=None, workers=1):
    """Both rungs on the run's training rows (`only`: just the training rows of
    these buildings)."""
    run_dir, result, kept, config, frame, heldout = _load(name)
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    _check_draws(run_dir, prep)
    names = [str(n) for n in feats.names]
    spacing = model.walk_spacing(config)
    first_knot, b_rows, center = _first_rows(prep.train, spacing, len(prep.buildings))
    ctx = {
        "spacing": spacing,
        "fslope_index": np.asarray(
            [names.index(n) for n in config.feature_slopes], int
        ),
        "first_knot": first_knot,
        "center": center,
        "rows": b_rows,
    }
    mask = ~heldout
    if only is not None:
        mask &= frame.building.isin(only).to_numpy()

    def seen(m):
        a = model.row_arrays(prep, frame, m)
        return a, a.building

    out, rows = _score(kept, config, prep, frame, mask, RUNGS, ctx, seen, SEED, workers)
    return _record(name, result, kept, rows, out, METHOD)


METHOD = (
    "training rows, building (new building) or unit (new unit) terms redrawn "
    "from their population distributions per kept draw; walk from 0 at "
    "walk_origin (the panel's first knot unless anchored); the new-unit rung is "
    "in-sample for the building terms; predictive median and PIT of the "
    "mixture of Student-t noise over draws; each row chunk draws from its own "
    "generator, seeded by (SEED, chunk index)"
)


def _record(name, result, kept, rows, out, method):
    return {
        "source_run": name,
        "source_commit": result["commit"],
        "model": result["model"]["name"],
        "feature_set": result["feature_set"],
        "data_rules": list(result.get("data_rules", ())),
        "rows": int(rows),
        "draws": int(kept["alpha"].shape[0]),
        "rungs": out,
        "in_sample": {r: IN_SAMPLE[r] for r in out if r in IN_SAMPLE},
        "method": method,
    }


def score_holdout(name: str, workers=1):
    """The new-building rung on the held-out lots of a fit with a
    `data.HOLDOUT_PREFIX` rule: the rows of those buildings that the same
    split without that rule trains on (step 1's rows for them), scored with the
    fit's population draws. The fit never saw these buildings."""
    run_dir, result, kept, config, frame, heldout = _load(name)
    rules = data.recorded_rules(result)
    holdout = [r for r in rules if r.startswith(data.HOLDOUT_PREFIX)]
    if len(holdout) != 1:
        raise SystemExit(f"{name} has no single held-out-lots rule: {rules}")
    lots = data.holdout_buildings(data.RULE_SOURCES[holdout[0]])
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    _check_draws(run_dir, prep)

    # The same rows with the held-out buildings back, trained on as before.
    full, full_held = data.split_and_rules(
        data.load(Path(result["dataset"])),
        result["split"],
        tuple(r for r in rules if r != holdout[0]),
    )
    lot_rows = full.building.isin(lots).to_numpy()
    train = ~full_held & ~lot_rows
    full_feats = features.build(result["feature_set"], full, train)
    keyed = pd.Series(np.arange(len(full)), index=full.audit_id.to_numpy())
    same = keyed.loc[frame.audit_id.to_numpy()].to_numpy()
    if not (
        list(full_feats.names) == list(feats.names)
        and np.allclose(full_feats.values[same][~heldout], feats.values[~heldout])
    ):
        raise SystemExit("features differ with the held-out buildings back")
    target = lot_rows & ~full_held
    new = np.sort(full.building[target].unique())
    wide = dataclasses.replace(
        prep,
        features=full_feats,
        buildings=np.concatenate([prep.buildings, new]),
    )
    if prep.building_rows is not None:  # the noise cells: unseen, so no rows
        wide.building_rows = np.concatenate(
            [prep.building_rows, np.zeros(len(new), int)]
        )
        first_year = full[target].period.dt.year.groupby(full.building[target]).min()
        wide.building_first_year = np.concatenate(
            [prep.building_first_year, first_year.reindex(new).to_numpy()]
        )
    names = [str(n) for n in feats.names]
    spacing = model.walk_spacing(config)
    a_all = model.row_arrays(wide, full, target)
    first_knot, b_rows, center = _first_rows(
        a_all, spacing, len(prep.buildings) + len(new)
    )
    ctx = {
        "spacing": spacing,
        "fslope_index": np.asarray(
            [names.index(n) for n in config.feature_slopes], int
        ),
        "first_knot": first_knot,
        "center": center,
        "rows": b_rows,
    }

    def unseen(m):
        a = model.row_arrays(wide, full, m)
        building = a.building
        a.building = np.zeros_like(building)  # any seen building: its terms drop out
        return a, building

    out, rows = _score(
        kept,
        config,
        wide,
        full,
        target,
        ("new building",),
        ctx,
        unseen,
        SEED,
        workers,
    )
    record = _record(name, result, kept, rows, out, METHOD_HOLDOUT)
    record["holdout_rule"] = holdout[0]
    record["holdout_buildings"] = len(new)
    return record


METHOD_HOLDOUT = (
    "rows of the held-out lots' buildings that the split trains on without the "
    "held-out-lots rule, from a fit that never saw them; building and unit terms "
    "drawn from their population distributions per kept draw; walk from 0 at "
    "walk_origin (the panel's first knot unless anchored); predictive median "
    "and PIT of the "
    "mixture of Student-t noise over draws; each row chunk draws from its own "
    "generator, seeded by (SEED, chunk index)"
)


def draw_lots(buildings, lots, fraction=0.10, seed=SEED) -> pd.DataFrame:
    """About `fraction` of the tax lots of `buildings` (with `lots` mapping a
    building to its lot), every building of each, as (lot, building) rows:
    buildings sharing a lot (towers of one complex) go out together."""
    lot = lots.reindex(np.sort(np.unique(buildings))).astype(str)
    unique = np.sort(lot.unique())
    chosen = np.random.default_rng(seed).choice(
        unique, size=round(fraction * len(unique)), replace=False
    )
    out = lot[lot.isin(set(chosen))]
    return pd.DataFrame({"lot": out.to_numpy(), "building": out.index}).sort_values(
        ["lot", "building"], ignore_index=True
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("runs", nargs="*")
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="score each run's held-out lots (a fit with a held-out-lots rule)",
    )
    parser.add_argument(
        "--only",
        help="a held-out-lots file: score only the training rows of its buildings",
    )
    parser.add_argument(
        "--draw-lots",
        metavar="DATASET",
        help="print a held-out-lots file for DATASET's buildings (NB8 registry)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="score row chunks on this many forked processes (each holds a chunk's "
        "draws-by-rows arrays; the draws and frame are shared)",
    )
    args = parser.parse_args(argv)
    if args.draw_lots:
        frame = data.load(Path(args.draw_lots))
        lots = pd.read_parquet(features.NB8_REGISTRY_FILE).set_index("building").bbl
        out = draw_lots(frame.building.to_numpy(), lots)
        print(
            f"# Held-out lots: {len(out)} buildings on {out.lot.nunique()} tax lots "
            f"(10% of lots, seed {SEED}),\n# drawn by rentfrontier.newbuilding "
            f"--draw-lots from {Path(args.draw_lots).name}.\n# lot\tbuilding"
        )
        for r in out.itertuples():
            print(f"{r.lot}\t{r.building}")
        return
    only = data.holdout_buildings(args.only) if args.only else None
    tag = (
        "holdout" if args.holdout else ("only-" + Path(args.only).stem if only else "")
    )
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    for name in args.runs:
        out_dir = NEWBUILDING_ROOT / "-".join(filter(None, (name, tag, commit[:7])))
        if (out_dir / "result.json").exists():
            print(f"skip {name}: {out_dir} exists")
            continue
        t0 = time.perf_counter()
        record = (
            score_holdout(name, args.workers)
            if args.holdout
            else score_run(name, only, args.workers)
        )
        record["workers"] = args.workers
        record.update(
            commit=commit,
            dirty=False,
            seconds=time.perf_counter() - t0,
            hardware=hardware(),
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(record, indent=2))
        for rung, r in record["rungs"].items():
            a = r["all"]
            print(
                f"{name}: {rung}{' (in-sample)' if rung in IN_SAMPLE else ''}: "
                f"miss {a['median_abs_pct_miss']:.1f}%, "
                f"80% {100 * a['cover_80']:.1f}, 95% {100 * a['cover_95']:.1f}"
                f" ({record['seconds']:.0f} s)",
                flush=True,
            )


if __name__ == "__main__":
    main()
