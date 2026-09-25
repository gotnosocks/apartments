"""Hierarchical log-rent model as a JAX log density (NumPyro for transforms).

log rent_i - offset = alpha + x_i . beta                 named feature terms
                    + trend[month_i] + season[cal_i]     market time
                    + b[building_i] + u[unit_i]          group effects
                    + eps_i,  eps ~ StudentT(nu, 0, sigma)

Group effects and the monthly random walk are written centered; any of them
can be non-centered through `ModelConfig.noncentered` (NumPyro
LocScaleReparam). The design is set by `ModelConfig`; the feature set is
chosen separately (features.py).

This is the one definition of every design. NUTS (nuts.py) samples it
directly; the deprecated Gibbs sampler (gibbs.py, kept only to reproduce old
run records) works on it through `gibbs.site_values`. Both are scored by the
same code (collect.py, loo.py, variance.py).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import jax.numpy as jnp
import numpy as np
import numpyro
import numpyro.distributions as dist
import pandas as pd
from numpyro.distributions import constraints

from .features import Features


@dataclass(frozen=True)
class ModelConfig:
    name: str = "m0-base"
    # The base terms. The model ladder's simplest designs drop some; a dropped
    # term is a zero effect with scale 0 (see `constants`), so every consumer
    # sees the same effect tree. Gibbs designs have all five.
    trend: bool = True
    season: bool = True
    features: bool = True
    buildings: bool = True
    units: bool = True
    # One shared linear drift of log rent per year, centred on the mean
    # training month and folded into the trend effect (the ladder's L1).
    market_drift: bool = False
    market_drift_sd: float = 0.1
    beta_sd: float = 0.5
    trend_scale_sd: float = 0.05
    season_scale_sd: float = 0.05
    building_scale_sd: float = 0.5
    unit_scale_sd: float = 0.2
    noise_scale_sd: float = 0.2
    # Sites to non-center. With ~2.4 rows per unit, ~42 per building and
    # ~250 per month the data dominate, so centered is the default.
    noncentered: tuple = ()
    # Sampling coordinates for gradient samplers. Like `noncentered` they change
    # how a sampler moves, not the model (each is a unit-Jacobian linear map,
    # and the original sites stay as deterministic sites):
    # - "trend_levels": sample the market's absolute knot levels (intercept
    #   plus trend) instead of the trend's steps: each quarter's rows inform
    #   that quarter's level directly, where the steps are strongly
    #   correlated. Sampling the trend's levels relative to the intercept
    #   instead leaves a ridge (intercept up, every level down) that NUTS
    #   cannot cross (c1ad7d0: L2 intercept R-hat 1.83).
    # - "season_zerosum": sample the centred season (ZeroSumNormal) instead of
    #   12 raw values whose mean the data never see; that mean's prior depends
    #   on the season scale and makes a funnel (bfcf2cb: L3 season_scale ESS
    #   263). Integrating the unseen mean out leaves every other posterior
    #   exactly unchanged.
    # - "building_zerosum": sample the building levels (and per-building
    #   bedroom slopes) as their mean plus zero-sum deviations. i.i.d. normal
    #   values split exactly into those two independent parts. The mean is a
    #   single global number, so a dense mass matrix can follow the ridge
    #   "market up, every building down" that the prior alone pins
    #   (1b0dca6: L5 Chelsea Tower level R-hat 1.04, ESS 42).
    # - "unit_totals": sample each unit's own effect plus its mean features
    #   times beta, less its building's mean features times beta when the
    #   building is centred too (hierarchical centering, level by level), so
    #   apartment attributes (size, baths, floor) do not trade off against the
    #   unit effects (41e8fe0: m0q half-baths R-hat 1.017). Including the
    #   building effect in the unit total instead puts the market-level ridge
    #   through every unit (41e8fe0: m0q Chelsea Tower R-hat 1.13).
    # - "unit_partial": partially non-centre each unit effect by its number of
    #   rows, n / (n + UNIT_KAPPA) (LocScaleReparam with per-unit weights).
    #   Units listed once are half prior, half data; fully centred, their
    #   effects and the unit scale make a funnel (ed9a8a3: m0q unit_scale
    #   R-hat 1.017, ESS 240).
    # - "building_totals": the same one level up. Sample each building's
    #   total (its effect plus its mean features times beta), split into a
    #   global mean plus zero-sum deviations; the building prior is imposed on
    #   total - features. Building attributes (doorman, elevator) then do not
    #   trade off against the building levels (f4ffd1a: L5 doorman R-hat 1.026).
    coordinates: tuple = ()
    # Per-building random walk over KNOT_MONTHS knots (anchored at 0 in the
    # first month), interpolated linearly between knots.
    building_walk: bool = False
    walk_scale_sd: float = 0.1
    # Bedroom-group market curves: random-walk deviations of the month trend
    # for studios, 2- and 3+-bedrooms, relative to 1-bedrooms.
    bedroom_time: bool = False
    bedroom_time_scale_sd: float = 0.02
    # Per-building bedroom slope: each building's premium per bedroom around
    # the global bedroom coefficients.
    bedroom_slope: bool = False
    bedroom_slope_scale_sd: float = 0.1
    # Per-building random slopes on these feature columns (by name), each
    # with its own HalfNormal(feature_slope_scale_sd) scale.
    feature_slopes: tuple = ()
    feature_slope_scale_sd: float = 0.1
    # Knot spacing (months) of the market trend and bedroom-group curves:
    # random walks over knots, linearly interpolated; 1 = one value per month.
    trend_knot_months: int = 1
    bedroom_time_knot_months: int = 1
    # Student-t degrees of freedom: None = estimated (Gamma(2, 0.1) prior),
    # a number = fixed (the promoted model fixes 5).
    nu_fixed: float | None = None
    # Student-t unit effects (heavy tails let a few units sit far from their
    # building without bending its slopes). unit_nu_fixed None = estimated.
    unit_t: bool = False
    unit_nu_fixed: float | None = None
    # Per-unit linear drift in log rent per year, centred on the unit's mean
    # training date: drift_j ~ N(0, unit_drift_scale^2).
    unit_drift: bool = False
    unit_drift_scale_sd: float = 0.05

    def to_dict(self):
        return asdict(self)


KNOT_MONTHS = 6
BEDROOM_GROUPS = ("studio", "one_bedroom", "two_bedroom", "three_plus")
TIME_GROUPS = (
    0,
    2,
    3,
)  # bedroom groups with their own market curve (1-bedroom is the reference)


@dataclass
class Arrays:
    y: np.ndarray
    x: np.ndarray
    month: np.ndarray
    calendar: np.ndarray
    building: np.ndarray
    unit: np.ndarray  # -1 for units without training rows
    knot: np.ndarray  # walk knot at or before the row's month
    knot_frac: np.ndarray  # linear interpolation weight on the next knot
    bed_group: np.ndarray  # index into BEDROOM_GROUPS
    beds_centered: np.ndarray  # bedrooms (capped at 4) minus 1
    unit_time: np.ndarray  # years from the unit's mean training date (unit drift)

    FIELDS = (
        "y",
        "x",
        "month",
        "calendar",
        "building",
        "unit",
        "knot",
        "knot_frac",
        "bed_group",
        "beds_centered",
        "unit_time",
    )

    def map(self, fn):
        return Arrays(*(fn(getattr(self, f)) for f in self.FIELDS))


def n_knots(n_months: int, spacing: int = KNOT_MONTHS) -> int:
    return int(np.ceil((n_months - 1) / spacing)) + 1


def knot_basis(n_months: int, spacing: int) -> np.ndarray:
    """(months, knots - 1) linear interpolation onto knots 1.. (knot 0 = 0)."""
    k = n_knots(n_months, spacing)
    pos = np.arange(n_months) / spacing
    lo = np.floor(pos).astype(int)
    frac = pos - lo
    basis = np.zeros((n_months, k))
    basis[np.arange(n_months), lo] = 1 - frac
    hi = np.minimum(lo + 1, k - 1)
    basis[np.arange(n_months), hi] += np.where(hi > lo, frac, 0.0)
    return basis[:, 1:]


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
    unit_mean_month: np.ndarray | None = None  # (units,) mean training month

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
    prep = Prepared(
        features=features,
        offset=float(frame.log_rent[train].mean()),
        periods=pd.date_range(frame.period.min(), frame.period.max(), freq="MS"),
        buildings=np.sort(frame.building[train].unique()),
        units=np.sort(frame.unit_id[train].unique()),
        train=None,
        test=None,
        test_audit_id=frame.audit_id[heldout].to_numpy(),
    )
    tr = frame[train]
    months = (
        (tr.period.dt.year - prep.periods[0].year) * 12
        + tr.period.dt.month
        - prep.periods[0].month
    )
    prep.unit_mean_month = (
        months.groupby(tr.unit_id).mean().reindex(prep.units).to_numpy().astype(float)
    )
    prep.train = row_arrays(prep, frame, train)
    prep.test = row_arrays(prep, frame, heldout)
    return prep


def row_arrays(prep: Prepared, frame: pd.DataFrame, mask: np.ndarray) -> Arrays:
    """Model arrays for any rows of `frame`, encoded as in the fit `prep`."""
    sub = frame[mask]
    periods = prep.periods
    month = (
        (sub.period.dt.year - periods[0].year) * 12
        + sub.period.dt.month
        - periods[0].month
    )
    building = pd.Index(prep.buildings).get_indexer(sub.building)
    if (building < 0).any():
        raise ValueError("Row in a building without training rows")
    month = month.to_numpy().astype(np.int32)
    return Arrays(
        y=(sub.log_rent.to_numpy() - prep.offset),
        x=prep.features.values[mask],
        month=month,
        calendar=(sub.period.dt.month.to_numpy() - 1).astype(np.int32),
        building=building.astype(np.int32),
        unit=pd.Index(prep.units).get_indexer(sub.unit_id).astype(np.int32),
        knot=(month // KNOT_MONTHS).astype(np.int32),
        knot_frac=(month % KNOT_MONTHS) / KNOT_MONTHS,
        bed_group=np.minimum(sub.bedrooms.round().clip(0, 3), 3)
        .to_numpy()
        .astype(np.int32),
        beds_centered=sub.bedrooms.round().clip(0, 4).to_numpy() - 1.0,
        unit_time=_unit_time(prep, sub, month),
    )


def _unit_time(prep: Prepared, sub: pd.DataFrame, month: np.ndarray) -> np.ndarray:
    """Years from the unit's mean training month; for a unit with no training
    rows, from the mean month of its own rows here (dates only, no prices)."""
    unit = pd.Index(prep.units).get_indexer(sub.unit_id)
    center = np.where(unit >= 0, prep.unit_mean_month[np.maximum(unit, 0)], np.nan)
    own = (
        pd.Series(month, index=sub.index)
        .groupby(sub.unit_id.to_numpy())
        .transform("mean")
        .to_numpy()
    )
    center = np.where(np.isnan(center), own, center)
    return (month - center) / 12.0


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
    if "walk_step" in p:
        w = e["walk"]
        mu = (
            mu
            + (1 - a.knot_frac) * w[a.building, a.knot]
            + a.knot_frac * w[a.building, a.knot + 1]
        )
    if "bedroom_time_step" in p:
        mu = mu + e["bedroom_time"][a.bed_group, a.month]
    if "bedroom_slope" in p:
        mu = mu + e["bedroom_slope"][a.building] * a.beds_centered
    if "fslope" in p:
        mu = mu + jnp.sum(p["fslope"][a.building] * a.x[:, p["fslope_index"]], axis=1)
    if include_unit:
        mu = mu + jnp.where(a.unit >= 0, e["unit"][jnp.maximum(a.unit, 0)], 0.0)
        if "unit_drift" in p:
            mu = mu + jnp.where(
                a.unit >= 0, p["unit_drift"][jnp.maximum(a.unit, 0)] * a.unit_time, 0.0
            )
    return mu


def effects(p):
    """Named effect vectors (log scale) from constrained site values."""
    season = p["season_raw"] - p["season_raw"].mean()
    trend = (
        p["trend_basis"] @ jnp.cumsum(p["trend_step"])
        if "trend_basis" in p
        else jnp.concatenate([jnp.zeros(1), jnp.cumsum(p["trend_step"])])
    )
    if "market_drift" in p:
        months = jnp.arange(trend.shape[0])
        trend = trend + p["market_drift"] * (months - p["month_center"]) / 12.0
    return {
        "alpha": p["alpha"],
        "beta": p["beta"],
        "trend": trend,
        "market_drift": p.get("market_drift", jnp.zeros(())),
        "season": season,
        "building": p["building"],
        "unit": p["unit"],
        "sigma": p["sigma"],
        "nu": p["nu"],
        "unit_scale": p["unit_scale"],
        "unit_nu": p.get("unit_nu", jnp.zeros(())),  # 0 = Gaussian unit effects
        "unit_drift": p.get("unit_drift", jnp.zeros(1)),
        "unit_drift_scale": p.get("unit_drift_scale", jnp.zeros(())),
        "building_scale": p["building_scale"],
        "trend_scale": p["trend_scale"],
        "season_scale": p["season_scale"],
        # Building walks (knot values; knot 0 is fixed at 0). Placeholders
        # when the design has no walk keep the effect tree the same shape.
        "walk": (
            jnp.concatenate(
                [
                    jnp.zeros((p["walk_step"].shape[0], 1)),
                    jnp.cumsum(p["walk_step"], axis=1),
                ],
                axis=1,
            )
            if "walk_step" in p
            else jnp.zeros((1, 1))
        ),
        "walk_scale": p.get("walk_scale", jnp.zeros(())),
        # Market-curve deviation per bedroom group (row 1 = 1-bedroom = 0).
        "bedroom_time": _bedroom_time(p),
        "bedroom_time_scale": p.get("bedroom_time_scale", jnp.zeros(())),
        "bedroom_slope": p.get("bedroom_slope", jnp.zeros(1)),
        "bedroom_slope_scale": p.get("bedroom_slope_scale", jnp.zeros(())),
        "fslope": p.get("fslope", jnp.zeros((1, 1))),
        "fslope_scales": p.get("fslope_scales", jnp.zeros(1)),
    }


def _bedroom_time(p):
    if "bedroom_time_step" not in p:
        return jnp.zeros((len(BEDROOM_GROUPS), 1))
    steps = p["bedroom_time_step"]  # (len(TIME_GROUPS), knots - 1)
    if "bedroom_time_basis" in p:
        curves = (
            jnp.cumsum(steps, axis=1) @ p["bedroom_time_basis"].T
        )  # (groups, months)
    else:
        curves = jnp.concatenate(
            [jnp.zeros((steps.shape[0], 1)), jnp.cumsum(steps, axis=1)], axis=1
        )
    out = jnp.zeros((len(BEDROOM_GROUPS), curves.shape[1]))
    return out.at[jnp.asarray(TIME_GROUPS)].set(curves)


def constants(prep: Prepared, config: ModelConfig) -> dict:
    """Site values that are not sampled: bases, indices, and zero effects
    (scale 0) for the base terms the design drops."""
    n_months = len(prep.periods)
    if not config.buildings and (
        config.building_walk or config.bedroom_slope or config.feature_slopes
    ):
        raise ValueError(f"{config.name}: building terms need building levels")
    if not config.units and (config.unit_t or config.unit_drift):
        raise ValueError(f"{config.name}: unit terms need unit levels")
    trend_basis = jnp.asarray(knot_basis(n_months, config.trend_knot_months))
    out = {"trend_basis": trend_basis}
    if config.market_drift:
        out["month_center"] = jnp.asarray(float(np.mean(prep.train.month)))
    if config.bedroom_time:
        out["bedroom_time_basis"] = jnp.asarray(
            knot_basis(n_months, config.bedroom_time_knot_months)
        )
    if config.feature_slopes:
        out["fslope_index"] = jnp.asarray(
            [prep.features.names.index(n) for n in config.feature_slopes],
            dtype=jnp.int32,
        )
    if config.nu_fixed is not None:
        out["nu"] = jnp.asarray(config.nu_fixed)
    if config.unit_t and config.unit_nu_fixed is not None:
        out["unit_nu"] = jnp.asarray(config.unit_nu_fixed)
    if "unit_totals" in config.coordinates:
        # A unit's building, for centring units within buildings.
        ub = np.full(len(prep.units), -1)
        ub[prep.train.unit] = prep.train.building
        if (ub < 0).any() or (ub[prep.train.unit] != prep.train.building).any():
            raise ValueError("unit_totals needs every unit in exactly one building")
        out["unit_building"] = jnp.asarray(ub, dtype=jnp.int32)
        out["unit_xbar"] = jnp.asarray(
            _group_means(prep.train.x, prep.train.unit, len(prep.units))
        )
    if "unit_partial" in config.coordinates:
        rows = np.bincount(np.asarray(prep.train.unit), minlength=len(prep.units))
        out["unit_centering"] = jnp.asarray(rows / (rows + UNIT_KAPPA))
    if "building_totals" in config.coordinates:
        out["building_xbar"] = jnp.asarray(
            _group_means(prep.train.x, prep.train.building, len(prep.buildings))
        )
    zero = jnp.zeros(())
    if not config.features:
        out["beta"] = jnp.zeros(len(prep.features.names))
    if not config.trend:
        out |= {"trend_scale": zero, "trend_step": jnp.zeros(trend_basis.shape[1])}
    if not config.season:
        out |= {"season_scale": zero, "season_raw": jnp.zeros(12)}
    if not config.buildings:
        out |= {"building_scale": zero, "building": jnp.zeros(len(prep.buildings))}
    if not config.units:
        out |= {"unit_scale": zero, "unit": jnp.zeros(len(prep.units))}
    return out


# (noise sd / unit sd)^2 from the fitted m0q (0.066 / 0.086)^2: a unit with n
# rows is centred by n / (n + UNIT_KAPPA) under "unit_partial". Any fixed
# value gives the same model; it only sets NUTS's coordinates.
UNIT_KAPPA = 0.6


def _group_means(x, group, n):
    """Mean of the rows of x in each of n groups (training rows)."""
    x = np.asarray(x, dtype=float)
    sums = np.zeros((n, x.shape[1]))
    np.add.at(sums, np.asarray(group), x)
    counts = np.bincount(np.asarray(group), minlength=n)
    return sums / np.maximum(counts, 1)[:, None]


def _centred_totals(site: str, loc, scale, n: int):
    """Effects e ~ i.i.d. N(0, scale) sampled through their totals t = loc + e,
    written as a global mean plus zero-sum deviations (flat coordinates) with
    the prior imposed on t - loc. Returns e as a deterministic site `site`."""
    mean = numpyro.sample(
        f"{site}_total_mean", dist.ImproperUniform(constraints.real, (), ())
    )
    dev = numpyro.sample(
        f"{site}_total_dev", dist.ImproperUniform(constraints.zero_sum(1), (), (n,))
    )
    effect = mean + dev - loc
    numpyro.factor(f"{site}_prior", dist.Normal(0.0, scale).log_prob(effect).sum())
    return numpyro.deterministic(site, effect)


def _mean_plus_zero_sum(site: str, scale, n: int):
    """n i.i.d. N(0, scale) values sampled as their mean (N(0, scale / sqrt(n)))
    plus zero-sum deviations (ZeroSumNormal(scale)): the same distribution,
    split into its two independent parts. Returns the values as a
    deterministic site named `site`."""
    mean = numpyro.sample(f"{site}_mean", dist.Normal(0.0, scale / jnp.sqrt(n)))
    dev = numpyro.sample(f"{site}_dev", dist.ZeroSumNormal(scale, (n,)))
    return numpyro.deterministic(site, mean + dev)


def build_model(prep: Prepared, config: ModelConfig):
    from numpyro.infer.reparam import LocScaleReparam

    a = prep.train
    n_months = len(prep.periods)
    y = jnp.asarray(a.y)
    arrays = a.map(jnp.asarray)
    beta_sd = config.beta_sd * jnp.asarray(prep.features.prior_scale)
    fixed = constants(prep, config)
    trend_basis = fixed["trend_basis"]

    def model():
        p = dict(fixed)
        p["alpha"] = numpyro.sample("alpha", dist.Normal(0.0, 1.0))
        if config.features:
            p["beta"] = numpyro.sample("beta", dist.Normal(0.0, beta_sd))
        if config.trend:
            p["trend_scale"] = numpyro.sample(
                "trend_scale", dist.HalfNormal(config.trend_scale_sd)
            )
        if config.season:
            p["season_scale"] = numpyro.sample(
                "season_scale", dist.HalfNormal(config.season_scale_sd)
            )
        if config.buildings:
            p["building_scale"] = numpyro.sample(
                "building_scale", dist.HalfNormal(config.building_scale_sd)
            )
        if config.units:
            p["unit_scale"] = numpyro.sample(
                "unit_scale", dist.HalfNormal(config.unit_scale_sd)
            )
        p["sigma"] = numpyro.sample("sigma", dist.HalfNormal(config.noise_scale_sd))
        p["nu"] = (
            jnp.asarray(config.nu_fixed)
            if config.nu_fixed is not None
            else numpyro.sample("nu", dist.Gamma(2.0, 0.1))  # Juarez & Steel (2010)
        )
        if config.market_drift:
            p["market_drift"] = numpyro.sample(
                "market_drift", dist.Normal(0.0, config.market_drift_sd)
            )
        if config.trend and "trend_levels" in config.coordinates:
            # alpha is the anchor knot's level; the walk prior is on the steps
            # between absolute levels (a unit-Jacobian shift of the steps).
            absolute = numpyro.sample(
                "trend_absolute",
                dist.ImproperUniform(constraints.real, (), (trend_basis.shape[1],)),
            )
            steps = jnp.diff(absolute, prepend=jnp.reshape(p["alpha"], (1,)))
            numpyro.factor(
                "trend_walk", dist.Normal(0.0, p["trend_scale"]).log_prob(steps).sum()
            )
            p["trend_step"] = numpyro.deterministic("trend_step", steps)
        elif config.trend:
            p["trend_step"] = numpyro.sample(
                "trend_step",
                dist.Normal(0.0, p["trend_scale"]).expand([trend_basis.shape[1]]),
            )
        if config.season and "season_zerosum" in config.coordinates:
            p["season_raw"] = numpyro.deterministic(
                "season_raw",
                numpyro.sample("season", dist.ZeroSumNormal(p["season_scale"], (12,))),
            )
        elif config.season:
            p["season_raw"] = numpyro.sample(
                "season_raw", dist.Normal(0.0, p["season_scale"]).expand([12])
            )
        if config.buildings and "building_totals" in config.coordinates:
            p["building"] = _centred_totals(
                "building",
                fixed["building_xbar"] @ p["beta"],
                p["building_scale"],
                len(prep.buildings),
            )
        elif config.buildings and "building_zerosum" in config.coordinates:
            p["building"] = _mean_plus_zero_sum(
                "building", p["building_scale"], len(prep.buildings)
            )
        elif config.buildings:
            p["building"] = numpyro.sample(
                "building",
                dist.Normal(0.0, p["building_scale"]).expand([len(prep.buildings)]),
            )
        if config.units and config.unit_t:
            p["unit_nu"] = (
                jnp.asarray(config.unit_nu_fixed)
                if config.unit_nu_fixed is not None
                else numpyro.sample("unit_nu", dist.Gamma(2.0, 0.1))
            )
        if config.units:
            n_units = len(prep.units)
            loc = 0.0
            if "unit_totals" in config.coordinates:
                # Centre each unit on its own mean features, less its building's
                # when the building is centred on those (building_totals).
                xbar = fixed["unit_xbar"]
                if "building_totals" in config.coordinates and config.buildings:
                    xbar = xbar - fixed["building_xbar"][fixed["unit_building"]]
                loc = xbar @ p["beta"]
            prior = (
                dist.StudentT(p["unit_nu"], loc, p["unit_scale"])
                if config.unit_t
                else dist.Normal(loc, p["unit_scale"])
            )
            if "unit_totals" in config.coordinates:
                total = numpyro.sample("unit_total", prior.expand([n_units]))
                p["unit"] = numpyro.deterministic("unit", total - loc)
            else:
                p["unit"] = numpyro.sample("unit", prior.expand([n_units]))
        if config.unit_drift:
            p["unit_drift_scale"] = numpyro.sample(
                "unit_drift_scale", dist.HalfNormal(config.unit_drift_scale_sd)
            )
            p["unit_drift"] = numpyro.sample(
                "unit_drift",
                dist.Normal(0.0, p["unit_drift_scale"]).expand([len(prep.units)]),
            )
        if config.building_walk:
            p["walk_scale"] = numpyro.sample(
                "walk_scale", dist.HalfNormal(config.walk_scale_sd)
            )
            p["walk_step"] = numpyro.sample(
                "walk_step",
                dist.Normal(0.0, p["walk_scale"]).expand(
                    [len(prep.buildings), n_knots(n_months) - 1]
                ),
            )
        if config.bedroom_time:
            p["bedroom_time_scale"] = numpyro.sample(
                "bedroom_time_scale", dist.HalfNormal(config.bedroom_time_scale_sd)
            )
            p["bedroom_time_step"] = numpyro.sample(
                "bedroom_time_step",
                dist.Normal(0.0, p["bedroom_time_scale"]).expand(
                    [len(TIME_GROUPS), p["bedroom_time_basis"].shape[1]]
                ),
            )
        if config.bedroom_slope:
            p["bedroom_slope_scale"] = numpyro.sample(
                "bedroom_slope_scale", dist.HalfNormal(config.bedroom_slope_scale_sd)
            )
            if "building_zerosum" in config.coordinates:
                p["bedroom_slope"] = _mean_plus_zero_sum(
                    "bedroom_slope", p["bedroom_slope_scale"], len(prep.buildings)
                )
            else:
                p["bedroom_slope"] = numpyro.sample(
                    "bedroom_slope",
                    dist.Normal(0.0, p["bedroom_slope_scale"]).expand(
                        [len(prep.buildings)]
                    ),
                )
        if config.feature_slopes:
            p["fslope_scales"] = numpyro.sample(
                "fslope_scales",
                dist.HalfNormal(config.feature_slope_scale_sd).expand(
                    [len(config.feature_slopes)]
                ),
            )
            p["fslope"] = numpyro.sample(
                "fslope",
                dist.Normal(0.0, p["fslope_scales"]).expand(
                    [len(prep.buildings), len(config.feature_slopes)]
                ),
            )
        mu = linear_predictor(p, arrays)
        numpyro.sample("y", dist.StudentT(p["nu"], mu, p["sigma"]), obs=y)

    reparam = {site: LocScaleReparam(centered=0) for site in config.noncentered}
    if config.units and "unit_partial" in config.coordinates:
        site = "unit_total" if "unit_totals" in config.coordinates else "unit"
        reparam[site] = LocScaleReparam(
            centered=fixed["unit_centering"],
            shape_params=("df",) if config.unit_t else (),
        )
    return numpyro.handlers.reparam(model, config=reparam) if reparam else model


# Named model designs. Add new entries rather than changing existing ones, so
# earlier leaderboard rows stay reproducible from their commits.
MODELS = {
    "m0-base": ModelConfig(name="m0-base"),
    "m1-walk": ModelConfig(name="m1-walk", building_walk=True),
    "m2-walk-bedtime": ModelConfig(
        name="m2-walk-bedtime", building_walk=True, bedroom_time=True
    ),
    "m3-walk-bedslope": ModelConfig(
        name="m3-walk-bedslope", building_walk=True, bedroom_slope=True
    ),
    "m5-quarterly": ModelConfig(
        name="m5-quarterly",
        building_walk=True,
        bedroom_time=True,
        bedroom_slope=True,
        trend_knot_months=3,
        bedroom_time_knot_months=3,
    ),
    # Ablations of m5: which piece earns the gain over the promoted model?
    "m5-nu5": ModelConfig(
        name="m5-nu5",
        building_walk=True,
        bedroom_time=True,
        bedroom_slope=True,
        trend_knot_months=3,
        bedroom_time_knot_months=3,
        nu_fixed=5.0,
    ),
    "m5-noslope": ModelConfig(
        name="m5-noslope",
        building_walk=True,
        bedroom_time=True,
        trend_knot_months=3,
        bedroom_time_knot_months=3,
    ),
    "m5-nocurves": ModelConfig(
        name="m5-nocurves",
        building_walk=True,
        bedroom_slope=True,
        trend_knot_months=3,
    ),
    # Per-building slopes on size and bathrooms, on top of m5.
    "m6-slopes": ModelConfig(
        name="m6-slopes",
        building_walk=True,
        bedroom_time=True,
        bedroom_slope=True,
        trend_knot_months=3,
        bedroom_time_knot_months=3,
        feature_slopes=("log_sqft_vs_bedroom_median", "bathrooms=2", "bathrooms=3"),
    ),
    # m6 with Student-t unit effects (unit-level degrees of freedom estimated).
    "m7-tunits": ModelConfig(
        name="m7-tunits",
        building_walk=True,
        bedroom_time=True,
        bedroom_slope=True,
        trend_knot_months=3,
        bedroom_time_knot_months=3,
        feature_slopes=("log_sqft_vs_bedroom_median", "bathrooms=2", "bathrooms=3"),
        unit_t=True,
    ),
    # m7 plus a per-unit linear drift.
    "m8-drift": ModelConfig(
        name="m8-drift",
        building_walk=True,
        bedroom_time=True,
        bedroom_slope=True,
        trend_knot_months=3,
        bedroom_time_knot_months=3,
        feature_slopes=("log_sqft_vs_bedroom_median", "bathrooms=2", "bathrooms=3"),
        unit_t=True,
        unit_drift=True,
    ),
    "m4-walk-bedtime-bedslope": ModelConfig(
        name="m4-walk-bedtime-bedslope",
        building_walk=True,
        bedroom_time=True,
        bedroom_slope=True,
    ),
    # Quarterly market trend (68 knots instead of 201): the global block is
    # about half the size, and its solve dominates an iteration on the
    # RTX 2060; projection loses ~0.1% more than the monthly trend.
    "m0q": ModelConfig(name="m0q", trend_knot_months=3),
    "m1q": ModelConfig(name="m1q", building_walk=True, trend_knot_months=3),
    # m6-m8 without the bedroom-group market curves: the curves add ~200
    # global columns (3 groups x 68 quarterly knots) and the global solve
    # grows with the square of its size; projection loses only ~120-170
    # nats without them. Candidates for the sub-10-minute frontier on thelio.
    "m6-nocurves": ModelConfig(
        name="m6-nocurves",
        building_walk=True,
        bedroom_slope=True,
        trend_knot_months=3,
        feature_slopes=("log_sqft_vs_bedroom_median", "bathrooms=2", "bathrooms=3"),
    ),
    "m7-nocurves": ModelConfig(
        name="m7-nocurves",
        building_walk=True,
        bedroom_slope=True,
        trend_knot_months=3,
        feature_slopes=("log_sqft_vs_bedroom_median", "bathrooms=2", "bathrooms=3"),
        unit_t=True,
    ),
    "m8-nocurves": ModelConfig(
        name="m8-nocurves",
        building_walk=True,
        bedroom_slope=True,
        trend_knot_months=3,
        feature_slopes=("log_sqft_vs_bedroom_median", "bathrooms=2", "bathrooms=3"),
        unit_t=True,
        unit_drift=True,
    ),
}

# The model ladder: the simplest design first, one term more per step, up to
# the sub-15-minute candidates. Fit by NUTS (the deprecated Gibbs sampler
# needs every base term and is not used for new work).
_BARE = {
    "trend": False,
    "season": False,
    "features": False,
    "buildings": False,
    "units": False,
    "trend_knot_months": 3,
}
MODELS |= {
    "L0-mean": ModelConfig(name="L0-mean", **_BARE),
    "L1-drift": ModelConfig(name="L1-drift", **_BARE | {"market_drift": True}),
    "L2-trend": ModelConfig(name="L2-trend", **_BARE | {"trend": True}),
    "L3-season": ModelConfig(
        name="L3-season", **_BARE | {"trend": True, "season": True}
    ),
    "L4-features": ModelConfig(
        name="L4-features",
        **_BARE | {"trend": True, "season": True, "features": True},
    ),
    "L5-building": ModelConfig(
        name="L5-building",
        **_BARE | {"trend": True, "season": True, "features": True, "buildings": True},
    ),
}
LADDER = (
    "L0-mean",  # intercept only, Student-t noise
    "L1-drift",  # + one shared linear drift per year
    "L2-trend",  # a quarterly market trend instead (it contains the drift)
    "L3-season",  # + calendar season
    "L4-features",  # + the listing features
    "L5-building",  # + building levels
    "m0q",  # + unit levels
    "m1q",  # + each building's half-year random walk
    "m5-nocurves",  # + each building's bedroom slope
    "m6-nocurves",  # + each building's size and bathroom slopes
    "m7-nocurves",  # Student-t unit levels
    "m8-nocurves",  # + each unit's linear drift
)
