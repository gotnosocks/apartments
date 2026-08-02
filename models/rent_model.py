"""Bayesian weekly rent index for The Sierra Chelsea.

The response is log asking rent. Observations are collapsed to one median per
unit-week so frequently repriced furnished listings do not dominate ordinary
rentals.
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
from scipy.special import stdtr

CUTOFF = pd.Timestamp("2019-05-01")
BUILDING_SLUG = "the-sierra-chelsea"
FREQUENCIES = {
    "weekly": {"rw_prior": 0.03, "date_freq": "W-MON", "label": "week"},
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
                  l.floor AS marketed_floor, l.physical_floor, l.unit_format,
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
    # Monday-starting calendar week containing the observed event.
    events["period"] = events["event_date"] - pd.to_timedelta(
        events["event_date"].dt.weekday, unit="D"
    )

    period_data = events.groupby(["unit", "period"], as_index=False).agg(
        asking_rent=("asking_rent", "median"),
        bedrooms=("bedrooms", "first"),
        bathrooms=("bathrooms", "first"),
        square_feet=("square_feet", "first"),
        marketed_floor=("marketed_floor", "first"),
        physical_floor=("physical_floor", "first"),
        unit_format=("unit_format", "first"),
        is_furnished=("is_furnished", "first"),
        source_events=("asking_rent", "size"),
    )
    period_data = period_data.dropna(subset=["bedrooms", "physical_floor", "asking_rent"]).copy()
    period_data["bedrooms"] = period_data["bedrooms"].astype(int)
    period_data["marketed_floor"] = period_data["marketed_floor"].astype(int)
    period_data["physical_floor"] = period_data["physical_floor"].astype(int)
    period_data["square_feet"] = period_data["square_feet"].astype(float)
    period_data["sqft_missing"] = period_data["square_feet"].isna().astype(int)
    bedroom_medians = period_data.groupby("bedrooms")["square_feet"].transform("median")
    period_data["square_feet_imputed"] = period_data["square_feet"].fillna(
        bedroom_medians
    )
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
    floor_levels = sorted(data["physical_floor"].unique())
    floor_lookup = {floor: index for index, floor in enumerate(floor_levels)}
    floor_indices = data["physical_floor"].map(floor_lookup).astype(int).to_numpy()
    coords = {
        "obs_id": np.arange(len(data)),
        "period": periods.strftime("%Y-%m-%d").tolist(),
        "trend_step": periods.strftime("%Y-%m-%d").tolist()[1:],
        "floor": floor_levels,
        "floor_step": floor_levels[1:],
        "unit": unit_names,
    }
    with pm.Model(coords=coords) as model:
        period_idx = pm.Data("period_idx", data["period_idx"].to_numpy(), dims="obs_id")
        unit_idx = pm.Data("unit_idx", data["unit_idx"].to_numpy(), dims="obs_id")
        floor_idx = pm.Data("floor_idx", floor_indices, dims="obs_id")
        furnished = pm.Data(
            "furnished", data["is_furnished"].astype(float).to_numpy(), dims="obs_id"
        )
        has_first_bedroom = pm.Data(
            "has_first_bedroom",
            (data["bedrooms"] >= 1).astype(float).to_numpy(),
            dims="obs_id",
        )
        has_second_bedroom = pm.Data(
            "has_second_bedroom",
            (data["bedrooms"] >= 2).astype(float).to_numpy(),
            dims="obs_id",
        )
        log_sqft_z = pm.Data("log_sqft_z", data["log_sqft_z"].to_numpy(), dims="obs_id")
        sqft_missing = pm.Data(
            "sqft_missing", data["sqft_missing"].to_numpy(), dims="obs_id"
        )

        alpha = pm.Normal("alpha", mu=np.log(5500), sigma=0.7)
        beta_furnished = pm.Normal("beta_furnished", mu=0.15, sigma=0.25)
        beta_first_bedroom = pm.Normal("beta_first_bedroom", mu=0.2, sigma=0.3)
        beta_second_bedroom = pm.Normal("beta_second_bedroom", mu=0.1, sigma=0.25)
        beta_log_sqft = pm.Normal("beta_log_sqft", mu=0.5, sigma=0.3)
        beta_sqft_missing = pm.Normal("beta_sqft_missing", mu=0, sigma=0.15)

        sigma_rw = pm.HalfNormal("sigma_rw", sigma=FREQUENCIES[frequency]["rw_prior"])
        rw_steps = pm.Normal(
            "building_rw_steps", mu=0, sigma=sigma_rw, dims="trend_step"
        )
        building_trend = pm.Deterministic(
            "building_trend",
            pt.concatenate([pt.zeros(1), pt.cumsum(rw_steps)]),
            dims="period",
        )

        # Each level's effect is the cumulative sum of adjacent-floor changes.
        # A shared innovation scale shrinks those changes toward zero.
        sigma_floor = pm.HalfNormal("sigma_floor", sigma=0.03)
        floor_change_z = pm.Normal("floor_change_z", mu=0, sigma=1, dims="floor_step")
        floor_changes = pm.Deterministic(
            "floor_changes", floor_change_z * sigma_floor, dims="floor_step"
        )
        floor_effect = pm.Deterministic(
            "floor_effect",
            pt.concatenate([pt.zeros(1), pt.cumsum(floor_changes)]),
            dims="floor",
        )

        sigma_unit = pm.HalfNormal("sigma_unit", sigma=0.25)
        unit_z = pm.Normal("unit_z", mu=0, sigma=1, dims="unit")
        unit_effect = pm.Deterministic("unit_effect", unit_z * sigma_unit, dims="unit")
        sigma = pm.HalfNormal("sigma", sigma=0.15)

        mu = (
            alpha
            + building_trend[period_idx]
            + beta_furnished * furnished
            + beta_first_bedroom * has_first_bedroom
            + beta_second_bedroom * has_second_bedroom
            + beta_log_sqft * log_sqft_z
            + beta_sqft_missing * sqft_missing
            + floor_effect[floor_idx]
            + unit_effect[unit_idx]
        )
        pm.StudentT(
            "log_rent",
            nu=5,
            mu=mu,
            sigma=sigma,
            observed=data["log_rent"],
            dims="obs_id",
        )
        inference = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            cores=min(chains, 4),
            nuts_sampler="nutpie",
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
    prediction = pd.DataFrame(
        {
            "period": periods,
            "index_median": np.median(index_samples, axis=0),
            "index_lower": np.quantile(index_samples, 0.025, axis=0),
            "index_upper": np.quantile(index_samples, 0.975, axis=0),
        }
    )
    prediction.to_parquet(output_dir / "index.parquet", index=False)

    posterior = inference.posterior
    furnished = posterior["beta_furnished"].values.reshape(-1)
    premium = 100 * (np.exp(furnished) - 1)
    first_bedroom = posterior["beta_first_bedroom"].values.reshape(-1)
    second_bedroom = posterior["beta_second_bedroom"].values.reshape(-1)
    bedroom_effects = {
        "first_bedroom": 100 * (np.exp(first_bedroom) - 1),
        "second_bedroom_increment": 100 * (np.exp(second_bedroom) - 1),
        "two_bedroom_vs_studio": 100 * (np.exp(first_bedroom + second_bedroom) - 1),
    }

    floor_levels = posterior.coords["floor"].values.astype(int)
    floor_effect_samples = posterior["floor_effect"].values.reshape(-1, len(floor_levels))
    floor_change_samples = posterior["floor_changes"].values.reshape(-1, len(floor_levels) - 1)
    unit_counts_by_floor = data.groupby("physical_floor")["unit"].nunique()
    floor_characteristics = data.groupby("physical_floor").agg(
        marketed_floor=("marketed_floor", "first"),
        is_penthouse=("unit_format", lambda values: (values == "penthouse").any()),
    )
    floor_rows = []
    for index, floor in enumerate(floor_levels):
        cumulative = 100 * (np.exp(floor_effect_samples[:, index]) - 1)
        change = (
            np.zeros(floor_effect_samples.shape[0])
            if index == 0
            else 100 * (np.exp(floor_change_samples[:, index - 1]) - 1)
        )
        floor_rows.append({
            "physical_floor": int(floor),
            "marketed_floor": int(floor_characteristics.loc[floor, "marketed_floor"]),
            "floor_label": (
                "PH" if floor_characteristics.loc[floor, "is_penthouse"]
                else str(int(floor_characteristics.loc[floor, "marketed_floor"]))
            ),
            "units": int(unit_counts_by_floor.get(floor, 0)),
            "cumulative_median": float(np.median(cumulative)),
            "cumulative_lower": float(np.quantile(cumulative, 0.025)),
            "cumulative_upper": float(np.quantile(cumulative, 0.975)),
            "increment_median": float(np.median(change)),
            "increment_lower": float(np.quantile(change, 0.025)),
            "increment_upper": float(np.quantile(change, 0.975)),
        })
    pd.DataFrame(floor_rows).to_parquet(output_dir / "floor_effects.parquet", index=False)

    # In-sample observation diagnostics. The tail probability integrates the
    # Student-t CDF over posterior parameter draws; it is not a leave-one-out score.
    observation_floor_lookup = {floor: index for index, floor in enumerate(floor_levels)}
    observation_floor_idx = data["physical_floor"].map(observation_floor_lookup).to_numpy()
    observation_mu = (
        posterior["alpha"].values.reshape(-1, 1)
        + trend[:, data["period_idx"].to_numpy()]
        + furnished.reshape(-1, 1) * data["is_furnished"].astype(float).to_numpy()
        + first_bedroom.reshape(-1, 1) * (data["bedrooms"] >= 1).astype(float).to_numpy()
        + second_bedroom.reshape(-1, 1) * (data["bedrooms"] >= 2).astype(float).to_numpy()
        + posterior["beta_log_sqft"].values.reshape(-1, 1) * data["log_sqft_z"].to_numpy()
        + posterior["beta_sqft_missing"].values.reshape(-1, 1) * data["sqft_missing"].to_numpy()
        + floor_effect_samples[:, observation_floor_idx]
        + posterior["unit_effect"].values.reshape(-1, data["unit"].nunique())[
            :, data["unit_idx"].to_numpy()
        ]
    )
    observed_log_rent = data["log_rent"].to_numpy()
    fitted_log_rent = np.median(observation_mu, axis=0)
    sigma_samples = posterior["sigma"].values.reshape(-1, 1)
    standardized = (observed_log_rent - observation_mu) / sigma_samples
    predictive_cdf = stdtr(5, standardized)
    lower_tail_probability = predictive_cdf.mean(axis=0)
    two_sided_tail_probability = 2 * np.minimum(
        lower_tail_probability, 1 - lower_tail_probability
    )
    observation_diagnostics = data[[
        "unit", "period", "asking_rent", "bedrooms", "marketed_floor",
        "physical_floor", "square_feet", "square_feet_imputed", "sqft_missing",
        "is_furnished", "source_events",
    ]].copy()
    observation_diagnostics["bedroom_group"] = observation_diagnostics["bedrooms"].map(
        {0: "Studio", 1: "1 BR", 2: "2 BR"}
    )
    observation_diagnostics["fitted_rent"] = np.exp(fitted_log_rent)
    observation_diagnostics["residual_dollars"] = (
        observation_diagnostics["asking_rent"] - observation_diagnostics["fitted_rent"]
    )
    observation_diagnostics["residual_percent"] = 100 * (
        observation_diagnostics["asking_rent"] / observation_diagnostics["fitted_rent"] - 1
    )
    observation_diagnostics["standardized_residual"] = np.median(standardized, axis=0)
    observation_diagnostics["tail_probability"] = two_sided_tail_probability
    observation_diagnostics["is_outlier_95"] = two_sided_tail_probability < 0.05
    observation_diagnostics.to_parquet(
        output_dir / "observation_diagnostics.parquet", index=False
    )

    # Adjusted dollar trajectories use each bedroom group's typical square
    # footage at floor 8, an unfurnished listing, observed square footage, and
    # zero unit effect.
    unit_characteristics = (
        data.sort_values("period").groupby("unit", as_index=False).first()
    )
    alpha = posterior["alpha"].values.reshape(-1, 1)
    beta_size = posterior["beta_log_sqft"].values.reshape(-1, 1)
    reference_floor = 8
    reference_floor_index = floor_levels.tolist().index(reference_floor)
    reference_floor_term = floor_effect_samples[:, reference_floor_index].reshape(-1, 1)
    bedroom_rows = []
    for bedrooms, name in [(0, "Studio"), (1, "1 BR"), (2, "2 BR")]:
        group = unit_characteristics[unit_characteristics["bedrooms"] == bedrooms]
        typical_sqft = float(group["square_feet_imputed"].median())
        typical_log_sqft_z = float(group["log_sqft_z"].median())
        bedroom_term = np.zeros_like(first_bedroom).reshape(-1, 1)
        if bedrooms >= 1:
            bedroom_term = bedroom_term + first_bedroom.reshape(-1, 1)
        if bedrooms >= 2:
            bedroom_term = bedroom_term + second_bedroom.reshape(-1, 1)
        price_samples = np.exp(
            alpha
            + trend
            + bedroom_term
            + beta_size * typical_log_sqft_z
            + reference_floor_term
        )
        for index, period in enumerate(periods):
            bedroom_rows.append(
                {
                    "period": period,
                    "bedroom_group": name,
                    "typical_square_feet": typical_sqft,
                    "price_median": float(np.median(price_samples[:, index])),
                    "price_lower": float(np.quantile(price_samples[:, index], 0.025)),
                    "price_upper": float(np.quantile(price_samples[:, index], 0.975)),
                }
            )
    pd.DataFrame(bedroom_rows).to_parquet(
        output_dir / "bedroom_prices.parquet", index=False
    )

    diagnostics = az.summary(
        inference,
        var_names=[
            "beta_furnished",
            "beta_first_bedroom",
            "beta_second_bedroom",
            "sigma_rw",
            "sigma_floor",
            "sigma_unit",
            "sigma",
        ],
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
        "floor_reference": 3,
        "bedroom_price_reference_floor": reference_floor,
        "furnished_premium_percent": {
            "median": float(np.median(premium)),
            "lower_95": float(np.quantile(premium, 0.025)),
            "upper_95": float(np.quantile(premium, 0.975)),
        },
        "bedroom_premiums_percent": {
            name: {
                "median": float(np.median(samples)),
                "lower_95": float(np.quantile(samples, 0.025)),
                "upper_95": float(np.quantile(samples, 0.975)),
            }
            for name, samples in bedroom_effects.items()
        },
        "max_rhat": float(diagnostics["r_hat"].max()),
        "min_ess_bulk": float(diagnostics["ess_bulk"].min()),
        "sampler": "nutpie",
        "divergences": int(inference.sample_stats["diverging"].sum().item()),
        "assumptions": [
            f"One median asking-rent observation per unit-{label}.",
            "Furnished status begins at each unit's first explicit 'Listed by The Blueground' event; uncertain transfer windows are excluded.",
            f"The {frequency} building trend is a Gaussian random walk anchored at 100 in the first post-cutoff {label}.",
            "Cumulative >=1-bedroom and >=2-bedroom indicators estimate the first and incremental second bedroom premiums.",
            "Physical floor 3 is the floor-effect baseline; each higher physical floor cumulatively sums shrunk adjacent-level changes.",
            "Marketed floors 14 and 15 map to physical floors 13 and 14 because the building has no marketed floor 13.",
            "Imputed square footage, missing-square-footage status, and unit random effects are controls.",
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
    inference = fit_model(
        data, periods, args.frequency, args.draws, args.tune, args.chains
    )
    save_outputs(inference, data, periods, args.frequency, output)
    print(f"Saved model outputs to {output}")


if __name__ == "__main__":
    main()
