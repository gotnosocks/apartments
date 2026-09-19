"""Regularized natural cubic floor curve; all nonfloor features stay unchanged."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.linalg import null_space

from . import bayesian_feature_model as reference
from .bayesian_floor_increment_design import listed_floor_values, _support

VERSION = 'regularized-listed-floor-spline-design-v1'
INTERIOR_KNOTS = (5., 10., 20., 35.)


def knot_specification(levels):
    values = np.asarray(levels, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all() or not np.array_equal(values, np.unique(values)):
        raise ValueError('Spline requires at least two distinct finite observed floor levels')
    low, high = float(values[0]), float(values[-1])
    knots = [low, *[v for v in INTERIOR_KNOTS if low < v < high], high]
    return knots, 2. if low <= 2. <= high else low


def policy():
    return {
        'source': 'listed_floor, falling back to advertised_floor; label proxies are not physical height',
        'basis': 'Natural cubic interpolation of zero-sum knot heights, anchored at reference floor; no monotonicity constraint',
        'knots': 'Observed endpoints plus prespecified interior labels 5, 10, 20, 35 strictly inside the observed range',
        'prior': 'Independent equal-scale Normal coefficients on orthonormal zero-sum knot-height contrasts; no learned smoothness hierarchy',
        'unknown': 'Zero raw spline coordinates plus a separate unknown indicator when varying',
        'unseen_known_levels': 'Interpolation within fitted range allowed; extrapolation outside observed endpoints rejected',
        'interpretation': 'Shared smooth floor association conditional on other features and group effects; no causal or physical-height claim',
    }


class FeatureDesign(reference.FeatureDesign):
    def __init__(self, train, spec='full_half_balance', *, floor_prior_scale=.10):
        if isinstance(floor_prior_scale, (bool, np.bool_)) or not np.isfinite(floor_prior_scale) or floor_prior_scale <= 0:
            raise ValueError('Floor prior scale must be finite and positive')
        values = listed_floor_values(train)
        self.version = VERSION
        self.floor_levels = np.unique(values[np.isfinite(values)]).tolist()
        self.floor_knots, self.floor_reference = knot_specification(self.floor_levels)
        self.floor_basis = null_space(np.ones((1, len(self.floor_knots)))).tolist()
        self.floor_prior_scale = float(floor_prior_scale)
        self.floor_policy = policy()
        self.floor_support = _support(train, values, self.floor_levels)
        for row in self.floor_support['adjacent_supported_contrasts']:
            row.pop('feature')
            row['interpretation'] = 'Observed endpoint support for a shared smooth curve, not an independent floor increment'
        super().__init__(train, spec)
        self.numeric.pop('listed_floor', None)
        self.numeric_order = list(self.numeric)
        self.category_order = list(self.categories)
        _, names, scales = self.raw_features(train.iloc[:1])
        self.raw_feature_names = names
        self.raw_prior_scales = np.asarray(scales, dtype=float)
        self._validate_saved_structure()

    def floor_coordinates(self, values):
        values = np.asarray(values, dtype=float)
        if values.ndim != 1:
            raise ValueError('Floor values must be a vector')
        known = np.isfinite(values)
        if np.isinf(values).any() or np.any(values[known] < self.floor_knots[0]) or np.any(values[known] > self.floor_knots[-1]):
            raise ValueError('Floor extrapolation outside fitted range is not supported')
        spline = CubicSpline(self.floor_knots, np.asarray(self.floor_basis), bc_type='natural', extrapolate=False)
        result = np.zeros((len(values), len(self.floor_knots)-1))
        result[known] = spline(values[known]) - spline(self.floor_reference)
        return result

    def raw_features(self, data):
        matrix, names, scales = super().raw_features(data)
        keep = [i for i, name in enumerate(names) if name not in ('listed_floor', 'listed_floor.unknown')]
        values = listed_floor_values(data)
        coordinates = self.floor_coordinates(values)
        columns = [matrix[:, i] for i in keep]
        names = [names[i] for i in keep]
        scales = [scales[i] for i in keep]
        for index in range(coordinates.shape[1]):
            columns.append(coordinates[:, index])
            names.append(f'listed_floor_spline_{index}')
            scales.append(self.floor_prior_scale)
        columns.append((~np.isfinite(values)).astype(float))
        names.append('listed_floor.unknown')
        scales.append(.2)
        return np.column_stack(columns), names, scales

    def contrast_vector(self, low, high):
        if not np.isfinite([low, high]).all():
            raise ValueError('Floor contrast requires finite endpoints')
        coordinates = self.floor_coordinates([low, high])
        result = np.zeros(len(self.features))
        for index, value in enumerate(coordinates[1]-coordinates[0]):
            name = f'listed_floor_spline_{index}'
            if name not in self.features:
                raise ValueError('Spline coordinate missing from fitted feature support')
            result[self.features.index(name)] = value
        return result

    def _validate_saved_structure(self):
        if self.version != VERSION or self.spec not in reference.SPECS:
            raise ValueError('Unsupported spline design version or feature specification')
        knots, anchor = knot_specification(self.floor_levels)
        expected_basis = null_space(np.ones((1, len(knots))))
        if (self.floor_knots != knots or self.floor_reference != anchor
                or not np.array_equal(np.asarray(self.floor_basis), expected_basis)
                or self.floor_policy != policy()):
            raise ValueError('Saved spline knots, basis, reference or policy differs')
        if not np.isfinite(self.floor_prior_scale) or self.floor_prior_scale <= 0:
            raise ValueError('Invalid floor prior scale')
        suffix = [f'listed_floor_spline_{i}' for i in range(len(knots)-1)] + ['listed_floor.unknown']
        if self.raw_feature_names[-len(suffix):] != suffix or 'listed_floor' in self.raw_feature_names:
            raise ValueError('Saved spline feature inventory differs')
        if (len(set(self.raw_feature_names)) != len(self.raw_feature_names)
                or self.active.dtype != np.dtype(bool)
                or self.active.shape != (len(self.raw_feature_names),)
                or [n for n, active in zip(self.raw_feature_names, self.active) if active] != self.features
                or self.raw_prior_scales.shape != self.active.shape
                or not np.array_equal(self.prior_scales, self.raw_prior_scales[self.active])
                or not np.array_equal(self.raw_prior_scales[-len(suffix):], [self.floor_prior_scale]*(len(knots)-1)+[.2])
                or not np.isfinite(self.prior_scales).all() or np.any(self.prior_scales <= 0)
                or self.means.shape != (len(self.features),) or not np.isfinite(self.means).all()):
            raise ValueError('Saved spline columns, priors or centering differ')
        if (self.numeric_order != [n for n in reference.amenity.NUMERIC if n != 'listed_floor']
                or self.category_order != list(reference.amenity.CATEGORIES)
                or set(self.numeric) != set(self.numeric_order) or set(self.categories) != set(self.category_order)):
            raise ValueError('Saved nonfloor feature inventory differs')

    def save(self, root):
        self._validate_saved_structure()
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.time.save(root/'time-design.json')
        metadata = {k: v for k, v in self.__dict__.items() if k != 'time'}
        for key in ('active', 'prior_scales', 'means', 'raw_prior_scales'):
            metadata[key] = metadata[key].tolist()
        (root/'feature-design.json').write_text(json.dumps(metadata, sort_keys=True, indent=2, allow_nan=False)+'\n')

    @classmethod
    def load(cls, root):
        root = Path(root)
        result = cls.__new__(cls)
        result.__dict__.update(json.loads((root/'feature-design.json').read_text()))
        for key in ('active', 'prior_scales', 'means', 'raw_prior_scales'):
            setattr(result, key, np.asarray(getattr(result, key)))
        result._validate_saved_structure()
        result.numeric = {key: result.numeric[key] for key in result.numeric_order}
        result.categories = {key: result.categories[key] for key in result.category_order}
        result.time = reference.base.Design.load(root/'time-design.json')
        return result
