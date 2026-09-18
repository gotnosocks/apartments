"""Bayesian descriptive rent model with explicit bathroom composition and balance.

Research only: source-reported counts are measurements, not verified amenities.
The old serving model and its frozen runtime are deliberately independent.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import bayesian_rent_model as base
from . import amenity_rent_model as amenity
from apartments import pricing
import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt
import scipy.linalg

VERSION = 'bayesian-feature-bathroom-v1'
SPECS = ('linear_total', 'incremental_total', 'full_half', 'full_half_balance')


def bathroom_values(data):
    """Mask suspect measurements, never rewrite raw source values or drop rows."""
    full = pd.to_numeric(data.reported_full_bathrooms, errors='coerce').to_numpy(float)
    half = pd.to_numeric(data.reported_half_bathrooms, errors='coerce').to_numpy(float)
    flagged = data.bathroom_count_evidence.map(lambda v: bool(v.get('flags'))).to_numpy()
    total = pd.to_numeric(data.bathrooms, errors='coerce').to_numpy(float)
    known = (np.isfinite(full) & np.isfinite(half) & (full >= 1) & (half >= 0)
             & (full % 1 == 0) & (half % 1 == 0) & ~flagged
             & np.isfinite(total) & np.isclose(total, full+.5*half, rtol=0, atol=1e-8))
    return full, half, known


class FeatureDesign:
    def __init__(self, train, spec='full_half_balance'):
        if spec not in SPECS:
            raise ValueError('Unknown bathroom specification')
        self.spec = spec
        self.time = base.Design(train, train.period.max(), linear_drift=True)
        self.numeric = {}
        self.categories = {}
        normalized = [amenity.feature_record(r) for r in train.to_dict('records')]
        raw = [pricing._raw_features(r, '2000-01-01') for r in normalized]
        for field in amenity.NUMERIC:
            values = np.array([r[field] if r[field] is not None else np.nan for r in raw])
            known = np.isfinite(values)
            self.numeric[field] = {'center': float(values[known].mean()) if known.any() else 0.,
                'scale': float(values[known].std()) if len(set(values[known])) > 1 else 1.,
                'varying': len(set(values[known])) > 1,
                'missing_varying': bool(known.any() and not known.all())}
        for field in amenity.CATEGORIES:
            values = [pricing._category(r.get(field)) for r in normalized]
            levels = sorted(set(values)-{'__unknown__'})
            counts = np.array([values.count(v) for v in levels], dtype=float)
            basis = scipy.linalg.null_space(np.ones((1, len(levels)))) if levels else np.empty((0, 0))
            self.categories[field] = {'levels': levels, 'basis': basis.tolist(),
                'frequencies': (counts/counts.sum()).tolist() if len(counts) else [],
                'missing_varying': bool(levels and '__unknown__' in values)}
        matrix, names, scales = self.raw_features(train)
        self.active = np.ptp(matrix, axis=0) > 1e-12
        self.features = [n for n, use in zip(names, self.active) if use]
        self.prior_scales = np.asarray(scales)[self.active]
        self.means = matrix[:, self.active].mean(axis=0)
        self.support = {'rows': len(train), 'bathroom_composition_known': int(bathroom_values(train)[2].sum()),
            'dropped_constant_features': [n for n, use in zip(names, self.active) if not use],
            'matrix_rank': int(np.linalg.matrix_rank(matrix[:, self.active]-self.means)),
            'features': len(self.features)}
        if self.support['matrix_rank'] < len(self.features):
            raise ValueError('Feature matrix is rank deficient; revise construction before fitting')

    def raw_features(self, data):
        cols, names, scales = [], [], []
        def add(name, value, scale=.2):
            names.append(name); cols.append(np.asarray(value, dtype=float)); scales.append(scale)
        for i in range(5):
            add(f'bedrooms_gt_{i}', data.bedrooms.gt(i), .25)
        full, half, known = bathroom_values(data)
        total = data.bathrooms.to_numpy(float)
        # Identical bathroom measurement mask across specifications makes comparisons matched.
        if self.spec == 'linear_total':
            add('bathrooms_above_one', np.where(known, total-1, 0), .25)
        elif self.spec == 'incremental_total':
            for threshold in np.arange(1, 5, .5):
                add(f'bathrooms_gt_{threshold:g}', known & (total > threshold), .25)
        else:
            for threshold in range(1, 5):
                add(f'full_bathrooms_gt_{threshold}', known & (full > threshold), .25)
            for threshold in range(2):
                add(f'half_bathrooms_gt_{threshold}', known & (half > threshold), .2)
            if self.spec == 'full_half_balance':
                add('full_bathroom_shortfall', np.where(known, np.maximum(data.bedrooms-full, 0), 0), .2)
        add('bathroom_composition_unknown', ~known)
        area = data.square_feet.to_numpy(float)
        medians = data.bedrooms.map(lambda b: self.time.size_medians.get(str(int(b)), self.time.size_default)).to_numpy()
        present = np.isfinite(area) & (area > 0)
        add('log_size_within_bedrooms', np.log(np.where(present, area, medians)/medians), .35)
        add('size_missing', ~present)
        rows = [amenity.feature_record(r) for r in data.to_dict('records')]
        raw = [pricing._raw_features(r, '2000-01-01') for r in rows]
        for field, meta in self.numeric.items():
            vals = np.array([r[field] if r[field] is not None else np.nan for r in raw])
            observed = np.isfinite(vals)
            if meta['varying']:
                add(field, np.where(observed, (vals-meta['center'])/meta['scale'], 0), .15)
            if meta['missing_varying']:
                add(field+'.unknown', ~observed)
        for field, meta in self.categories.items():
            levels = meta['levels']
            if not levels:
                continue
            values = np.array([pricing._category(r.get(field)) for r in rows])
            observed = np.isin(values, levels)
            indicators = np.column_stack([values == level for level in levels]).astype(float)
            centered = np.where(observed[:, None], indicators-np.array(meta['frequencies']), 0)
            basis = np.array(meta['basis']).reshape(len(levels), len(levels)-1)
            contrasts = centered @ basis
            for j in range(contrasts.shape[1]):
                add(f'{field}.contrast_{j}', contrasts[:, j], .15)
            if meta['missing_varying']:
                add(field+'.unknown', ~observed)
        return np.column_stack(cols), names, scales

    def matrix(self, data):
        return self.raw_features(data)[0][:, self.active]-self.means

    def save(self, root):
        root = Path(root)
        self.time.save(root/'time-design.json')
        meta = {k: v for k, v in self.__dict__.items() if k != 'time'}
        for key in ('active', 'prior_scales', 'means'):
            meta[key] = meta[key].tolist()
        (root/'feature-design.json').write_text(json.dumps(meta, sort_keys=True, indent=2)+'\n')

    @classmethod
    def load(cls, root):
        result = cls.__new__(cls)
        result.__dict__.update(json.loads((Path(root)/'feature-design.json').read_text()))
        for key in ('active', 'prior_scales', 'means'):
            setattr(result, key, np.array(getattr(result, key)))
        result.time = base.Design.load(Path(root)/'time-design.json')
        return result


def build_model(train, design, prior_multiplier=1.):
    d = design.time
    a = d.arrays(train)
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
        mu = (alpha + pt.dot(design.matrix(train), beta)
              + pt.dot((d.time_matrix-d.time_center)[a['period']], trend_coefficients)
              + annual_drift*(d.linear_time-d.linear_center)[a['period']]
              + pt.dot((d.season_matrix-d.season_weights@d.season_matrix)[a['season']], season_coefficients)
              + building_effect[a['building']] + sigma_unit*unit_z[a['unit']])
        pm.StudentT('log_rent', nu=5., mu=mu, sigma=sigma, observed=np.log(train.asking_rent))
    return model
