"""Exact independent compression of nonfloor, floor, and interaction blocks.

Changes deterministic arithmetic sharing only; preserves the reference posterior.
"""
from __future__ import annotations
import numpy as np
import pymc as pm
import pytensor.tensor as pt
from . import bayesian_feature_graph as reference
from .bayesian_feature_graph_v3 import graph_configuration, bedroom_index

VERSION = 'bayesian-independent-floor-block-graph-v1'


def compress_blocks(matrix, features):
    """Partition every saved column once; losslessly compress each block."""
    matrix = np.asarray(matrix)
    if matrix.ndim != 2 or matrix.shape[1] != len(features) or len(set(features)) != len(features):
        raise ValueError('Unique feature names must match matrix columns')
    if not np.isfinite(matrix).all():
        raise ValueError('Finite feature matrix required')
    groups = {'nonfloor': [], 'floor': [], 'interaction': []}
    for index, name in enumerate(features):
        block = ('floor' if name.startswith('listed_floor_gt_') or name == 'listed_floor.unknown'
                 else 'interaction' if name.startswith('floor_elevator_') else 'nonfloor')
        groups[block].append(index)
    if not groups['floor']:
        raise ValueError('A saved cumulative floor design is required')
    blocks = []
    for name, indices in groups.items():
        if indices:
            columns = np.asarray(indices, dtype=np.int64)
            unique, inverse = reference.compress(matrix[:, columns])
            blocks.append((name, columns, unique, inverse))
    return blocks


def build_model(train, design, prior_multiplier=1., *, residual_scale='shared',
                building_prior_scale=.35, unit_prior_scale=.25, residual_parameterization='centered'):
    config = graph_configuration(train, prior_multiplier, residual_scale=residual_scale,
                                 building_prior_scale=building_prior_scale, unit_prior_scale=unit_prior_scale,
                                 residual_parameterization=residual_parameterization)
    d = design.time
    a = d.arrays(train)
    blocks = compress_blocks(design.matrix(train), design.features)
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
        feature_mu = sum(pt.dot(unique, beta[columns])[inverse]
                         for _, columns, unique, inverse in blocks)
        monthly_mu = (pt.dot(d.time_matrix-d.time_center, trend_coefficients)
                      + annual_drift*(d.linear_time-d.linear_center))
        seasonal_mu = pt.dot(d.season_matrix-d.season_weights@d.season_matrix, season_coefficients)
        mu = (alpha + feature_mu + monthly_mu[a['period']] + seasonal_mu[a['season']]
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
        'version': VERSION, 'observations': len(train),
        'blocks': [{'name': name, 'columns': columns.tolist(), 'features': len(columns),
                    'unique_rows': len(unique), 'dense_entries': int(unique.size)}
                   for name, columns, unique, inverse in blocks],
        'periods': len(d.periods), 'features': len(design.features),
        'expanded_dense_entries': len(train)*(len(design.features)+d.time_matrix.shape[1]+11),
        'compressed_dense_entries': int(sum(unique.size for _, _, unique, _ in blocks)+d.time_matrix.size+d.season_matrix.size),
        'interpretation': 'Exact sharing of repeated matrix rows; no rounding, aggregation of targets or changed mean specification.'}
    return model
