"""Hierarchical log-rent model as a JAX log density (NumPyro for transforms).

log rent_i - offset = alpha + x_i . beta                 named feature terms
                    + trend[month_i] + season[cal_i]     market time
                    + b[building_i] + u[unit_i]          group effects
                    + eps_i,  eps ~ StudentT(nu, 0, sigma)

Group effects and the monthly random walk are written centered; any of them
can be non-centered through `ModelConfig.noncentered` (NumPyro
LocScaleReparam). The design is set by `ModelConfig`; the feature set is
chosen separately (features.py).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import jax.numpy as jnp
import numpy as np
import numpyro
import numpyro.distributions as dist
import pandas as pd

from .features import Features


@dataclass(frozen=True)
class ModelConfig:
    name: str = "m0-base"
    beta_sd: float = 0.5
    trend_scale_sd: float = 0.05
    season_scale_sd: float = 0.05
    building_scale_sd: float = 0.5
    unit_scale_sd: float = 0.2
    noise_scale_sd: float = 0.2
    # Sites to non-center. With ~2.4 rows per unit, ~42 per building and
    # ~250 per month the data dominate, so centered is the default.
    noncentered: tuple = ()

    def to_dict(self):
        return asdict(self)


@dataclass
class Arrays:
    y: np.ndarray
    x: np.ndarray
    month: np.ndarray
    calendar: np.ndarray
    building: np.ndarray
    unit: np.ndarray  # -1 for units without training rows


@dataclass
class Prepared:
    features: Features
    offset: float
    periods: pd.DatetimeIndex
    buildings: np.ndarray
    units: np.ndarray
    train: Arrays
    test: Arrays
    test_audit_id: np.ndarray

    @property
    def sizes(self):
        return {
            "rows": len(self.train.y),
            "features": self.train.x.shape[1],
            "months": len(self.periods),
            "buildings": len(self.buildings),
            "units": len(self.units),
            "heldout_rows": len(self.test.y),
        }


def prepare(frame: pd.DataFrame, heldout: np.ndarray, features: Features) -> Prepared:
    train = ~heldout
    periods = pd.date_range(frame.period.min(), frame.period.max(), freq="MS")
    buildings = np.sort(frame.building[train].unique())
    units = np.sort(frame.unit_id[train].unique())
    offset = float(frame.log_rent[train].mean())

    def arrays(mask):
        sub = frame[mask]
        month = (
            (sub.period.dt.year - periods[0].year) * 12
            + sub.period.dt.month
            - periods[0].month
        )
        building = pd.Index(buildings).get_indexer(sub.building)
        if (building < 0).any():
            raise ValueError("Held-out row in a building without training rows")
        return Arrays(
            y=(sub.log_rent.to_numpy() - offset),
            x=features.values[mask],
            month=month.to_numpy().astype(np.int32),
            calendar=(sub.period.dt.month.to_numpy() - 1).astype(np.int32),
            building=building.astype(np.int32),
            unit=pd.Index(units).get_indexer(sub.unit_id).astype(np.int32),
        )

    return Prepared(
        features=features,
        offset=offset,
        periods=periods,
        buildings=buildings,
        units=units,
        train=arrays(train),
        test=arrays(heldout),
        test_audit_id=frame.audit_id[heldout].to_numpy(),
    )


def linear_predictor(p, a: Arrays, include_unit=True):
    """Mean log rent without offset, from constrained site values."""
    e = effects(p)
    mu = (
        e["alpha"]
        + a.x @ e["beta"]
        + e["trend"][a.month]
        + e["season"][a.calendar]
        + e["building"][a.building]
    )
    if include_unit:
        mu = mu + jnp.where(a.unit >= 0, e["unit"][jnp.maximum(a.unit, 0)], 0.0)
    return mu


def effects(p):
    """Named effect vectors (log scale) from constrained site values."""
    season = p["season_raw"] - p["season_raw"].mean()
    return {
        "alpha": p["alpha"],
        "beta": p["beta"],
        "trend": jnp.concatenate([jnp.zeros(1), jnp.cumsum(p["trend_step"])]),
        "season": season,
        "building": p["building"],
        "unit": p["unit"],
        "sigma": p["sigma"],
        "nu": p["nu"],
        "unit_scale": p["unit_scale"],
        "building_scale": p["building_scale"],
        "trend_scale": p["trend_scale"],
        "season_scale": p["season_scale"],
    }


def build_model(prep: Prepared, config: ModelConfig):
    from numpyro.infer.reparam import LocScaleReparam

    a = prep.train
    n_months = len(prep.periods)
    y = jnp.asarray(a.y)
    arrays = Arrays(
        *(
            jnp.asarray(getattr(a, f))
            for f in ("y", "x", "month", "calendar", "building", "unit")
        )
    )
    beta_sd = config.beta_sd * jnp.asarray(prep.features.prior_scale)

    def model():
        p = {
            "alpha": numpyro.sample("alpha", dist.Normal(0.0, 1.0)),
            "beta": numpyro.sample("beta", dist.Normal(0.0, beta_sd)),
            "trend_scale": numpyro.sample(
                "trend_scale", dist.HalfNormal(config.trend_scale_sd)
            ),
            "season_scale": numpyro.sample(
                "season_scale", dist.HalfNormal(config.season_scale_sd)
            ),
            "building_scale": numpyro.sample(
                "building_scale", dist.HalfNormal(config.building_scale_sd)
            ),
            "unit_scale": numpyro.sample(
                "unit_scale", dist.HalfNormal(config.unit_scale_sd)
            ),
            "sigma": numpyro.sample("sigma", dist.HalfNormal(config.noise_scale_sd)),
            "nu": numpyro.sample("nu", dist.Gamma(2.0, 0.1)),  # Juarez & Steel (2010)
        }
        p["trend_step"] = numpyro.sample(
            "trend_step", dist.Normal(0.0, p["trend_scale"]).expand([n_months - 1])
        )
        p["season_raw"] = numpyro.sample(
            "season_raw", dist.Normal(0.0, p["season_scale"]).expand([12])
        )
        p["building"] = numpyro.sample(
            "building",
            dist.Normal(0.0, p["building_scale"]).expand([len(prep.buildings)]),
        )
        p["unit"] = numpyro.sample(
            "unit", dist.Normal(0.0, p["unit_scale"]).expand([len(prep.units)])
        )
        mu = linear_predictor(p, arrays)
        numpyro.sample("y", dist.StudentT(p["nu"], mu, p["sigma"]), obs=y)

    reparam = {site: LocScaleReparam(centered=0) for site in config.noncentered}
    return numpyro.handlers.reparam(model, config=reparam) if reparam else model
