"""Bayesian weekly/monthly rent index for The Sierra Chelsea.

The response is log asking rent. Observations are collapsed to one median per
unit-period so frequently repriced furnished listings do not dominate ordinary
rentals. Weekly is the primary model; monthly is a sensitivity analysis.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import arviz as az
import duckdb
import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt

CUTOFF = pd.Timestamp("2019-05-01")
BUILDING_SLUG = "the-sierra-chelsea"
FREQUENCIES = {
    "weekly": {"rw_prior": 0.03, "date_freq": "W-MON", "label": "week"},
    "monthly": {"rw_prior": 0.06, "date_freq": "MS", "label": "month"},
}


def prepare_data(
    db_path: Path,
    frequency: str = "weekly",
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    if frequency not in FREQUENCIES:
        raise ValueError(f"Unknown frequency: {frequency}")
    connection = duckdb.connect(str(db_path), read_only=True)
    events = connection.execute(
        """SELECT l.unit, l.bedrooms, l.bathrooms, l.square_feet,
                  CASE
                    WHEN fp.furnishing_status = 'confirmed-furnished' THEN true
                    WHEN fp.furnishing_status = 'unknown-transition' THEN NULL
                    ELSE false
                  END AS is_furnished,
                  fp.furnishing_status,
                  CAST(e.event_at AS DATE) AS event_date,
                  e.price AS asking_rent
           FROM listing_events e
           JOIN listings l USING (source, source_listing_id)
           LEFT JOIN unit_furnishing_periods fp
             ON fp.source=e.source
            AND fp.building_slug=?
            AND fp.unit=l.unit
            AND CAST(e.event_at AS DATE) >= fp.starts_on
            AND (fp.ends_on IS NULL OR CAST(e.event_at AS DATE) <= fp.ends_on)
           WHERE e.source = 'streeteasy'
             AND e.source_listing_id LIKE ?
             AND e.event_at >= ?
             AND e.price BETWEEN 1000 AND 30000
             AND COALESCE(l.unit_is_specific, true)""",
        [BUILDING_SLUG, f"{BUILDING_SLUG}/%", CUTOFF.date()],
    ).df()
    connection.close()
    events["event_date"] = pd.to_datetime(events["event_date"])
    events = events.dropna(subset=["is_furnished"]).copy()
    events["is_furnished"] = events["is_furnished"].astype(bool)
    if frequency == "weekly":
        # Monday-starting calendar week containing the observed event.
        events["period"] = events["event_date"] - pd.to_timedelta(
            events["event_date"].dt.weekday, unit="D"
        )
    else:
        events["period"] = events["event_date"].dt.to_period("M").dt.to_timestamp()

    period_data = events.groupby(["unit", "period"], as_index=False).agg(
        asking_rent=("asking_rent", "median"),
        bedrooms=("bedrooms", "first"),
        bathrooms=("bathrooms", "first"),
        square_feet=("square_feet", "first"),
        is_furnished=("is_furnished", "first"),
        source_events=("asking_rent", "size"),
    )
    period_data = period_data.dropna(subset=["bedrooms", "asking_rent"]).copy()
    period_data["bedrooms"] = period_data["bedrooms"].astype(int)
    period_data["sqft_missing"] = period_data["square_feet"].isna().astype(int)
    bedroom_medians = period_data.groupby("bedrooms")["square_feet"].transform("median")
    period_data["square_feet_imputed"] = period_data["square_feet"].fillna(bedroom_medians)
    period_data["square_feet_imputed"] = period_data["square_feet_imputed"].fillna(
        period_data["square_feet"].median()
    )
    log_sqft = np.log(period_data["square_feet_imputed"])
    period_data["log_sqft_z"] = (log_sqft - log_sqft.mean()) / log_sqft.std()
    period_data["log_rent"] = np.log(period_data["asking_rent"])

    periods = pd.date_range(
        period_data["period"].min(),
        period_data["period"].max(),
        freq=FREQUENCIES[frequency]["date_freq"],
    )
    period_lookup = {period: index for index, period in enumerate(periods)}
    unit_names = sorted(period_data["unit"].unique())
    unit_lookup = {unit: index for index, unit in enumerate(unit_names)}
    period_data["period_idx"] = period_data["period"].map(period_lookup).astype(int)
    period_data["unit_idx"] = period_data["unit"].map(unit_lookup).astype(int)
    return period_data, periods


def fit_model(
    data: pd.DataFrame,
    periods: pd.DatetimeIndex,
    frequency: str,
    draws: int,
    tune: int,
    chains: int,
):
    unit_names = sorted(data["unit"].unique())
    coords = {
        "obs_id": np.arange(len(data)),
        "period": periods.strftime("%Y-%m-%d").tolist(),
        "trend_step": periods.strftime("%Y-%m-%d").tolist()[1:],
        "unit": unit_names,
    }
    with pm.Model(coords=coords) as model:
        period_idx = pm.Data("period_idx", data["period_idx"].to_numpy(), dims="obs_id")
        unit_idx = pm.Data("unit_idx", data["unit_idx"].to_numpy(), dims="obs_id")
        furnished = pm.Data("furnished", data["is_furnished"].astype(float).to_numpy(), dims="obs_id")
        one_bed = pm.Data("one_bed", (data["bedrooms"] == 1).astype(float).to_numpy(), dims="obs_id")
        two_bed = pm.Data("two_bed", (data["bedrooms"] >= 2).astype(float).to_numpy(), dims="obs_id")
        log_sqft_z = pm.Data("log_sqft_z", data["log_sqft_z"].to_numpy(), dims="obs_id")
        sqft_missing = pm.Data("sqft_missing", data["sqft_missing"].to_numpy(), dims="obs_id")

        alpha = pm.Normal("alpha", mu=np.log(5500), sigma=0.7)
        beta_furnished = pm.Normal("beta_furnished", mu=0.15, sigma=0.25)
        beta_one_bed = pm.Normal("beta_one_bed", mu=0.25, sigma=0.3)
        beta_two_bed = pm.Normal("beta_two_bed", mu=0.55, sigma=0.35)
        beta_log_sqft = pm.Normal("beta_log_sqft", mu=0.5, sigma=0.3)
        beta_sqft_missing = pm.Normal("beta_sqft_missing", mu=0, sigma=0.15)

        sigma_rw = pm.HalfNormal("sigma_rw", sigma=FREQUENCIES[frequency]["rw_prior"])
        rw_steps = pm.Normal("building_rw_steps", mu=0, sigma=sigma_rw, dims="trend_step")
        building_trend = pm.Deterministic(
            "building_trend",
            pt.concatenate([pt.zeros(1), pt.cumsum(rw_steps)]),
            dims="period",
        )

        sigma_unit = pm.HalfNormal("sigma_unit", sigma=0.25)
        unit_z = pm.Normal("unit_z", mu=0, sigma=1, dims="unit")
        unit_effect = pm.Deterministic("unit_effect", unit_z * sigma_unit, dims="unit")
        sigma = pm.HalfNormal("sigma", sigma=0.15)

        mu = (
            alpha
            + building_trend[period_idx]
            + beta_furnished * furnished
            + beta_one_bed * one_bed
            + beta_two_bed * two_bed
            + beta_log_sqft * log_sqft_z
            + beta_sqft_missing * sqft_missing
            + unit_effect[unit_idx]
        )
        pm.StudentT("log_rent", nu=5, mu=mu, sigma=sigma, observed=data["log_rent"], dims="obs_id")
        inference = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            cores=min(chains, 4),
            target_accept=0.92,
            random_seed=150130,
            progressbar=False,
            return_inferencedata=True,
        )
    return inference


def save_outputs(
    inference,
    data: pd.DataFrame,
    periods: pd.DatetimeIndex,
    frequency: str,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    inference.to_netcdf(output_dir / "posterior.nc")
    data.to_parquet(output_dir / "training_data.parquet", index=False)

    trend = inference.posterior["building_trend"].values.reshape(-1, len(periods))
    index_samples = 100 * np.exp(trend)
    prediction = pd.DataFrame({
        "period": periods,
        "index_median": np.median(index_samples, axis=0),
        "index_lower": np.quantile(index_samples, 0.025, axis=0),
        "index_upper": np.quantile(index_samples, 0.975, axis=0),
    })
    prediction.to_parquet(output_dir / "index.parquet", index=False)

    furnished = inference.posterior["beta_furnished"].values.reshape(-1)
    premium = 100 * (np.exp(furnished) - 1)
    diagnostics = az.summary(
        inference,
        var_names=["beta_furnished", "sigma_rw", "sigma_unit", "sigma"],
        kind="diagnostics",
    )
    label = FREQUENCIES[frequency]["label"]
    metadata = {
        "building_slug": BUILDING_SLUG,
        "frequency": frequency,
        "cutoff": CUTOFF.date().isoformat(),
        "index_base_period": periods[0].date().isoformat(),
        "observations": len(data),
        "units": int(data["unit"].nunique()),
        "periods": len(periods),
        "furnished_units": int(data.loc[data["is_furnished"], "unit"].nunique()),
        "furnished_premium_percent": {
            "median": float(np.median(premium)),
            "lower_95": float(np.quantile(premium, 0.025)),
            "upper_95": float(np.quantile(premium, 0.975)),
        },
        "max_rhat": float(diagnostics["r_hat"].max()),
        "min_ess_bulk": float(diagnostics["ess_bulk"].min()),
        "assumptions": [
            f"One median asking-rent observation per unit-{label}.",
            "Furnished status begins at each unit's first explicit 'Listed by The Blueground' event; uncertain transfer windows are excluded.",
            f"The {frequency} building trend is a Gaussian random walk anchored at 100 in the first post-cutoff {label}.",
            "Bedroom count, imputed square footage, missing-square-footage status, and unit random effects are controls.",
        ],
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/apartments.duckdb"))
    parser.add_argument("--frequency", choices=sorted(FREQUENCIES), default="weekly")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--draws", type=int, default=1000)
    parser.add_argument("--tune", type=int, default=1000)
    parser.add_argument("--chains", type=int, default=4)
    args = parser.parse_args()
    output = args.output or Path("data/model") / args.frequency
    data, periods = prepare_data(args.db, args.frequency)
    label = FREQUENCIES[args.frequency]["label"]
    print(
        f"Fitting {len(data)} unit-{label} observations from {data.unit.nunique()} units "
        f"over {len(periods)} {label}s; "
        f"{data.loc[data.is_furnished, 'unit'].nunique()} furnished units."
    )
    inference = fit_model(data, periods, args.frequency, args.draws, args.tune, args.chains)
    save_outputs(inference, data, periods, args.frequency, output)
    print(f"Saved model outputs to {output}")


if __name__ == "__main__":
    main()
