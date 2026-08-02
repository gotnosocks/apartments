"""Bayesian weekly rent model for neighboring West 15th Street buildings.

The response is log asking rent. Observations are collapsed to one median per
building-unit-week. Units with confirmed Blueground furnished periods are
excluded from modeling.
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
BUILDINGS = {
    "the-sierra-chelsea": "The Sierra Chelsea",
    "stonehenge-gardens": "Stonehenge Gardens",
    "101w15-101-west-15th-street-new_york": "101 W 15th",
}
REFERENCE_BUILDING = "the-sierra-chelsea"
FLOOR_REFERENCES = {
    "the-sierra-chelsea": 3,
    "stonehenge-gardens": 3,
    "101w15-101-west-15th-street-new_york": 3,
}
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
        """SELECT l.building_slug, l.unit, l.bedrooms, l.bathrooms, l.square_feet,
                  l.floor AS marketed_floor, l.physical_floor, l.unit_format,
                  l.is_garden_facing, l.is_street_facing,
                  CAST(e.event_at AS DATE) AS event_date,
                  e.price AS asking_rent
           FROM listing_events e
           JOIN listings l USING (source, source_listing_id)
           WHERE e.source = 'streeteasy'
             AND l.building_slug IN (?, ?, ?)
             AND e.event_at >= ?
             AND e.price BETWEEN 1000 AND 30000
             AND COALESCE(l.unit_is_specific, true)
             AND NOT EXISTS (
                 SELECT 1
                 FROM unit_furnishing_periods fp
                 WHERE fp.source=e.source
                   AND fp.building_slug=l.building_slug
                   AND fp.unit=l.unit
                   AND fp.furnishing_status='confirmed-furnished'
             )""",
        [*BUILDINGS, CUTOFF.date()],
    ).df()
    excluded_blueground_units = [
        {"building_slug": row[0], "unit": row[1]}
        for row in connection.execute(
            """SELECT DISTINCT building_slug, unit
               FROM unit_furnishing_periods
               WHERE source='streeteasy'
                 AND building_slug IN (?, ?, ?)
                 AND furnishing_status='confirmed-furnished'
               ORDER BY building_slug, unit""",
            list(BUILDINGS),
        ).fetchall()
    ]
    connection.close()
    events["event_date"] = pd.to_datetime(events["event_date"])
    # Monday-starting calendar week containing the observed event.
    events["period"] = events["event_date"] - pd.to_timedelta(
        events["event_date"].dt.weekday, unit="D"
    )

    period_data = events.groupby(["building_slug", "unit", "period"], as_index=False).agg(
        asking_rent=("asking_rent", "median"),
        bedrooms=("bedrooms", "first"),
        bathrooms=("bathrooms", "first"),
        square_feet=("square_feet", "first"),
        marketed_floor=("marketed_floor", "first"),
        physical_floor=("physical_floor", "first"),
        unit_format=("unit_format", "first"),
        is_garden_facing=("is_garden_facing", "first"),
        is_street_facing=("is_street_facing", "first"),
        source_events=("asking_rent", "size"),
    )
    period_data = period_data.dropna(subset=[
        "bedrooms", "physical_floor", "asking_rent"
    ]).copy()
    period_data["bedrooms"] = period_data["bedrooms"].astype(int)
    period_data["marketed_floor"] = period_data["marketed_floor"].astype(int)
    period_data["physical_floor"] = period_data["physical_floor"].astype(int)
    period_data["square_feet"] = period_data["square_feet"].astype(float)
    period_data["is_garden_facing"] = period_data["is_garden_facing"].fillna(False).astype(bool)
    period_data["is_street_facing"] = period_data["is_street_facing"].fillna(False).astype(bool)
    period_data["facing_contrast"] = (
        period_data["is_street_facing"].astype(float)
        - period_data["is_garden_facing"].astype(float)
    ) / 2
    period_data["both_facing"] = (
        period_data["is_garden_facing"] & period_data["is_street_facing"]
    ).astype(float)
    period_data["sqft_missing"] = period_data["square_feet"].isna().astype(int)
    bedroom_medians = period_data.groupby(["building_slug", "bedrooms"])["square_feet"].transform("median")
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
    period_data["unit_key"] = period_data["building_slug"] + "/" + period_data["unit"]
    unit_names = sorted(period_data["unit_key"].unique())
    unit_lookup = {unit: index for index, unit in enumerate(unit_names)}
    building_lookup = {building: index for index, building in enumerate(BUILDINGS)}
    period_data["period_idx"] = period_data["period"].map(period_lookup).astype(int)
    period_data["unit_idx"] = period_data["unit_key"].map(unit_lookup).astype(int)
    period_data["building_idx"] = period_data["building_slug"].map(building_lookup).astype(int)
    period_data.attrs["excluded_blueground_units"] = excluded_blueground_units
    return period_data, periods


def fit_model(
    data: pd.DataFrame,
    periods: pd.DatetimeIndex,
    frequency: str,
    draws: int,
    tune: int,
    chains: int,
):
    unit_names = sorted(data["unit_key"].unique())
    floor_groups = {
        building: sorted(group["physical_floor"].unique())
        for building, group in data.groupby("building_slug")
    }
    floor_cells = [
        (building, floor)
        for building in BUILDINGS
        for floor in floor_groups[building]
    ]
    floor_steps = [
        (building, floor)
        for building in BUILDINGS
        for floor in floor_groups[building][1:]
    ]
    floor_lookup = {cell: index for index, cell in enumerate(floor_cells)}
    floor_indices = np.array([
        floor_lookup[(building, floor)]
        for building, floor in zip(data["building_slug"], data["physical_floor"])
    ])
    coords = {
        "obs_id": np.arange(len(data)),
        "period": periods.strftime("%Y-%m-%d").tolist(),
        "trend_step": periods.strftime("%Y-%m-%d").tolist()[1:],
        "building": list(BUILDINGS),
        "floor_cell": [f"{building}:{floor}" for building, floor in floor_cells],
        "floor_step": [f"{building}:{floor}" for building, floor in floor_steps],
        "unit": unit_names,
    }
    with pm.Model(coords=coords) as model:
        period_idx = pm.Data("period_idx", data["period_idx"].to_numpy(), dims="obs_id")
        unit_idx = pm.Data("unit_idx", data["unit_idx"].to_numpy(), dims="obs_id")
        floor_idx = pm.Data("floor_idx", floor_indices, dims="obs_id")
        building_idx = pm.Data("building_idx", data["building_idx"].to_numpy(), dims="obs_id")
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
        has_third_bedroom = pm.Data(
            "has_third_bedroom",
            (data["bedrooms"] >= 3).astype(float).to_numpy(),
            dims="obs_id",
        )
        log_sqft_z = pm.Data("log_sqft_z", data["log_sqft_z"].to_numpy(), dims="obs_id")
        sqft_missing = pm.Data(
            "sqft_missing", data["sqft_missing"].to_numpy(), dims="obs_id"
        )
        facing_contrast = pm.Data(
            "facing_contrast", data["facing_contrast"].to_numpy(), dims="obs_id"
        )
        both_facing = pm.Data(
            "both_facing", data["both_facing"].to_numpy(), dims="obs_id"
        )

        alpha = pm.Normal("alpha", mu=np.log(5500), sigma=0.7)
        beta_first_bedroom = pm.Normal("beta_first_bedroom", mu=0.2, sigma=0.3)
        beta_second_bedroom = pm.Normal("beta_second_bedroom", mu=0.1, sigma=0.25)
        beta_third_bedroom = pm.Normal("beta_third_bedroom", mu=0.1, sigma=0.3)
        beta_stonehenge = pm.Normal("beta_stonehenge", mu=-0.15, sigma=0.3)
        beta_101w15 = pm.Normal("beta_101w15", mu=-0.1, sigma=0.3)
        building_offset = pm.Deterministic(
            "building_offset",
            pt.stack([0, beta_stonehenge, beta_101w15]),
            dims="building",
        )
        beta_log_sqft = pm.Normal("beta_log_sqft", mu=0.5, sigma=0.3)
        beta_sqft_missing = pm.Normal("beta_sqft_missing", mu=0, sigma=0.15)
        beta_skyline_vs_garden = pm.Normal("beta_skyline_vs_garden", mu=0, sigma=0.15)
        beta_both_facing = pm.Normal("beta_both_facing", mu=0, sigma=0.15)

        sigma_rw = pm.HalfNormal("sigma_rw", sigma=FREQUENCIES[frequency]["rw_prior"])
        building_rw_z = pm.Normal(
            "building_rw_z", mu=0, sigma=1, dims="trend_step"
        )
        rw_steps = pm.Deterministic(
            "building_rw_steps", building_rw_z * sigma_rw, dims="trend_step"
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
        floor_effect_blocks = []
        step_offset = 0
        for building in BUILDINGS:
            step_count = len(floor_groups[building]) - 1
            building_changes = floor_changes[step_offset:step_offset + step_count]
            raw_floor_effect = pt.concatenate([pt.zeros(1), pt.cumsum(building_changes)])
            reference_index = floor_groups[building].index(FLOOR_REFERENCES[building])
            floor_effect_blocks.append(raw_floor_effect - raw_floor_effect[reference_index])
            step_offset += step_count
        floor_effect = pm.Deterministic(
            "floor_effect", pt.concatenate(floor_effect_blocks), dims="floor_cell"
        )

        sigma_unit = pm.HalfNormal("sigma_unit", sigma=0.25)
        unit_z = pm.Normal("unit_z", mu=0, sigma=1, dims="unit")
        unit_effect = pm.Deterministic("unit_effect", unit_z * sigma_unit, dims="unit")
        sigma = pm.HalfNormal("sigma", sigma=0.15)

        mu = (
            alpha
            + building_trend[period_idx]
            + building_offset[building_idx]
            + beta_first_bedroom * has_first_bedroom
            + beta_second_bedroom * has_second_bedroom
            + beta_third_bedroom * has_third_bedroom
            + beta_log_sqft * log_sqft_z
            + beta_sqft_missing * sqft_missing
            + beta_skyline_vs_garden * facing_contrast
            + beta_both_facing * both_facing
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
    first_bedroom = posterior["beta_first_bedroom"].values.reshape(-1)
    second_bedroom = posterior["beta_second_bedroom"].values.reshape(-1)
    third_bedroom = posterior["beta_third_bedroom"].values.reshape(-1)
    building_offset_samples = posterior["building_offset"].values.reshape(-1, len(BUILDINGS))
    bedroom_effects = {
        "first_bedroom": 100 * (np.exp(first_bedroom) - 1),
        "second_bedroom_increment": 100 * (np.exp(second_bedroom) - 1),
        "third_bedroom_increment": 100 * (np.exp(third_bedroom) - 1),
        "two_bedroom_vs_studio": 100 * (np.exp(first_bedroom + second_bedroom) - 1),
        "three_bedroom_vs_studio": 100 * (
            np.exp(first_bedroom + second_bedroom + third_bedroom) - 1
        ),
    }
    skyline_vs_garden = posterior["beta_skyline_vs_garden"].values.reshape(-1)
    both_facing = posterior["beta_both_facing"].values.reshape(-1)
    facing_effects = {
        "skyline_vs_garden": 100 * (np.exp(skyline_vs_garden) - 1),
        "both_vs_single_facing_midpoint": 100 * (np.exp(both_facing) - 1),
    }

    floor_groups = {
        building: sorted(group["physical_floor"].unique())
        for building, group in data.groupby("building_slug")
    }
    floor_cells = [
        (building, floor)
        for building in BUILDINGS
        for floor in floor_groups[building]
    ]
    floor_lookup = {cell: index for index, cell in enumerate(floor_cells)}
    floor_effect_samples = posterior["floor_effect"].values.reshape(-1, len(floor_cells))
    floor_change_samples = posterior["floor_changes"].values.reshape(
        -1, len(floor_cells) - len(BUILDINGS)
    )
    unit_counts_by_floor = data.groupby(["building_slug", "physical_floor"])["unit"].nunique()
    floor_characteristics = data.groupby(["building_slug", "physical_floor"]).agg(
        marketed_floor=("marketed_floor", "first"),
        is_penthouse=("unit_format", lambda values: (values == "penthouse").any()),
    )
    floor_rows = []
    change_index = 0
    for index, (building, floor) in enumerate(floor_cells):
        building_floor_index = floor_groups[building].index(floor)
        cumulative = 100 * (np.exp(floor_effect_samples[:, index]) - 1)
        if building_floor_index == 0:
            change = np.zeros(floor_effect_samples.shape[0])
        else:
            change = 100 * (np.exp(floor_change_samples[:, change_index]) - 1)
            change_index += 1
        characteristics = floor_characteristics.loc[(building, floor)]
        floor_rows.append({
            "building_slug": building,
            "building_name": BUILDINGS[building],
            "physical_floor": int(floor),
            "marketed_floor": int(characteristics["marketed_floor"]),
            "floor_label": (
                "PH" if characteristics["is_penthouse"]
                else str(int(characteristics["marketed_floor"]))
            ),
            "units": int(unit_counts_by_floor.get((building, floor), 0)),
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
    observation_floor_idx = np.array([
        floor_lookup[(building, floor)]
        for building, floor in zip(data["building_slug"], data["physical_floor"])
    ])
    observation_mu = (
        posterior["alpha"].values.reshape(-1, 1)
        + trend[:, data["period_idx"].to_numpy()]
        + building_offset_samples[:, data["building_idx"].to_numpy()]
        + first_bedroom.reshape(-1, 1) * (data["bedrooms"] >= 1).astype(float).to_numpy()
        + second_bedroom.reshape(-1, 1) * (data["bedrooms"] >= 2).astype(float).to_numpy()
        + third_bedroom.reshape(-1, 1) * (data["bedrooms"] >= 3).astype(float).to_numpy()
        + posterior["beta_log_sqft"].values.reshape(-1, 1) * data["log_sqft_z"].to_numpy()
        + posterior["beta_sqft_missing"].values.reshape(-1, 1) * data["sqft_missing"].to_numpy()
        + skyline_vs_garden.reshape(-1, 1) * data["facing_contrast"].to_numpy()
        + both_facing.reshape(-1, 1) * data["both_facing"].to_numpy()
        + floor_effect_samples[:, observation_floor_idx]
        + posterior["unit_effect"].values.reshape(-1, data["unit_key"].nunique())[
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
        "building_slug", "unit", "period", "asking_rent", "bedrooms", "marketed_floor",
        "physical_floor", "square_feet", "square_feet_imputed", "sqft_missing",
        "is_garden_facing", "is_street_facing", "source_events",
    ]].copy()
    observation_diagnostics["bedroom_group"] = observation_diagnostics["bedrooms"].map(
        {0: "Studio", 1: "1 BR", 2: "2 BR", 3: "3 BR"}
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

    # Adjusted dollar trajectories use each building-bedroom group's typical
    # square footage at a representative floor, neutral facing, and zero unit effect.
    unit_characteristics = (
        data.sort_values("period").groupby("unit_key", as_index=False).first()
    )
    alpha = posterior["alpha"].values.reshape(-1, 1)
    beta_size = posterior["beta_log_sqft"].values.reshape(-1, 1)
    reference_floors = {
        "the-sierra-chelsea": 8,
        "stonehenge-gardens": 4,
        "101w15-101-west-15th-street-new_york": 4,
    }
    bedroom_rows = []
    bedroom_names = {0: "Studio", 1: "1 BR", 2: "2 BR", 3: "3 BR"}
    for building_index, building in enumerate(BUILDINGS):
        building_units = unit_characteristics[
            unit_characteristics["building_slug"] == building
        ]
        reference_floor = reference_floors[building]
        reference_floor_index = floor_lookup[(building, reference_floor)]
        reference_floor_term = floor_effect_samples[:, reference_floor_index].reshape(-1, 1)
        building_term = building_offset_samples[:, building_index].reshape(-1, 1)
        for bedrooms in sorted(building_units["bedrooms"].unique()):
            group = building_units[building_units["bedrooms"] == bedrooms]
            typical_sqft = float(group["square_feet_imputed"].median())
            typical_log_sqft_z = float(group["log_sqft_z"].median())
            bedroom_term = np.zeros_like(first_bedroom).reshape(-1, 1)
            if bedrooms >= 1:
                bedroom_term += first_bedroom.reshape(-1, 1)
            if bedrooms >= 2:
                bedroom_term += second_bedroom.reshape(-1, 1)
            if bedrooms >= 3:
                bedroom_term += third_bedroom.reshape(-1, 1)
            price_samples = np.exp(
                alpha
                + trend
                + building_term
                + bedroom_term
                + beta_size * typical_log_sqft_z
                + reference_floor_term
            )
            for index, period in enumerate(periods):
                bedroom_rows.append(
                    {
                        "building_slug": building,
                        "building_name": BUILDINGS[building],
                        "reference_floor": reference_floor,
                        "period": period,
                        "bedroom_group": bedroom_names[int(bedrooms)],
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
            "beta_first_bedroom",
            "beta_second_bedroom",
            "beta_third_bedroom",
            "beta_stonehenge",
            "beta_101w15",
            "beta_skyline_vs_garden",
            "beta_both_facing",
            "sigma_rw",
            "sigma_floor",
            "sigma_unit",
            "sigma",
        ],
        kind="diagnostics",
    )
    label = FREQUENCIES[frequency]["label"]
    stonehenge_effect = 100 * (
        np.exp(posterior["beta_stonehenge"].values.reshape(-1)) - 1
    )
    building_101_effect = 100 * (
        np.exp(posterior["beta_101w15"].values.reshape(-1)) - 1
    )
    metadata = {
        "buildings": BUILDINGS,
        "reference_building": REFERENCE_BUILDING,
        "frequency": frequency,
        "cutoff": CUTOFF.date().isoformat(),
        "index_base_period": periods[0].date().isoformat(),
        "observations": len(data),
        "units": int(data["unit_key"].nunique()),
        "units_by_building": data.groupby("building_slug")["unit"].nunique().to_dict(),
        "observations_by_building": data.groupby("building_slug").size().to_dict(),
        "periods": len(periods),
        "excluded_blueground_units": data.attrs.get("excluded_blueground_units", []),
        "floor_references": FLOOR_REFERENCES,
        "bedroom_price_reference_floors": reference_floors,
        "building_effects_vs_sierra_percent": {
            "stonehenge-gardens": {
                "median": float(np.median(stonehenge_effect)),
                "lower_95": float(np.quantile(stonehenge_effect, 0.025)),
                "upper_95": float(np.quantile(stonehenge_effect, 0.975)),
            },
            "101w15-101-west-15th-street-new_york": {
                "median": float(np.median(building_101_effect)),
                "lower_95": float(np.quantile(building_101_effect, 0.025)),
                "upper_95": float(np.quantile(building_101_effect, 0.975)),
            },
        },
        "bedroom_premiums_percent": {
            name: {
                "median": float(np.median(samples)),
                "lower_95": float(np.quantile(samples, 0.025)),
                "upper_95": float(np.quantile(samples, 0.975)),
            }
            for name, samples in bedroom_effects.items()
        },
        "facing_effects_percent": {
            name: {
                "median": float(np.median(samples)),
                "lower_95": float(np.quantile(samples, 0.025)),
                "upper_95": float(np.quantile(samples, 0.975)),
            }
            for name, samples in facing_effects.items()
        },
        "max_rhat": float(diagnostics["r_hat"].max()),
        "min_ess_bulk": float(diagnostics["ess_bulk"].min()),
        "sampler": "nutpie",
        "divergences": int(inference.sample_stats["diverging"].sum().item()),
        "assumptions": [
            f"One median asking-rent observation per unit-{label}.",
            "Every unit with any confirmed Blueground furnished period is excluded from all model training periods.",
            f"A shared three-building {frequency} market trend is a Gaussian random walk anchored at 100 in the first post-cutoff {label}.",
            "Stonehenge Gardens and 101 W 15th each have a time-constant adjusted offset relative to The Sierra Chelsea.",
            "Cumulative >=1-bedroom, >=2-bedroom, and >=3-bedroom indicators estimate incremental bedroom premiums.",
            "Physical floor 3 is the floor-effect baseline in both buildings; other floors cumulatively sum shrunk adjacent-level changes.",
            "Marketed floors 14 and 15 map to physical floors 13 and 14 because the building has no marketed floor 13.",
            "For Sierra, suffixes A-J are garden-facing, K faces both directions, and L onward are street-facing (marketed as skyline).",
            "Sierra facing is effect-coded as skyline versus garden plus a both-facing deviation; frontage is neutral for the other buildings.",
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
        f"Fitting {len(data)} unit-{label} observations from {data.unit_key.nunique()} units "
        f"over {len(periods)} {label}s after excluding confirmed Blueground units."
    )
    inference = fit_model(
        data, periods, args.frequency, args.draws, args.tune, args.chains
    )
    save_outputs(inference, data, periods, args.frequency, output)
    print(f"Saved model outputs to {output}")


if __name__ == "__main__":
    main()
