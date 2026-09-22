"""Bedroom-group time-trend deviations on the shared-residual v3 graph.

The frozen main graph gives every bedroom count one Chelsea-wide trend. Saved
deviations (unit effect + residual) of the selected fit are systematically
signed by bedroom group and era: in 2010-2013 studios sit 2-4% below and
two/three-bedroom units 4-10% above their fitted values; by 2026 studios are
2% below and 3+ bedrooms 3% above. This graph adds an explicit deviation curve
per bedroom group:

    mu_i += f_{g(i)}(t(i)),  g in {studio, 1, 2, 3+}.

`walk`: f_g is piecewise-linear between January knots with Gaussian
random-walk knot values, step scale tau ~ HalfNormal(walk_prior_scale) per year.
`linear`: f_g(t) = delta_g * years, delta_g ~ N(0, linear_prior_scale).

Both are zero-sum across groups at every knot/slope (the common trend stays the
equal-weight group average) and each group's curve is centered over that
group's own training periods, so bedroom increments keep their meaning as
period-averaged premiums and the curves carry only relative time movement.
Everything else is identical to `bayesian_feature_graph_v3` with shared noise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt

from . import bayesian_feature_graph as reference
from .bayesian_feature_graph_v3 import graph_configuration as base_configuration

VERSION = 'bayesian-bedroom-time-graph-v1'
MODES = ('none', 'linear', 'walk')
GROUP_LABELS = ('studio', 'one_bedroom', 'two_bedroom', 'three_plus_bedroom')


def bedroom_groups(bedrooms):
    values = np.asarray(bedrooms, dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or (values != np.floor(values)).any():
        raise ValueError('Bedroom-time groups require nonnegative integer bedroom counts')
    return np.minimum(values.astype(int), len(GROUP_LABELS)-1)


def knot_matrix(periods):
    """Piecewise-linear interpolation from January knots (plus the final month)."""
    periods = pd.DatetimeIndex(periods)
    months = np.arange(len(periods), dtype=float)
    knots = [float(i) for i, p in enumerate(periods) if p.month == 1]
    if not knots or knots[0] != 0.:
        knots.insert(0, 0.)
    if knots[-1] != months[-1]:
        knots.append(months[-1])
    knots = np.asarray(knots)
    basis = np.zeros((len(periods), len(knots)))
    for k in range(len(knots)):
        e = np.zeros(len(knots)); e[k] = 1.
        basis[:, k] = np.interp(months, knots, e)
    labels = [periods[int(k)].strftime('%Y-%m') for k in knots]
    return basis, knots, labels


def graph_configuration(train, prior_multiplier=1., *, mode='walk', walk_prior_scale=.05,
                        linear_prior_scale=.02, building_prior_scale=.35, unit_prior_scale=.25,
                        group_column='bedrooms'):
    if mode not in MODES:
        raise ValueError('Unknown bedroom-time mode')
    config = base_configuration(train, prior_multiplier, building_prior_scale=building_prior_scale,
                                unit_prior_scale=unit_prior_scale)
    groups, counts = np.unique(bedroom_groups(train[group_column]), return_counts=True)
    if mode != 'none' and len(groups) != len(GROUP_LABELS):
        raise ValueError('Every bedroom-time group must be observed')
    config.update(bedroom_time={
        'version': VERSION, 'mode': mode, 'groups': list(GROUP_LABELS),
        'group_counts': counts.tolist(), 'group_column': group_column,
        'walk_prior_scale': float(walk_prior_scale) if mode == 'walk' else None,
        'linear_prior_scale': float(linear_prior_scale) if mode == 'linear' else None,
        'identification': 'zero-sum across groups; each group curve centered over its own training periods'})
    return config


def build_model(train, design, prior_multiplier=1., *, mode='walk', walk_prior_scale=.05,
                linear_prior_scale=.02, building_prior_scale=.35, unit_prior_scale=.25, group_column='bedrooms'):
    """`group_column` other than bedrooms exists only for screening negative controls."""
    config = graph_configuration(train, prior_multiplier, mode=mode, walk_prior_scale=walk_prior_scale,
                                 linear_prior_scale=linear_prior_scale,
                                 building_prior_scale=building_prior_scale, unit_prior_scale=unit_prior_scale,
                                 group_column=group_column)
    d = design.time
    a = d.arrays(train)
    unique, inverse = reference.compress(design.matrix(train))
    group = bedroom_groups(train[group_column])
    n_periods, n_groups = len(d.periods), len(GROUP_LABELS)
    weights = np.zeros((n_groups, n_periods))
    np.add.at(weights, (group, a['period']), 1.)
    weights /= np.maximum(weights.sum(1, keepdims=True), 1.)
    coords = {'feature': design.features, 'building': d.buildings, 'unit': d.unit_ids,
              'trend_basis': np.arange(d.time_matrix.shape[1]), 'season_basis': np.arange(11),
              'bedroom_group': list(GROUP_LABELS), 'period': [p.strftime('%Y-%m') for p in d.periods]}
    with pm.Model(coords=coords) as model:
        alpha = pm.Normal('alpha', np.log(4500), .8)
        beta = pm.Normal('beta', 0., design.prior_scales*config['beta_prior_multiplier'], dims='feature')
        trend_scale = pm.HalfNormal('trend_scale', .15)
        trend_coefficients = pm.Normal('trend_coefficients', 0, trend_scale*d.time_prior_scales, dims='trend_basis')
        annual_drift = pm.Normal('annual_drift', .03, .05)
        season_scale = pm.HalfNormal('season_scale', .10)
        season_coefficients = pm.Normal('season_coefficients', 0, season_scale, dims='season_basis')
        sigma_building = pm.HalfNormal('sigma_building', config['building_prior_scale'])
        building_effect = pm.ZeroSumNormal('building_effect', sigma=sigma_building, dims='building')
        sigma_unit = pm.HalfNormal('sigma_unit', config['unit_prior_scale'])
        unit_z = pm.Normal('unit_z', 0, 1, dims='unit')
        sigma = pm.HalfNormal('sigma', .25)
        monthly_mu = (pt.dot(d.time_matrix-d.time_center, trend_coefficients)
                      + annual_drift*(d.linear_time-d.linear_center))
        seasonal_mu = pt.dot(d.season_matrix-d.season_weights@d.season_matrix, season_coefficients)
        mu = (alpha + pt.dot(unique, beta)[inverse] + monthly_mu[a['period']] + seasonal_mu[a['season']]
              + building_effect[a['building']] + sigma_unit*unit_z[a['unit']])
        if mode != 'none':
            if mode == 'walk':
                basis, knots, labels = knot_matrix(d.periods)
                model.add_coord('time_knot', labels)
                walk_scale = pm.HalfNormal('bedroom_walk_scale', walk_prior_scale)
                steps = pm.Normal('bedroom_walk_z', 0, 1, dims=('bedroom_group', 'time_knot'))
                levels = walk_scale*pt.cumsum(steps, axis=1)
                raw = pt.dot(levels, basis.T)
            else:
                years = (np.arange(n_periods)-d.anchor)/12.
                slope = pm.Normal('bedroom_slope_raw', 0, linear_prior_scale, dims='bedroom_group')
                raw = slope[:, None]*years[None, :]
            raw = raw-raw.mean(0, keepdims=True)
            curve = raw-(raw*weights).sum(1, keepdims=True)
            curve = pm.Deterministic('bedroom_time', curve, dims=('bedroom_group', 'period'))
            mu = mu+curve.reshape((-1,))[group*n_periods+a['period']]
        pm.StudentT('log_rent', nu=5., mu=mu, sigma=sigma, observed=np.log(train.asking_rent))
    model.graph_configuration = config
    model.compression_summary = {
        'version': VERSION, 'observations': len(train), 'features': len(design.features),
        'unique_feature_rows': len(unique), 'periods': n_periods, 'bedroom_groups': n_groups,
        'interpretation': 'Exact sharing of repeated feature rows; no rounding or aggregation of targets.'}
    return model
