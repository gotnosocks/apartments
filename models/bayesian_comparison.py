"""Paired validation comparisons with resampling of whole buildings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


KEYS = ["unit_id", "period"]


def weighted_medians(values, weights):
    order = np.argsort(values)
    cumulative = np.cumsum(weights[:, order], axis=1)
    total = cumulative[:, -1]
    left = np.argmax(cumulative > ((total - 1) // 2)[:, None], axis=1)
    right = np.argmax(cumulative > (total // 2)[:, None], axis=1)
    ordered = values[order]
    return (ordered[left] + ordered[right]) / 2


def compare(candidate, reference, *, draws=2000, seed=81274):
    columns = KEYS + [
        "building",
        "asking_rent",
        "predicted_rent",
        "log_predictive_density",
    ]
    joined = candidate[columns].merge(
        reference[columns],
        on=KEYS,
        validate="one_to_one",
        how="outer",
        suffixes=("_candidate", "_reference"),
        indicator=True,
    )
    if not joined["_merge"].eq("both").all():
        raise ValueError("Comparisons require exactly the same validation observations")
    if not (
        joined.building_candidate.eq(joined.building_reference).all()
        and joined.asking_rent_candidate.eq(joined.asking_rent_reference).all()
    ):
        raise ValueError("Building and observed rent must agree in a paired comparison")
    for column in [
        "predicted_rent_candidate",
        "predicted_rent_reference",
        "log_predictive_density_candidate",
        "log_predictive_density_reference",
    ]:
        if not np.isfinite(joined[column]).all():
            raise ValueError("Comparison scores must be finite")
    building, levels = pd.factorize(joined.building_candidate, sort=True)
    groups = len(levels)
    rng = np.random.default_rng(seed)
    frequencies = rng.multinomial(groups, np.full(groups, 1 / groups), size=draws)
    rows = np.bincount(building, minlength=groups)
    density_difference = (
        joined.log_predictive_density_candidate
        - joined.log_predictive_density_reference
    )
    sums = np.bincount(building, weights=density_difference, minlength=groups)
    density_draws = (frequencies @ sums) / (frequencies @ rows)
    weights = frequencies[:, building]
    actual = joined.asking_rent_candidate.to_numpy()
    candidate_error = (
        np.abs(joined.predicted_rent_candidate.to_numpy() / actual - 1) * 100
    )
    reference_error = (
        np.abs(joined.predicted_rent_reference.to_numpy() / actual - 1) * 100
    )
    error_draws = weighted_medians(candidate_error, weights) - weighted_medians(
        reference_error, weights
    )

    def estimate(point, samples):
        lower, upper = np.quantile(samples, [0.025, 0.975])
        return {
            "estimate": float(point),
            "lower_95": float(lower),
            "upper_95": float(upper),
        }

    return {
        "observations": len(joined),
        "buildings": groups,
        "bootstrap_draws": draws,
        "seed": seed,
        "method": "Paired resampling of entire validation buildings, retaining all rows within each sampled building",
        "interpretation": "Conditional comparison on this validation year; not a posterior interval or a guarantee for future years",
        "log_predictive_density_difference": estimate(
            density_difference.mean(), density_draws
        ),
        "median_absolute_percent_error_difference": estimate(
            np.median(candidate_error) - np.median(reference_error), error_draws
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new comparison output")
    result = compare(
        pd.read_parquet(args.candidate / "validation.parquet"),
        pd.read_parquet(args.reference / "validation.parquet"),
    )
    result.update(candidate=str(args.candidate), reference=str(args.reference))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
