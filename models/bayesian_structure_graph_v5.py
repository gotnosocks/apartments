"""Structure graph v5: v4 plus per-building slopes on named design columns.

v4 is kept for its screens. ``building_feature_slopes`` names raw feature-design
columns (e.g. ``log_size_within_bedrooms``, ``full_bathrooms_gt_1``,
``full_bathrooms_gt_2``); each gets s_bj = tau_j * z_bj, z_bj ~ N(0, 1),
tau_j ~ HalfNormal(``feature_slope_prior``), added as s_bj * x_j on the raw
(uncentered) column: how much each building's size and bathroom premiums
differ from the Chelsea-wide ones. Following the from-scratch model session's
m6 ablation. ``citywide_walk_months`` adds a citywide random walk on knots
every that many months (scale ~ HalfNormal(``citywide_walk_prior``)), after
the from-scratch session's quarterly citywide walk; it carries sharp shared
moves such as the 2021 rebound, so building walks can be centered across
buildings without leaving that to the smooth trend basis. With default
arguments v5 builds exactly the v4 graph.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt

from . import bayesian_bedroom_time_graph as bedroom_time
from . import bayesian_feature_graph as reference
from . import bayesian_location_terms as location_terms
from .bayesian_feature_graph_v3 import graph_configuration as base_configuration

VERSION = "bayesian-structure-graph-v5"
BUILDING_TIME = ("none", "slope", "walk")


def groups(bedrooms, count):
    if count not in (4, 5):
        raise ValueError("bedroom_groups must be 4 or 5")
    values = bedroom_time.bedroom_groups(bedrooms)  # validates nonnegative integers
    return (
        np.minimum(np.asarray(bedrooms, dtype=float).astype(int), count - 1)
        if count == 5
        else values
    )


def group_labels(count):
    return (
        list(bedroom_time.GROUP_LABELS)
        if count == 4
        else [
            "studio",
            "one_bedroom",
            "two_bedroom",
            "three_bedroom",
            "four_plus_bedroom",
        ]
    )


def building_knots(periods, years):
    return location_terms.building_knots(pd.DatetimeIndex(periods), years)


def configuration(
    train,
    *,
    bedroom_groups=4,
    building_time="none",
    building_scale=None,
    building_scale_prior=0.02,
    building_knot_years=4,
    nu=5.0,
    walk_prior_scale=0.05,
    building_prior_scale=0.35,
    unit_prior_scale=0.25,
    prior_multiplier=1.0,
    group_column="bedrooms",
    shock_months=None,
    shock_scale=None,
    shock_scale_prior=0.05,
    noise="shared",
    noise_scale=None,
    noise_scale_prior=0.3,
    unit_slope_scale=None,
    unit_centering="none",
    intercept="global",
    walk_centering="none",
    feature_basis="identity",
    feature_centering="none",
    building_bedroom_slope=False,
    bedroom_slope_prior=0.1,
    building_feature_slopes=(),
    feature_slope_prior=0.1,
    citywide_walk_months=None,
    citywide_walk_prior=0.05,
):
    if building_time not in BUILDING_TIME:
        raise ValueError("Unknown building-time mode")
    config = base_configuration(
        train,
        prior_multiplier,
        building_prior_scale=building_prior_scale,
        unit_prior_scale=unit_prior_scale,
    )
    config.update(
        student_t_nu=None if nu is None else float(nu),
        structure={
            "version": VERSION,
            "bedroom_groups": group_labels(bedroom_groups),
            "walk_prior_scale": float(walk_prior_scale),
            "building_time": building_time,
            "building_scale": None if building_scale is None else float(building_scale),
            "building_scale_prior": float(building_scale_prior),
            "building_knot_years": building_knot_years
            if building_time == "walk"
            else None,
            "nu": None if nu is None else float(nu),
            "group_column": group_column,
            "shock_months": shock_months,
            "shock_scale": None if shock_scale is None else float(shock_scale),
            "shock_scale_prior": float(shock_scale_prior),
            "noise": noise,
            "noise_scale": noise_scale,
            "noise_scale_prior": noise_scale_prior,
            "unit_slope_scale": unit_slope_scale,
            "unit_centering": unit_centering,
            "intercept": intercept,
            "walk_centering": walk_centering,
            "feature_basis": feature_basis,
            "feature_centering": feature_centering,
            "building_bedroom_slope": building_bedroom_slope,
            "bedroom_slope_prior": bedroom_slope_prior,
            "building_feature_slopes": list(building_feature_slopes),
            "feature_slope_prior": feature_slope_prior,
            "citywide_walk_months": citywide_walk_months,
            "citywide_walk_prior": citywide_walk_prior,
        },
    )
    return config


def build_model(
    train,
    design,
    *,
    bedroom_groups=4,
    building_time="none",
    building_scale=None,
    building_scale_prior=0.02,
    building_knot_years=4,
    nu=5.0,
    walk_prior_scale=0.05,
    building_prior_scale=0.35,
    unit_prior_scale=0.25,
    prior_multiplier=1.0,
    group_column="bedrooms",
    shock_months=None,
    shock_scale=None,
    shock_scale_prior=0.05,
    noise="shared",
    noise_scale=None,
    noise_scale_prior=0.3,
    unit_slope_scale=None,
    unit_centering="none",
    intercept="global",
    walk_centering="none",
    feature_basis="identity",
    feature_centering="none",
    building_bedroom_slope=False,
    bedroom_slope_prior=0.1,
    building_feature_slopes=(),
    feature_slope_prior=0.1,
    citywide_walk_months=None,
    citywide_walk_prior=0.05,
):
    """`group_column` other than bedrooms exists only for screening negative controls."""
    config = configuration(
        train,
        bedroom_groups=bedroom_groups,
        building_time=building_time,
        building_scale=building_scale,
        building_scale_prior=building_scale_prior,
        building_knot_years=building_knot_years,
        nu=nu,
        walk_prior_scale=walk_prior_scale,
        building_prior_scale=building_prior_scale,
        unit_prior_scale=unit_prior_scale,
        prior_multiplier=prior_multiplier,
        group_column=group_column,
        shock_months=shock_months,
        shock_scale=shock_scale,
        shock_scale_prior=shock_scale_prior,
        noise=noise,
        noise_scale=noise_scale,
        noise_scale_prior=noise_scale_prior,
        unit_slope_scale=unit_slope_scale,
        unit_centering=unit_centering,
        intercept=intercept,
        walk_centering=walk_centering,
        feature_basis=feature_basis,
        feature_centering=feature_centering,
        building_bedroom_slope=building_bedroom_slope,
        bedroom_slope_prior=bedroom_slope_prior,
        building_feature_slopes=building_feature_slopes,
        feature_slope_prior=feature_slope_prior,
        citywide_walk_months=citywide_walk_months,
        citywide_walk_prior=citywide_walk_prior,
    )
    d = design.time
    a = d.arrays(train)
    full_matrix = design.matrix(train)
    if feature_centering == "building":
        if intercept != "building_mean":
            raise ValueError(
                "Within-building feature centering needs intercept=building_mean"
            )
        # Building means of every feature column (row-weighted); the row term
        # keeps only within-building deviations and beta . mean enters the
        # building level's prior mean: an exact reparameterization.
        rows_per_building = np.bincount(
            a0 := design.time.arrays(train)["building"],
            minlength=len(design.time.buildings),
        )
        building_means = np.zeros((len(design.time.buildings), full_matrix.shape[1]))
        np.add.at(building_means, a0, full_matrix)
        building_means /= np.maximum(rows_per_building, 1)[:, None]
        row_matrix = full_matrix - building_means[a0]
    elif feature_centering == "none":
        building_means = None
        row_matrix = full_matrix
    else:
        raise ValueError("feature_centering must be none or building")
    unique, inverse = reference.compress(row_matrix)
    group = groups(train[group_column], bedroom_groups)
    labels = group_labels(bedroom_groups)
    n_periods, n_groups, n_buildings = len(d.periods), len(labels), len(d.buildings)
    weights = np.zeros((n_groups, n_periods))
    np.add.at(weights, (group, a["period"]), 1.0)
    weights /= np.maximum(weights.sum(1, keepdims=True), 1.0)
    building_weights = np.zeros((n_buildings, n_periods))
    np.add.at(building_weights, (a["building"], a["period"]), 1.0)
    building_weights /= np.maximum(building_weights.sum(1, keepdims=True), 1.0)
    basis, _, knot_labels = bedroom_time.knot_matrix(d.periods)
    coords = {
        "feature": design.features,
        "building": d.buildings,
        "unit": d.unit_ids,
        "trend_basis": np.arange(d.time_matrix.shape[1]),
        "season_basis": np.arange(11),
        "bedroom_group": labels,
        "period": [p.strftime("%Y-%m") for p in d.periods],
        "time_knot": knot_labels,
    }
    with pm.Model(coords=coords) as model:
        alpha = pm.Normal("alpha", np.log(4500), 0.8)
        beta_scales = design.prior_scales * config["beta_prior_multiplier"]
        if feature_basis == "qr":
            # Sample theta = R beta (X = Q R of the centered training design):
            # the likelihood is near-isotropic in theta, so correlated feature
            # columns no longer slow a diagonal mass matrix. beta = R^-1 theta is
            # linear (constant Jacobian) and keeps its exact N(0, scale) prior.
            matrix = row_matrix
            if np.linalg.matrix_rank(matrix) < matrix.shape[1]:
                raise ValueError("QR feature basis needs a full-rank design")
            r_factor = np.linalg.qr(matrix / np.sqrt(len(matrix)), mode="r")
            theta = pm.Flat("beta_qr", dims="feature")
            beta = pm.Deterministic(
                "beta",
                pt.dot(np.linalg.inv(r_factor), theta),
                dims="feature",
            )
            pm.Potential(
                "beta_prior", pm.logp(pm.Normal.dist(0.0, beta_scales), beta).sum()
            )
        elif feature_basis == "identity":
            beta = pm.Normal("beta", 0.0, beta_scales, dims="feature")
        else:
            raise ValueError("feature_basis must be identity or qr")
        trend_scale = pm.HalfNormal("trend_scale", 0.15)
        trend_coefficients = pm.Normal(
            "trend_coefficients",
            0,
            trend_scale * d.time_prior_scales,
            dims="trend_basis",
        )
        annual_drift = pm.Normal("annual_drift", 0.03, 0.05)
        season_scale = pm.HalfNormal("season_scale", 0.10)
        season_coefficients = pm.Normal(
            "season_coefficients", 0, season_scale, dims="season_basis"
        )
        sigma_building = pm.HalfNormal("sigma_building", config["building_prior_scale"])
        if intercept == "building_mean":
            level_mean = (
                alpha
                if building_means is None
                else alpha + pt.dot(building_means, beta)
            )
            building_level = pm.Normal(
                "building_level", level_mean, sigma_building, dims="building"
            )
            # Saved so that alpha + x . beta + building_effect[j] reproduces mu,
            # the same arithmetic readers use for every other fit.
            building_effect = pm.Deterministic(
                "building_effect", building_level - level_mean, dims="building"
            )
            # The row term uses within-building features, so it adds the whole
            # building level (not the reader-facing effect, which also removes
            # beta . building mean because readers apply beta to raw features).
            building_term = building_level - alpha
        elif intercept == "global":
            building_effect = pm.ZeroSumNormal(
                "building_effect", sigma=sigma_building, dims="building"
            )
            building_term = building_effect
        else:
            raise ValueError("intercept must be global or building_mean")
        sigma_unit = pm.HalfNormal("sigma_unit", config["unit_prior_scale"])
        unit_z = pm.Normal("unit_z", 0, 1, dims="unit")
        unit_building = np.zeros(len(d.unit_ids), dtype=int)
        unit_building[a["unit"]] = a["building"]
        if unit_centering == "building":
            counts = np.bincount(unit_building, minlength=n_buildings)
            sums = pt.zeros(n_buildings)
            sums = pt.inc_subtensor(sums[unit_building], unit_z)
            unit_offsets = unit_z - (sums / np.maximum(counts, 1))[unit_building]
        elif unit_centering == "none":
            unit_offsets = unit_z
        else:
            raise ValueError("unit_centering must be none or building")
        sigma = pm.HalfNormal("sigma", 0.25)
        monthly_mu = pt.dot(
            d.time_matrix - d.time_center, trend_coefficients
        ) + annual_drift * (d.linear_time - d.linear_center)
        seasonal_mu = pt.dot(
            d.season_matrix - d.season_weights @ d.season_matrix, season_coefficients
        )
        mu = (
            alpha
            + pt.dot(unique, beta)[inverse]
            + monthly_mu[a["period"]]
            + seasonal_mu[a["season"]]
            + building_term[a["building"]]
            + sigma_unit * unit_offsets[a["unit"]]
        )
        walk_scale = pm.HalfNormal("bedroom_walk_scale", walk_prior_scale)
        steps = pm.Normal("bedroom_walk_z", 0, 1, dims=("bedroom_group", "time_knot"))
        raw = pt.dot(walk_scale * pt.cumsum(steps, axis=1), basis.T)
        raw = raw - raw.mean(0, keepdims=True)
        curve = pm.Deterministic(
            "bedroom_time",
            raw - (raw * weights).sum(1, keepdims=True),
            dims=("bedroom_group", "period"),
        )
        mu = mu + curve.reshape((-1,))[group * n_periods + a["period"]]
        if building_time != "none":
            scale = (
                pm.HalfNormal("building_time_scale", building_scale_prior)
                if building_scale is None
                else float(building_scale)
            )
            if building_time == "slope":
                years = (np.arange(n_periods) - d.anchor) / 12.0
                centers = building_weights @ years
                model.add_coord("building_time_basis", [0])
                z = pm.Normal(
                    "building_time_z", 0, 1, dims=("building", "building_time_basis")
                )
                drift = scale * z[:, 0]
                mu = mu + drift[a["building"]] * (
                    years[a["period"]] - centers[a["building"]]
                )
            else:
                bbasis, bknots = building_knots(d.periods, building_knot_years)
                # One flat (building-major) vector: diagnostics and reports can
                # then read bounded slices instead of a building x knot matrix.
                model.add_coord("building_knot", np.arange(n_buildings * len(bknots)))
                z = pm.Normal("building_time_z", 0, 1, dims="building_knot").reshape(
                    (n_buildings, len(bknots))
                )
                levels = scale * np.sqrt(building_knot_years) * pt.cumsum(z, axis=1)
                if walk_centering == "across_buildings":
                    # Remove the common drift: at every knot the walk levels
                    # average zero across buildings (weighted by rows), so the
                    # citywide trend and annual drift carry shared time movement.
                    rows = np.bincount(a["building"], minlength=n_buildings)
                    share = rows / rows.sum()
                    levels = levels - (levels * share[:, None]).sum(0, keepdims=True)
                elif walk_centering != "none":
                    raise ValueError("walk_centering must be none or across_buildings")
                centers = (levels * (building_weights @ bbasis)).sum(1)
                mu = (
                    mu
                    + (levels[a["building"]] * bbasis[a["period"]]).sum(1)
                    - centers[a["building"]]
                )
        if building_bedroom_slope:
            bedroom_step = (
                np.minimum(np.asarray(train.bedrooms, dtype=float), 4.0) - 1.0
            )
            slope_scale = pm.HalfNormal(
                "building_bedroom_slope_scale", bedroom_slope_prior
            )
            slope_z = pm.Normal("building_bedroom_slope_z", 0, 1, dims="building")
            mu = mu + slope_scale * slope_z[a["building"]] * bedroom_step
        if building_feature_slopes:
            raw, raw_names, _ = design.raw_features(train)
            missing = set(building_feature_slopes) - set(raw_names)
            if missing:
                raise ValueError(f"Unknown slope features: {sorted(missing)}")
            columns = raw[
                :, [raw_names.index(n) for n in building_feature_slopes]
            ].astype(float)
            model.add_coord("slope_feature", list(building_feature_slopes))
            feature_scale = pm.HalfNormal(
                "building_feature_slope_scale",
                feature_slope_prior,
                dims="slope_feature",
            )
            feature_z = pm.Normal(
                "building_feature_slope_z", 0, 1, dims=("building", "slope_feature")
            )
            mu = mu + ((feature_scale * feature_z)[a["building"]] * columns).sum(1)
        if citywide_walk_months:
            # Citywide random walk on knots every `citywide_walk_months`,
            # linearly interpolated, centered on the training rows so it does
            # not duplicate alpha. It carries sharp shared moves (the 2021
            # rebound) that the smooth trend basis cannot follow, which lets
            # the building walks be centered across buildings.
            cbasis, cknots = building_knots(d.periods, citywide_walk_months / 12.0)
            model.add_coord("citywide_knot", np.arange(len(cknots)))
            cscale = pm.HalfNormal("citywide_walk_scale", citywide_walk_prior)
            cz = pm.Normal("citywide_walk_z", 0, 1, dims="citywide_knot")
            clevels = cscale * np.sqrt(citywide_walk_months / 12.0) * pt.cumsum(cz)
            ccurve = pt.dot(cbasis, clevels)
            row_share = np.bincount(a["period"], minlength=len(d.periods))
            row_share = row_share / row_share.sum()
            citywide = pm.Deterministic(
                "citywide_walk", ccurve - pt.dot(row_share, ccurve), dims="period"
            )
            mu = mu + citywide[a["period"]]
        if shock_months:
            bucket = a["period"] // int(shock_months)
            n_buckets = (n_periods - 1) // int(shock_months) + 1
            shock_weights = np.zeros((n_buildings, n_buckets))
            np.add.at(shock_weights, (a["building"], bucket), 1.0)
            shock_weights /= np.maximum(shock_weights.sum(1, keepdims=True), 1.0)
            model.shock_weights = shock_weights
            model.add_coord("shock_bucket", np.arange(n_buckets))
            sscale = (
                pm.HalfNormal("building_shock_scale", shock_scale_prior)
                if shock_scale is None
                else float(shock_scale)
            )
            e = pm.Normal("building_shock_z", 0, 1, dims=("building", "shock_bucket"))
            centered = e - (e * shock_weights).sum(1, keepdims=True)
            mu = mu + sscale * centered[a["building"], bucket]
        if unit_slope_scale:
            # Per-unit linear drift, centered on each unit's own training years
            # (fixed scale; screened on a grid). Single-listing units contribute 0.
            years = (np.arange(n_periods) - d.anchor) / 12.0
            n_units = len(d.unit_ids)
            unit_years = np.bincount(
                a["unit"], weights=years[a["period"]], minlength=n_units
            )
            unit_years /= np.maximum(np.bincount(a["unit"], minlength=n_units), 1)
            model.unit_year_centers = unit_years
            slope = pm.Normal("unit_slope_z", 0, 1, dims="unit")
            scale = (
                pm.HalfNormal("unit_slope_scale", 0.01)
                if unit_slope_scale == "free"
                else float(unit_slope_scale)
            )
            mu = mu + scale * slope[a["unit"]] * (
                years[a["period"]] - unit_years[a["unit"]]
            )
        nu_value = pm.Gamma("nu", 2.0, 0.1) if nu is None else float(nu)
        observation_sigma = sigma
        if noise == "building":
            tau = (
                pm.HalfNormal("noise_building_scale", noise_scale_prior)
                if noise_scale is None
                else float(noise_scale)
            )
            noise_z = pm.ZeroSumNormal("noise_building_z", sigma=1.0, dims="building")
            observation_sigma = sigma * pt.exp(tau * noise_z)[a["building"]]
        elif noise == "level":
            # One global elasticity of the residual scale in the latent level:
            # sigma_i = sigma * exp(gamma * (mu_i - mean training log rent)).
            gamma = pm.Normal("noise_level_slope", 0.0, 0.5)
            center = float(np.mean(np.log(train.asking_rent)))
            observation_sigma = sigma * pt.exp(gamma * (mu - center))
        elif noise != "shared":
            raise ValueError("noise must be shared, building or level")
        pm.StudentT(
            "log_rent",
            nu=nu_value,
            mu=mu,
            sigma=observation_sigma,
            observed=np.log(train.asking_rent),
        )
    model.graph_configuration = config
    model.building_weights = building_weights
    return model


def building_time_numpy(
    posterior,
    design,
    frame,
    building_weights,
    *,
    building_time,
    building_scale,
    building_knot_years,
    centering_rows=None,
):
    """Per-row building-time contribution for stacked draws (rows x samples).

    ``centering_rows`` (training rows per building) reproduces
    ``walk_centering="across_buildings"``.
    """
    if building_time == "none":
        return 0.0
    d = design.time
    a = d.arrays(frame)
    z = posterior["building_time_z"].values  # (building, basis, sample)
    scale = (
        posterior["building_time_scale"].values
        if building_scale is None
        else np.full(z.shape[-1], float(building_scale))
    )
    if building_time == "slope":
        years = (np.arange(len(d.periods)) - d.anchor) / 12.0
        centers = building_weights @ years
        return (
            scale[None]
            * z[a["building"], 0]
            * (years[a["period"]] - centers[a["building"]])[:, None]
        )
    bbasis, _ = building_knots(d.periods, building_knot_years)
    if z.ndim == 2:  # flat building-major (building_knot, sample)
        z = z.reshape(len(d.buildings), bbasis.shape[1], z.shape[-1])
    levels = scale[None, None] * np.sqrt(building_knot_years) * np.cumsum(z, axis=1)
    if centering_rows is not None:
        share = np.asarray(centering_rows, dtype=float) / np.sum(centering_rows)
        levels = levels - np.einsum("bks,b->ks", levels, share)[None]
    centers = np.einsum("bks,bk->bs", levels, building_weights @ bbasis)
    return (
        np.einsum("rks,rk->rs", levels[a["building"]], bbasis[a["period"]])
        - centers[a["building"]]
    )


def building_shock_numpy(
    posterior, design, frame, shock_weights, *, shock_months, shock_scale
):
    """Per-row building shock for stacked draws (rows x samples)."""
    if not shock_months:
        return 0.0
    a = design.time.arrays(frame)
    e = posterior["building_shock_z"].values  # (building, bucket, sample)
    scale = (
        posterior["building_shock_scale"].values
        if shock_scale is None
        else np.full(e.shape[-1], float(shock_scale))
    )
    centered = e - np.einsum("bks,bk->bs", e, shock_weights)[:, None, :]
    return scale[None] * centered[a["building"], a["period"] // int(shock_months)]
