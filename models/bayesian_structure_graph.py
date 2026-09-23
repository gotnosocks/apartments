"""Structural extensions of the promoted bedroom-time graph (research screening).

Adds, each optional:

* ``building_time='slope'``: per-building linear drift s_b * (years - ybar_b),
  s_b = scale * z_b, z_b ~ N(0, 1);
* ``building_time='walk'``: per-building random walk on knots every
  ``building_knot_years`` years (piecewise-linear), step sd = scale*sqrt(years);
* ``bedroom_groups=5``: split 3+ bedrooms into 3 and 4+ for the time curve;
* ``nu=None``: estimate the Student-t degrees of freedom, nu ~ Gamma(2, 0.1).

Every building curve is centered over that building's own training months, so
building effects keep their meaning as period-averaged offsets. ``scale=None``
gives the drift scale a HalfNormal(scale_prior) hyperprior; a number fixes it
(used by conditional-MAP screening, where free hierarchical scales degenerate).
With the defaults this is exactly `bayesian_bedroom_time_graph` in walk mode.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt

from . import bayesian_feature_graph as reference
from . import bayesian_bedroom_time_graph as bedroom_time
from .bayesian_feature_graph_v3 import graph_configuration as base_configuration

VERSION = 'bayesian-structure-graph-v1'
BUILDING_TIME = ('none', 'slope', 'walk')


def groups(bedrooms, count):
    if count not in (4, 5):
        raise ValueError('bedroom_groups must be 4 or 5')
    values = bedroom_time.bedroom_groups(bedrooms)  # validates nonnegative integers
    return np.minimum(np.asarray(bedrooms, dtype=float).astype(int), count-1) if count == 5 else values


def group_labels(count):
    return list(bedroom_time.GROUP_LABELS) if count == 4 else [
        'studio', 'one_bedroom', 'two_bedroom', 'three_bedroom', 'four_plus_bedroom']


def building_knots(periods, years):
    periods = pd.DatetimeIndex(periods)
    months = np.arange(len(periods), dtype=float)
    step = 12*years
    knots = list(np.arange(0., months[-1], step))
    if knots[-1] != months[-1]:
        knots.append(months[-1])
    knots = np.asarray(knots)
    basis = np.zeros((len(periods), len(knots)))
    for k in range(len(knots)):
        e = np.zeros(len(knots)); e[k] = 1.
        basis[:, k] = np.interp(months, knots, e)
    return basis, knots


def configuration(train, *, bedroom_groups=4, building_time='none', building_scale=None,
                  building_scale_prior=.02, building_knot_years=4, nu=5., walk_prior_scale=.05,
                  building_prior_scale=.35, unit_prior_scale=.25, prior_multiplier=1.):
    if building_time not in BUILDING_TIME:
        raise ValueError('Unknown building-time mode')
    config = base_configuration(train, prior_multiplier, building_prior_scale=building_prior_scale,
                                unit_prior_scale=unit_prior_scale)
    config.update(student_t_nu=None if nu is None else float(nu), structure={
        'version': VERSION, 'bedroom_groups': group_labels(bedroom_groups),
        'walk_prior_scale': float(walk_prior_scale), 'building_time': building_time,
        'building_scale': None if building_scale is None else float(building_scale),
        'building_scale_prior': float(building_scale_prior),
        'building_knot_years': building_knot_years if building_time == 'walk' else None,
        'nu': None if nu is None else float(nu)})
    return config


def build_model(train, design, *, bedroom_groups=4, building_time='none', building_scale=None,
                building_scale_prior=.02, building_knot_years=4, nu=5., walk_prior_scale=.05,
                building_prior_scale=.35, unit_prior_scale=.25, prior_multiplier=1., group_column='bedrooms'):
    """`group_column` other than bedrooms exists only for screening negative controls."""
    config = configuration(train, bedroom_groups=bedroom_groups, building_time=building_time,
        building_scale=building_scale, building_scale_prior=building_scale_prior,
        building_knot_years=building_knot_years, nu=nu, walk_prior_scale=walk_prior_scale,
        building_prior_scale=building_prior_scale, unit_prior_scale=unit_prior_scale,
        prior_multiplier=prior_multiplier)
    d = design.time
    a = d.arrays(train)
    unique, inverse = reference.compress(design.matrix(train))
    group = groups(train[group_column], bedroom_groups)
    labels = group_labels(bedroom_groups)
    n_periods, n_groups, n_buildings = len(d.periods), len(labels), len(d.buildings)
    weights = np.zeros((n_groups, n_periods))
    np.add.at(weights, (group, a['period']), 1.)
    weights /= np.maximum(weights.sum(1, keepdims=True), 1.)
    building_weights = np.zeros((n_buildings, n_periods))
    np.add.at(building_weights, (a['building'], a['period']), 1.)
    building_weights /= np.maximum(building_weights.sum(1, keepdims=True), 1.)
    basis, _, knot_labels = bedroom_time.knot_matrix(d.periods)
    coords = {'feature': design.features, 'building': d.buildings, 'unit': d.unit_ids,
              'trend_basis': np.arange(d.time_matrix.shape[1]), 'season_basis': np.arange(11),
              'bedroom_group': labels, 'period': [p.strftime('%Y-%m') for p in d.periods],
              'time_knot': knot_labels}
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
        walk_scale = pm.HalfNormal('bedroom_walk_scale', walk_prior_scale)
        steps = pm.Normal('bedroom_walk_z', 0, 1, dims=('bedroom_group', 'time_knot'))
        raw = pt.dot(walk_scale*pt.cumsum(steps, axis=1), basis.T)
        raw = raw-raw.mean(0, keepdims=True)
        curve = pm.Deterministic('bedroom_time', raw-(raw*weights).sum(1, keepdims=True),
                                 dims=('bedroom_group', 'period'))
        mu = mu+curve.reshape((-1,))[group*n_periods+a['period']]
        if building_time != 'none':
            scale = (pm.HalfNormal('building_time_scale', building_scale_prior) if building_scale is None
                     else float(building_scale))
            if building_time == 'slope':
                years = (np.arange(n_periods)-d.anchor)/12.
                centers = building_weights@years
                model.add_coord('building_time_basis', [0])
                z = pm.Normal('building_time_z', 0, 1, dims=('building', 'building_time_basis'))
                drift = scale*z[:, 0]
                mu = mu+drift[a['building']]*(years[a['period']]-centers[a['building']])
            else:
                bbasis, bknots = building_knots(d.periods, building_knot_years)
                model.add_coord('building_time_basis', np.arange(len(bknots)))
                z = pm.Normal('building_time_z', 0, 1, dims=('building', 'building_time_basis'))
                levels = scale*np.sqrt(building_knot_years)*pt.cumsum(z, axis=1)
                centers = (levels*(building_weights@bbasis)).sum(1)
                mu = mu+(levels[a['building']]*bbasis[a['period']]).sum(1)-centers[a['building']]
        nu_value = pm.Gamma('nu', 2., .1) if nu is None else float(nu)
        pm.StudentT('log_rent', nu=nu_value, mu=mu, sigma=sigma, observed=np.log(train.asking_rent))
    config['structure']['group_column'] = group_column
    model.graph_configuration = config
    model.building_weights = building_weights
    return model


def building_time_numpy(posterior, design, frame, building_weights, *, building_time, building_scale,
                        building_knot_years):
    """Per-row building-time contribution for stacked draws (rows x samples)."""
    if building_time == 'none':
        return 0.
    d = design.time
    a = d.arrays(frame)
    z = posterior['building_time_z'].values  # (building, basis, sample)
    scale = (posterior['building_time_scale'].values if building_scale is None
             else np.full(z.shape[-1], float(building_scale)))
    if building_time == 'slope':
        years = (np.arange(len(d.periods))-d.anchor)/12.
        centers = building_weights@years
        return scale[None]*z[a['building'], 0]*(years[a['period']]-centers[a['building']])[:, None]
    bbasis, _ = building_knots(d.periods, building_knot_years)
    levels = scale[None, None]*np.sqrt(building_knot_years)*np.cumsum(z, axis=1)
    centers = np.einsum('bks,bk->bs', levels, building_weights@bbasis)
    return (np.einsum('rks,rk->rs', levels[a['building']], bbasis[a['period']])
            - centers[a['building']])
