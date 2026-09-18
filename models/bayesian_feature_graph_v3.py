"""Explicit residual/group-prior research alternatives to the frozen mean model.

Shared residual scale with default group priors is exactly the original compressed
posterior. Bedroom residual scales change observation noise only; the rent-location
features, Student-t degrees of freedom and mean-parameter priors are unchanged.
"""
from __future__ import annotations

import numpy as np
import pymc as pm
import pytensor.tensor as pt

from . import bayesian_feature_graph as reference

VERSION = 'bayesian-feature-residual-graph-v3'
CENTERED_VERSION = 'bayesian-feature-residual-graph-v3-centered'
RESIDUAL_PARAMETERIZATIONS = ('centered', 'noncentered')
RESIDUAL_SCALES = ('shared', 'bedroom')


def _positive(value, name):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(name+' must be a finite positive number')
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(name+' must be a finite positive number') from None
    if not np.isfinite(number) or number <= 0:
        raise ValueError(name+' must be a finite positive number')
    return number


def _bedrooms(values):
    values = np.asarray(values)
    if values.ndim != 1 or values.dtype.kind not in 'iuf' or values.size == 0:
        raise ValueError('Bedroom residual scales require nonnegative integer bedroom counts')
    numeric = values.astype(float)
    if not np.isfinite(numeric).all() or np.any(numeric < 0) or np.any(numeric != np.floor(numeric)):
        raise ValueError('Bedroom residual scales require nonnegative integer bedroom counts')
    if np.any(numeric > np.iinfo(np.int32).max):
        raise ValueError('Unsupported bedroom count')
    return numeric.astype(int)


def bedroom_index(values, levels):
    """Encode strictly within a declared, sorted set of observed bedroom levels."""
    observed, levels = _bedrooms(values), _bedrooms(levels)
    if not np.array_equal(levels, np.unique(levels)):
        raise ValueError('Bedroom levels must be sorted and unique')
    index = np.searchsorted(levels, observed)
    if np.any(index >= len(levels)) or not np.array_equal(levels[np.minimum(index, len(levels)-1)], observed):
        raise ValueError('Unsupported bedroom count absent from fitted residual levels')
    return index


def graph_configuration(train, prior_multiplier=1., *, residual_scale='shared',
                        building_prior_scale=.35, unit_prior_scale=.25, residual_parameterization='centered'):
    if residual_scale not in RESIDUAL_SCALES:
        raise ValueError('Unknown residual scale specification')
    if residual_parameterization not in RESIDUAL_PARAMETERIZATIONS:
        raise ValueError('Unknown residual hierarchy parameterization')
    multiplier = _positive(prior_multiplier, 'prior_multiplier')
    building = _positive(building_prior_scale, 'building_prior_scale')
    unit = _positive(unit_prior_scale, 'unit_prior_scale')
    levels, counts = [], []
    if residual_scale == 'bedroom':
        values = _bedrooms(train.bedrooms)
        unique, support = np.unique(values, return_counts=True)
        if len(unique) < 2:
            raise ValueError('Bedroom residual pooling requires at least two observed bedroom levels')
        levels, counts = unique.tolist(), support.tolist()
    configuration = {'version': VERSION, 'residual_scale': residual_scale, 'student_t_nu': 5.,
            'beta_prior_multiplier': multiplier, 'building_prior_scale': building,
            'unit_prior_scale': unit, 'residual_sigma_prior_scale': .25,
            'residual_bedroom_levels': levels, 'residual_bedroom_counts': counts,
            'residual_bedroom_offset_scale_prior': .3 if residual_scale == 'bedroom' else None,
            'parameterization': ('sigma_by_bedroom = sigma * exp(residual_bedroom_scale * residual_bedroom_z); '
                'z ~ ZeroSumNormal(sigma=1), scale ~ HalfNormal(0.3). Equal-level zero-sum log offsets; '
                'sigma is the geometric mean across observed bedroom-level scales, not their frequency-weighted mean.'
                if residual_scale == 'bedroom' else 'One shared sigma ~ HalfNormal(0.25).')}
    if residual_scale == 'bedroom' and residual_parameterization == 'centered':
        configuration.update(version=CENTERED_VERSION, residual_bedroom_parameterization='centered',
            parameterization='offset ~ ZeroSumNormal(sigma=residual_bedroom_scale), scale ~ HalfNormal(0.3); '
                'sigma_by_bedroom = sigma * exp(offset), residual_bedroom_z = offset/scale. '
                'Centered equal-level zero-sum log offsets; sigma is the geometric mean across observed '
                'bedroom-level scales, not their frequency-weighted mean.')
    return configuration


def build_model(train, design, prior_multiplier=1., *, residual_scale='shared',
                building_prior_scale=.35, unit_prior_scale=.25, residual_parameterization='centered'):
    config = graph_configuration(train, prior_multiplier, residual_scale=residual_scale,
                                 building_prior_scale=building_prior_scale, unit_prior_scale=unit_prior_scale,
                                 residual_parameterization=residual_parameterization)
    d = design.time
    a = d.arrays(train)
    unique, inverse = reference.compress(design.matrix(train))
    coords = {'feature': design.features, 'building': d.buildings, 'unit': d.unit_ids,
              'trend_basis': np.arange(d.time_matrix.shape[1]), 'season_basis': np.arange(11)}
    if residual_scale == 'bedroom':
        coords['residual_bedroom'] = config['residual_bedroom_levels']
        residual_index = bedroom_index(train.bedrooms, config['residual_bedroom_levels'])
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
        feature_mu = pt.dot(unique, beta)
        monthly_mu = (pt.dot(d.time_matrix-d.time_center, trend_coefficients)
                      + annual_drift*(d.linear_time-d.linear_center))
        seasonal_mu = pt.dot(d.season_matrix-d.season_weights@d.season_matrix, season_coefficients)
        mu = (alpha + feature_mu[inverse] + monthly_mu[a['period']] + seasonal_mu[a['season']]
              + building_effect[a['building']] + sigma_unit*unit_z[a['unit']])
        observation_sigma = sigma
        if residual_scale == 'bedroom':
            if residual_parameterization == 'noncentered':
                residual_z = pm.ZeroSumNormal('residual_bedroom_z', sigma=1., dims='residual_bedroom')
                residual_scale_sd = pm.HalfNormal('residual_bedroom_scale', .3)
                residual_offset = residual_scale_sd*residual_z
            else:
                residual_scale_sd = pm.HalfNormal('residual_bedroom_scale', .3)
                residual_offset = pm.ZeroSumNormal('residual_bedroom_offset', sigma=residual_scale_sd, dims='residual_bedroom')
                pm.Deterministic('residual_bedroom_z', residual_offset/residual_scale_sd, dims='residual_bedroom')
            sigma_by_bedroom = pm.Deterministic('sigma_by_bedroom',
                sigma*pt.exp(residual_offset), dims='residual_bedroom')
            observation_sigma = sigma_by_bedroom[residual_index]
        pm.StudentT('log_rent', nu=5., mu=mu, sigma=observation_sigma, observed=np.log(train.asking_rent))
    model.graph_configuration = config
    model.compression_summary = {
        'observations': len(train), 'unique_feature_rows': len(unique),
        'periods': len(d.periods), 'features': len(design.features),
        'expanded_dense_entries': len(train)*(len(design.features)+d.time_matrix.shape[1]+11),
        'compressed_dense_entries': int(unique.size+d.time_matrix.size+d.season_matrix.size),
        'interpretation': 'Exact sharing of repeated matrix rows; no rounding, aggregation of targets or changed mean specification.'}
    return model
