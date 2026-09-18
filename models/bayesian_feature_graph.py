"""Equivalent compressed likelihood graph for Bayesian feature research.

Preserves every observation and exactly the same priors and linear predictor.
Only identical covariate rows and calendar-level matrix products are shared.
"""
from __future__ import annotations

import numpy as np
import pymc as pm
import pytensor.tensor as pt

from . import bayesian_feature_model as reference

VERSION = 'compressed-bayesian-feature-graph-v1'


def compress(matrix):
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError('Finite two-dimensional feature matrix required')
    unique, inverse = np.unique(matrix, axis=0, return_inverse=True)
    if not np.array_equal(unique[inverse], matrix):
        raise ValueError('Feature compression must be lossless')
    return unique, inverse


def build_model(train, design, prior_multiplier=1.):
    d = design.time
    a = d.arrays(train)
    unique, inverse = compress(design.matrix(train))
    coords = {'feature': design.features, 'building': d.buildings, 'unit': d.unit_ids,
              'trend_basis': np.arange(d.time_matrix.shape[1]), 'season_basis': np.arange(11)}
    with pm.Model(coords=coords) as model:
        alpha = pm.Normal('alpha', np.log(4500), .8)
        beta = pm.Normal('beta', 0., design.prior_scales*prior_multiplier, dims='feature')
        trend_scale = pm.HalfNormal('trend_scale', .15)
        trend_coefficients = pm.Normal('trend_coefficients', 0, trend_scale*d.time_prior_scales, dims='trend_basis')
        annual_drift = pm.Normal('annual_drift', .03, .05)
        season_scale = pm.HalfNormal('season_scale', .10)
        season_coefficients = pm.Normal('season_coefficients', 0, season_scale, dims='season_basis')
        sigma_building = pm.HalfNormal('sigma_building', .35)
        building_effect = pm.ZeroSumNormal('building_effect', sigma=sigma_building, dims='building')
        sigma_unit = pm.HalfNormal('sigma_unit', .25)
        unit_z = pm.Normal('unit_z', 0, 1, dims='unit')
        sigma = pm.HalfNormal('sigma', .25)
        feature_mu = pt.dot(unique, beta)
        monthly_mu = (pt.dot(d.time_matrix-d.time_center, trend_coefficients)
                      + annual_drift*(d.linear_time-d.linear_center))
        seasonal_mu = pt.dot(d.season_matrix-d.season_weights@d.season_matrix, season_coefficients)
        mu = (alpha + feature_mu[inverse] + monthly_mu[a['period']] + seasonal_mu[a['season']]
              + building_effect[a['building']] + sigma_unit*unit_z[a['unit']])
        pm.StudentT('log_rent', nu=5., mu=mu, sigma=sigma, observed=np.log(train.asking_rent))
    model.compression_summary = {
        'observations': len(train), 'unique_feature_rows': len(unique),
        'periods': len(d.periods), 'features': len(design.features),
        'expanded_dense_entries': len(train)*(len(design.features)+d.time_matrix.shape[1]+11),
        'compressed_dense_entries': int(unique.size+d.time_matrix.size+d.season_matrix.size),
        'interpretation': 'Exact sharing of repeated matrix rows; no rounding, aggregation of targets or changed posterior specification.'}
    return model
