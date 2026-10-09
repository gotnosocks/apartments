"""A prediction kit for a recorded run: what the listings site needs to score
an apartment that is not in the data, without numpy or JAX.

    uv run --extra gpu python -m rentfrontier.kit <run-name> --summary <bundle>

The site scores a new apartment as `summary` scores a held-out row of a unit
the fit never saw: the run's terms (`explain.log_terms`) at the last month, a
unit level from the unit prior (`summary.new_unit_levels`) and Student-t noise.
The kit holds those terms per kept draw (thinned), split into the parts a form
can vary:

    log ask = market + season(date) + beta . x + bedroom_time[group] + level[b]
              + bedroom_slope[b] * beds_centered + fslope[b] . x[slopes]
              + unit level + noise

kit.json            per draw: market (offset, intercept and trend at the last
                    month, without the season), the season (the daily
                    Fourier coefficients, `model.day_basis` at the date's
                    fraction of the year, or twelve monthly values), beta,
                    bedroom_time at the last month per bedroom group, sigma
                    (per bedroom group, or one), nu, unit_scale, unit_nu; the
                    feature names, groups and slope columns; the period, the
                    summary bundle it goes with and provenance.
buildings.parquet   per building, a list over draws of: level (the building
                    effect plus its walk and trend at the last month),
                    bedroom_slope, and fslope (a list per draw).
units.parquet       per unit with training rows, a list over draws of its
                    level (the fit's own unit draws, thinned as the rest):
                    an apartment the fit has seen is scored with these in
                    place of the unit prior.
complete.json       provenance and the sha256 of each file; written last.

The kit does not encode x. The site copies a building's own columns from its
newest row in the summary bundle (`inputs`), encodes the apartment's columns
from its form, and recovers the training median of log square feet per
bedroom count from the bundle's rows (log square feet less the row's
`log_sqft_vs_bedroom_median`); each build checks its encoder against the
bundle's inputs.

Writes /data1/apartments/frontier/kits/<run>-<commit>/. Refuses designs the
formula above does not cover (line effects, unit drift) and a run that fails
the convergence gate, as `summary` does.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, explain, features, model, splits, summary
from .run import git

KITS = data.OUTPUT_ROOT / "kits"
VERSION = "frontier-kit-v1"
DRAWS = 250


def thin(n: int, keep: int = DRAWS) -> np.ndarray:
    """Evenly spaced draw indices, at most `keep` of them."""
    return np.unique(np.linspace(0, n - 1, min(n, keep)).round().astype(int))


def last_month_rows(prep, n_features: int) -> model.Arrays:
    """One reference row per building at the last month: no features, a
    one-bedroom (no bedroom curve or premium), a unit without training rows,
    at the middle of the month."""
    n = len(prep.buildings)
    month = len(prep.periods) - 1
    calendar = prep.periods[-1].month - 1
    full = lambda v, dtype=np.int32: np.full(n, v, dtype=dtype)
    return model.Arrays(
        y=np.zeros(n),
        x=np.zeros((n, n_features)),
        month=full(month),
        calendar=full(calendar),
        building=np.arange(n, dtype=np.int32),
        unit=full(-1),
        knot=full(month // model.KNOT_MONTHS),
        knot_frac=full((month % model.KNOT_MONTHS) / model.KNOT_MONTHS, float),
        bed_group=full(0),
        beds_centered=full(0.0, float),
        unit_time=full(0.0, float),
        year_frac=full((calendar + 0.5) / 12, float),
        year=full(prep.periods[-1].year - prep.periods[0].year),
    )


def kit_tables(kept, prep, config, feats, keep: int = DRAWS):
    """(per-draw record, per-building frame) for the kept draws."""
    if np.any(kept.get("line_scale", 0) > 0):
        raise SystemExit("line-effects designs are not supported")
    if "unit_drift" in kept and kept["unit_drift"].shape[1] > 1:
        raise SystemExit("unit-drift designs are not supported")
    idx = thin(kept["alpha"].shape[0], keep)
    kept = {k: np.asarray(v)[idx] for k, v in kept.items() if np.ndim(v)}
    d = len(idx)
    a = last_month_rows(prep, len(feats.names))
    # walk_term reads knot + 1, one past the last knot when the last month is
    # a knot (its weight is then 0): repeat the last knot so numpy can index it.
    padded = dict(kept)
    if "walk" in kept:
        padded["walk"] = np.concatenate([kept["walk"], kept["walk"][..., -1:]], axis=-1)
    terms = explain.log_terms(
        padded,
        a,
        feats.groups,
        model.walk_spacing(config),
        False,
        False,
        prep.offset,
    )
    for g in dict.fromkeys(feats.groups):
        if np.any(terms[g]):
            raise AssertionError("reference rows must have no feature terms")
    month = len(prep.periods) - 1
    market = prep.offset + kept["alpha"] + kept["trend"][:, month]
    daily = kept.get("season_daily_coef", np.zeros((1, 1))).shape[-1] > 1
    season = kept["season_daily_coef"] if daily else kept["season"]
    mid = (
        season @ model.day_basis(a.year_frac[:1], season.shape[1] // 2).T
        if daily
        else season[:, a.calendar[:1]]
    )[:, 0]
    if not np.allclose(market + mid, terms["market"][:, 0], rtol=0, atol=1e-12):
        raise AssertionError("market and season do not add up to log_terms' market")
    level = terms["building"] + terms["building_drift"]  # (draws, buildings)
    groups = len(model.BEDROOM_GROUPS)
    bedroom_time = (
        kept["bedroom_time"][:, :, month]
        if config.bedroom_time
        else np.zeros((d, groups))
    )
    slope = (
        kept["bedroom_slope"] if config.bedroom_slope else np.zeros((d, level.shape[1]))
    )
    fslope_names = list(config.feature_slopes)
    fslope = kept["fslope"] if fslope_names else np.zeros((d, level.shape[1], 0))
    sigma = kept["sigma"] if kept["sigma"].ndim == 2 else kept["sigma"][:, None]
    if getattr(config, "noise_loglinear", False):
        # By bedroom group and noise cell (group-major): the kit prices a new
        # unit, so it keeps the single-listing cell (floor known, an
        # established building).
        sigma = sigma.reshape(d, len(model.BEDROOM_GROUPS), -1)[:, :, 1]
    elif sigma.shape[1] > len(model.BEDROOM_GROUPS):
        # By bedroom group and year (group-major): the kit prices the last
        # period, so it keeps that year's scales.
        sigma = sigma.reshape(d, len(model.BEDROOM_GROUPS), -1)[:, :, -1]
    t_units = bool((kept.get("unit_nu", np.zeros(d)) > 0).all())
    record = {
        "period": prep.periods[-1].strftime("%Y-%m-%d"),
        "draws": d,
        "features": list(feats.names),
        "groups": list(feats.groups),
        "slopes": fslope_names,
        "bedroom_groups": [str(g) for g in model.BEDROOM_GROUPS],
        # As `model.row_arrays`: bedroom_time and sigma by group, the
        # building's bedroom slope by centred bedrooms.
        "bedroom_rule": {
            "group": "min(max(round(bedrooms), 0), 3)",
            "centered": "min(max(round(bedrooms), 0), 4) - 1",
        },
        "t_units": t_units,
        "market": market.tolist(),
        "season": {"daily": bool(daily), "coef": season.tolist()},
        "beta": kept["beta"].tolist(),
        "bedroom_time": bedroom_time.tolist(),
        "sigma": sigma.tolist(),
        "nu": kept["nu"].tolist(),
        "unit_scale": kept["unit_scale"].tolist(),
        "unit_nu": (kept["unit_nu"] if t_units else np.zeros(d)).tolist(),
    }
    buildings = pd.DataFrame(
        {
            "building": list(prep.buildings),
            "level": list(level.T),
            "bedroom_slope": list(slope.T),
            "fslope": [fslope[:, b, :] for b in range(level.shape[1])],
        }
    )
    buildings["fslope"] = buildings.fslope.map(lambda m: [list(r) for r in m])
    return record, buildings


def unit_table(kept, prep, keep: int = DRAWS) -> pd.DataFrame:
    """Per fitted unit, its level over the kept draws (thinned as `kit_tables`),
    in float32: the posterior unit effect a relisted apartment carries."""
    idx = thin(np.asarray(kept["alpha"]).shape[0], keep)
    if "unit" not in kept or not len(prep.units):
        return pd.DataFrame({"unit": pd.Series(dtype=str), "level": []})
    level = np.asarray(kept["unit"])[idx].astype(np.float32)  # (draws, units)
    return pd.DataFrame({"unit": list(prep.units), "level": list(level.T)})


def build_kit(name: str, summary_dir: Path, allow_failing: bool = False):
    import jax

    jax.config.update("jax_enable_x64", True)
    bundle = json.loads((summary_dir / "complete.json").read_text())
    if bundle.get("run") != name:
        raise SystemExit(f"{summary_dir} summarizes {bundle.get('run')}, not {name}")
    run_dir, result, kept = explain.load_run(name)
    gate_status = summary.gate(result, run_dir)
    if not gate_status["passes"] and not allow_failing:
        raise SystemExit(f"{name} fails the convergence gate: {gate_status}")
    summary.check_run(result)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load(Path(result["dataset"]))
    heldout = splits.SPLITS[result["split"]](frame)
    frame, heldout = data.apply_rules(frame, heldout, data.recorded_rules(result))
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    post = np.load(run_dir / "posterior.npz", allow_pickle=True)
    summary.verify_run(
        result, frame, heldout, prep, run_dir, post["units"], post["buildings"]
    )
    record, buildings = kit_tables(kept, prep, config, feats)
    units = unit_table(kept, prep)
    record |= {
        "run": result["name"],
        "run_commit": result["commit"],
        "model": result["model"],
        "feature_set": result["feature_set"],
        "gate": gate_status,
        "summary": str(summary_dir),
        "summary_sha256": data.sha256(summary_dir / "complete.json"),
    }
    return record, buildings, units


def write(record, buildings, units, out_dir: Path, commit: str) -> Path:
    tmp = out_dir.with_name(out_dir.name + ".tmp")
    tmp.mkdir(parents=True, exist_ok=False)
    (tmp / "kit.json").write_text(json.dumps(record, separators=(",", ":")))
    buildings.to_parquet(tmp / "buildings.parquet", index=False)
    units.to_parquet(tmp / "units.parquet", index=False)
    complete = {
        "version": VERSION,
        "run": record["run"],
        "commit": commit,
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "period": record["period"],
        "summary_sha256": record["summary_sha256"],
        "draws": record["draws"],
        "files": {p.name: data.sha256(p) for p in sorted(tmp.iterdir()) if p.is_file()},
    }
    (tmp / "complete.json").write_text(json.dumps(complete, indent=2))
    tmp.rename(out_dir)
    return out_dir


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run")
    parser.add_argument(
        "--summary", type=Path, required=True, help="the run's summary bundle"
    )
    parser.add_argument("--allow-failing", action="store_true")
    args = parser.parse_args(argv)
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    out_dir = KITS / f"{args.run}-{commit[:7]}"
    if (out_dir / "complete.json").exists():
        raise SystemExit(f"{out_dir} exists")
    record, buildings, units = build_kit(args.run, args.summary, args.allow_failing)
    path = write(record, buildings, units, out_dir, commit)
    print(
        f"wrote {path}: {len(buildings)} buildings, {len(units)} units, "
        f"{record['draws']} draws"
    )


if __name__ == "__main__":
    main()
