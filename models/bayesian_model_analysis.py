"""Additional diagnostics and matched validation summaries for Bayesian rent fits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


def energy_diagnostics(stats):
    """Energy mixing within each chain, with tuning already excluded."""
    energy = stats["energy"].transpose("chain", "draw").values
    bfmi = np.mean(np.diff(energy, axis=1) ** 2, axis=1) / np.var(energy, axis=1)
    return {
        "bfmi_per_chain": bfmi.tolist(),
        "min_bfmi": float(bfmi.min()),
        "maxdepth_reached": (
            int(stats["maxdepth_reached"].sum())
            if "maxdepth_reached" in stats
            else None
        ),
        "median_n_steps": float(stats["n_steps"].median()),
        "mean_acceptance": float(stats["mean_tree_accept"].mean()),
    }


def summarize_group(frame):
    actual = frame.asking_rent.to_numpy()
    ratio = frame.predicted_rent.to_numpy() / actual
    return pd.Series(
        {
            "observations": len(frame),
            "median_absolute_percent_error": float(np.median(np.abs(ratio - 1)) * 100),
            "median_signed_percent_error": float(np.median(ratio - 1) * 100),
            "log_rmse": float(np.sqrt(np.mean(np.log(ratio) ** 2))),
            "coverage_80": float(
                np.mean(actual >= frame.lower_80) - np.mean(actual > frame.upper_80)
            )
            * 100,
            "coverage_95": float(
                np.mean(actual >= frame.lower_95) - np.mean(actual > frame.upper_95)
            )
            * 100,
        }
    )


def analyze(directory, output):
    directory, output = Path(directory), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    settings = json.loads((directory / "settings.json").read_text())
    with xr.open_datatree(directory / "posterior.nc", engine="h5netcdf") as tree:
        energy = energy_diagnostics(tree["sample_stats"].to_dataset())
        posterior = tree["posterior"].to_dataset()
        summaries = []
        for name in [
            "alpha",
            "sigma",
            "sigma_building",
            "sigma_unit",
            "trend_scale",
            "season_scale",
            "annual_drift",
        ]:
            if name not in posterior:
                continue
            values = posterior[name].values.reshape(-1)
            lo, median, hi = np.quantile(values, [0.025, 0.5, 0.975])
            summaries.append(
                {"parameter": name, "lower_95": lo, "median": median, "upper_95": hi}
            )
        pd.DataFrame(summaries).to_parquet(output / "scales.parquet", index=False)
        trend = posterior["trend"].values.reshape(-1, posterior.sizes["period"])
        periods = pd.DatetimeIndex(posterior.period.values)
        changes = []
        for months in [12, 24, 60]:
            if len(periods) <= months:
                continue
            difference = 100 * np.expm1(trend[:, -1] - trend[:, -1 - months])
            lo, median, hi = np.quantile(difference, [0.025, 0.5, 0.975])
            changes.append(
                {
                    "from": str(periods[-1 - months].date()),
                    "to": str(periods[-1].date()),
                    "lower_95_percent": lo,
                    "median_percent": median,
                    "upper_95_percent": hi,
                }
            )
        pd.DataFrame(changes).to_parquet(output / "market_changes.parquet", index=False)
    (output / "energy.json").write_text(json.dumps(energy, indent=2))

    if (directory / "validation.parquet").exists():
        predictions = pd.read_parquet(directory / "validation.parquet")
        data = pd.read_parquet(settings["input"])
        details = data[["unit_id", "period", "square_feet", "bathrooms"]]
        predictions = predictions.merge(
            details, on=["unit_id", "period"], validate="one_to_one"
        )
        predictions["size_missing"] = predictions.square_feet.isna()
        # Reconstruct exposure from the training data so no-unit ablations use
        # exactly the same seen/unseen definition as models with unit effects.
        training = data[data.period <= pd.Timestamp(settings["train_end"])]
        if not settings.get("holdout_units"):
            predictions["seen_unit"] = predictions.unit_id.isin(training.unit_id)
        groups = {}
        for column in [
            "period",
            "bedrooms",
            "seen_unit",
            "seen_building",
            "size_missing",
        ]:
            grouped = (
                predictions.groupby(column)
                .apply(summarize_group, include_groups=False)
                .reset_index()
            )
            grouped.to_parquet(output / f"by_{column}.parquet", index=False)
            groups[column] = grouped.astype({column: str}).to_dict(orient="records")
        (output / "validation_groups.json").write_text(json.dumps(groups, indent=2))
    return energy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.model, args.output), indent=2))


if __name__ == "__main__":
    main()
