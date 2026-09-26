"""Per-apartment dollar contributions, fitted rent, residual and uncertainty.

    python -m rentfrontier.explain <run-name> [--rows current|heldout|train|all]

For every kept joint posterior draw, each row's log-scale predictor splits
into named additive terms:

    market       offset + intercept + month trend + calendar season
    <feature group>   sum of x * beta over that group's columns (bedrooms,
                 bathrooms, size, floor, elevator, doorman, laundry, ...)
    bedroom_market_curve   the bedroom group's own market-curve deviation
    building     the building's level
    building_drift   the building's time walk at this month, plus its linear
                     trend (building_trend designs)
    building_bedroom_premium   the building's bedroom slope x (bedrooms - 1)
    building_feature_slopes    the building's own slopes on size and baths
                 (designs with per-building feature slopes)
    unit         the unit's own effect (0 for a unit with no training rows)
    unit_drift   the unit's own linear drift at this date (designs with drift)

The fitted rent is exp(total), the posterior median of asking rent under
the Student-t log-scale noise. Dollar contributions use the logarithmic-
mean (LMDI) decomposition. With R = exp(total) and R0 = exp(market) (a
reference-level apartment in an average building that month),

    dollars_k = term_k * (R - R0) / (log R - log R0),

so the contributions add up exactly to R - R0 in every draw. The output
reports each contribution's posterior mean and 90% interval, the fitted
rent, the asking rent and the residual (asking - fitted). Residuals of rows
in the fit are in-sample review signals, not out-of-sample errors.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from . import data, features, model, splits
from .run import RUNS

FIXED_TERMS = (
    "market",
    "bedroom_market_curve",
    "building",
    "building_drift",
    "building_bedroom_premium",
    "unit",
)


def load_run(name):
    run_dir = RUNS / name
    result = json.loads((run_dir / "result.json").read_text())
    post = np.load(run_dir / "posterior.npz", allow_pickle=True)
    kept = {k[len("kept/") :]: post[k] for k in post.files if k.startswith("kept/")}
    # (chains, blocks, ...) -> (draws, ...)
    kept = {k: v.reshape(-1, *v.shape[2:]).astype(np.float64) for k, v in kept.items()}
    return run_dir, result, kept


def log_terms(
    kept,
    a: model.Arrays,
    feature_groups,
    walk: bool,
    bedroom_time: bool,
    slope: bool,
    offset,
    fslope_index=(),
):
    """Named log-scale terms, each (draws, rows).

    `fslope_index`: feature columns with per-building slopes (kept["fslope"]
    is (draws, buildings, len(fslope_index))).
    """
    d = kept["alpha"].shape[0]
    n = len(a.y)
    terms = {
        "market": offset
        + kept["alpha"][:, None]
        + kept["trend"][:, a.month]
        + kept["season"][:, a.calendar]
    }
    groups = np.asarray(feature_groups)
    for g in dict.fromkeys(feature_groups):
        cols = np.flatnonzero(groups == g)
        terms[g] = kept["beta"][:, cols] @ a.x[:, cols].T
    zeros = np.zeros((d, n))
    terms["bedroom_market_curve"] = (
        kept["bedroom_time"][:, a.bed_group, a.month] if bedroom_time else zeros
    )
    terms["building"] = kept["building"][:, a.building]
    if walk:
        w = kept["walk"]
        terms["building_drift"] = (1 - a.knot_frac) * w[
            :, a.building, a.knot
        ] + a.knot_frac * w[:, a.building, a.knot + 1]
    else:
        terms["building_drift"] = zeros
    if "building_trend" in kept and kept["building_trend"].shape[-1] > 1:
        terms["building_drift"] = terms["building_drift"] + model.building_trend_term(
            kept, a
        )
    terms["building_bedroom_premium"] = (
        kept["bedroom_slope"][:, a.building] * a.beds_centered if slope else zeros
    )
    if len(fslope_index):
        terms["building_feature_slopes"] = np.einsum(
            "dnk,nk->dn",
            kept["fslope"][:, a.building],
            a.x[:, np.asarray(fslope_index)],
        )
    seen = a.unit >= 0
    terms["unit"] = np.where(seen[None], kept["unit"][:, np.maximum(a.unit, 0)], 0.0)
    drift = kept.get("unit_drift")
    if drift is not None and drift.shape[1] > 1:
        terms["unit_drift"] = np.where(
            seen[None], drift[:, np.maximum(a.unit, 0)] * a.unit_time, 0.0
        )
    return terms


def decompose(terms):
    """LMDI dollar contributions; returns dict of (draws, rows) arrays."""
    total = sum(terms.values())
    base = terms["market"]
    fitted, reference = np.exp(total), np.exp(base)
    diff = total - base
    weight = np.where(
        np.abs(diff) > 1e-12,
        (fitted - reference) / np.where(diff == 0, 1, diff),
        fitted,
    )
    dollars = {k: v * weight for k, v in terms.items() if k != "market"}
    dollars["market"] = reference
    check = reference + sum(v for k, v in dollars.items() if k != "market")
    if not np.allclose(check, fitted, rtol=1e-9):
        raise AssertionError("LMDI contributions do not add up")
    return dollars, fitted


def explain(name, rows="current"):
    run_dir, result, kept = load_run(name)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load()
    heldout = splits.SPLITS[result["split"]](frame)
    feats = features.build(result["feature_set"], frame, ~heldout)
    prep = model.prepare(frame, heldout, feats)
    select = {
        "current": frame.price_basis.ne(
            "historical_initial_own_advertisement_ask"
        ).to_numpy(),
        "heldout": heldout,
        "train": ~heldout,
        "all": np.ones(len(frame), dtype=bool),
    }[rows]
    out = []
    for chunk in np.array_split(np.flatnonzero(select), max(1, select.sum() // 4000)):
        mask = np.zeros(len(frame), dtype=bool)
        mask[chunk] = True
        a = model.row_arrays(prep, frame, mask)
        terms = log_terms(
            kept,
            a,
            feats.groups,
            config.building_walk,
            config.bedroom_time,
            config.bedroom_slope,
            prep.offset,
            [feats.names.index(n) for n in config.feature_slopes],
        )
        dollars, fitted = decompose(terms)
        sub = frame.loc[
            mask,
            [
                "audit_id",
                "unit_id",
                "building",
                "canonical_unit_url",
                "period",
                "bedrooms",
                "asking_rent",
            ],
        ].copy()
        sub["in_fit"] = ~heldout[mask]
        sub["fitted_rent"] = fitted.mean(0)
        sub["fitted_rent_p05"], sub["fitted_rent_p95"] = np.percentile(
            fitted, [5, 95], axis=0
        )
        resid = sub.asking_rent.to_numpy()[None] - fitted
        sub["residual"] = resid.mean(0)
        sub["residual_p05"], sub["residual_p95"] = np.percentile(resid, [5, 95], axis=0)
        for k, v in dollars.items():
            sub[f"{k}_usd"] = v.mean(0)
            sub[f"{k}_usd_p05"], sub[f"{k}_usd_p95"] = np.percentile(v, [5, 95], axis=0)
        out.append(sub)
    table = pd.concat(out)
    path = run_dir / f"contributions-{rows}.csv"
    table.to_csv(path, index=False)
    return table, path


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run")
    parser.add_argument(
        "--rows", choices=("current", "heldout", "train", "all"), default="current"
    )
    args = parser.parse_args()
    table, path = explain(args.run, args.rows)
    cols = [c for c in table.columns if c.endswith("_usd")]
    print(f"wrote {path} ({len(table)} rows)")
    print(
        table[["canonical_unit_url", "asking_rent", "fitted_rent", "residual", *cols]]
        .head(5)
        .T.to_string()
    )


if __name__ == "__main__":
    main()
