"""Unfitted lower-floor interaction candidates over the unchanged floor design.

Known no/yes elevator claims receive -1/2 and +1/2 contrast weights; unknown
claims receive zero. That is a model allocation convention, not imputation of
physical access. The existing floor main effect is the midpoint of the two
known-access curves. No interaction is added for unsupported upper thresholds.
"""
import json
import math
from pathlib import Path

import numpy as np

from apartments import pricing
from apartments.corrections import canonical
from . import bayesian_floor_increment_design as floor

VERSION = 'lower-floor-elevator-interaction-design-v1'
THRESHOLDS = (2., 3., 4.)
MODES = ('pooled', 'separate')


def endpoint_support(data):
    values = floor.listed_floor_values(data)
    claims = np.asarray([pricing._boolean(floor.reference.amenity.feature_record(r).get('elevator'))
                         for r in data.to_dict('records')], dtype=object)
    return [{'floor': level, 'elevator': bool(access),
             'rows': int(np.sum((values == level) & (claims == access)))}
            for level in (2., 3., 4., 5.) for access in (0., 1.)]


def raw_interactions(data, mode):
    if mode not in MODES:
        raise ValueError('Choose pooled or separate lower-floor interactions')
    values = floor.listed_floor_values(data)
    known_floor = np.isfinite(values)
    claims = [pricing._boolean(floor.reference.amenity.feature_record(r).get('elevator'))
              for r in data.to_dict('records')]
    weights = np.array([0. if value is None else value-.5 for value in claims])
    matrix = np.column_stack([(known_floor & (values > k))*weights for k in THRESHOLDS])
    # Equal full-range prior variance for pooled and independent increments.
    return matrix if mode == 'separate' else matrix.sum(axis=1, keepdims=True)/math.sqrt(len(THRESHOLDS))


def names(mode):
    if mode == 'pooled': return ['floor_elevator_pooled_2_to_5']
    if mode == 'separate': return [f'floor_elevator_gt_{k:g}' for k in THRESHOLDS]
    raise ValueError('Unknown floor interaction representation')


class FeatureDesign:
    """Composition keeps every existing base column, centering and prior intact."""

    def __init__(self, train, spec='full_half_balance', *, mode='pooled',
                 interaction_prior_scale=.15, floor_increment_prior_scale=.15):
        if (isinstance(interaction_prior_scale, bool) or not isinstance(interaction_prior_scale, (int, float))
                or not math.isfinite(interaction_prior_scale) or interaction_prior_scale <= 0):
            raise ValueError('Positive finite interaction prior scale required')
        self.base = floor.FeatureDesign(train, spec, floor_increment_prior_scale=floor_increment_prior_scale)
        self.mode = mode
        self.interaction_prior_scale = float(interaction_prior_scale)
        if not {2., 3., 4., 5.} <= set(self.base.floor_levels):
            raise ValueError('All lower-floor endpoints 2, 3, 4, 5 require observed support')
        self.endpoint_support = endpoint_support(train)
        if any(r['rows'] == 0 for r in self.endpoint_support):
            raise ValueError('Every lower-floor endpoint requires both known elevator states')
        raw = raw_interactions(train, mode)
        self.interaction_means = raw.mean(axis=0)
        self._validate()

    def _validate(self):
        expected = len(names(self.mode))
        endpoints = [(level, access) for level in (2., 3., 4., 5.) for access in (False, True)]
        if (not {2., 3., 4., 5.} <= set(self.base.floor_levels)
                or self.interaction_means.shape != (expected,)
                or not np.isfinite(self.interaction_means).all()
                or isinstance(self.interaction_prior_scale, bool)
                or not math.isfinite(self.interaction_prior_scale) or self.interaction_prior_scale <= 0
                or [(r['floor'], r['elevator']) for r in self.endpoint_support] != endpoints
                or any(type(r['rows']) is not int or r['rows'] <= 0 or type(r['elevator']) is not bool
                       for r in self.endpoint_support)):
            raise ValueError('Invalid saved interaction design')

    @property
    def features(self):
        return self.base.features+names(self.mode)

    @property
    def prior_scales(self):
        return np.r_[self.base.prior_scales, np.full(len(names(self.mode)), self.interaction_prior_scale)]

    @property
    def time(self):
        return self.base.time

    def matrix(self, data):
        # The base rejects unsupported known floor labels before extrapolation.
        return np.column_stack([self.base.matrix(data), raw_interactions(data, self.mode)-self.interaction_means])

    def save(self, root):
        root = Path(root)
        self._validate()
        self.base.save(root/'base-design')
        (root/'interaction-design.json').write_text(canonical({
            'version': VERSION, 'mode': self.mode, 'thresholds': list(THRESHOLDS),
            'interaction_prior_scale': self.interaction_prior_scale,
            'interaction_means': self.interaction_means.tolist(),
            'endpoint_support': self.endpoint_support,
            'features': self.features, 'prior_scales': self.prior_scales.tolist(),
            'allocation': 'Known no/yes weights -0.5/+0.5; unknown zero; pooled sum divided by sqrt(3).',
        })+'\n')

    @classmethod
    def load(cls, root):
        root = Path(root)
        saved = json.loads((root/'interaction-design.json').read_text())
        if saved.get('version') != VERSION or saved.get('thresholds') != list(THRESHOLDS):
            raise ValueError('Unsupported interaction design version or thresholds')
        result = cls.__new__(cls)
        result.base = floor.FeatureDesign.load(root/'base-design')
        result.mode = saved['mode']
        result.interaction_prior_scale = saved['interaction_prior_scale']
        result.interaction_means = np.asarray(saved['interaction_means'], dtype=float)
        result.endpoint_support = saved['endpoint_support']
        result._validate()
        if saved['features'] != result.features or not np.array_equal(saved['prior_scales'], result.prior_scales):
            raise ValueError('Saved interaction feature order or priors differ')
        return result


def floor_contrast_vector(design, template, lower, upper, elevator):
    """Total floor contribution at fixed access, including the base floor terms."""
    if elevator is not True and elevator is not False:
        raise ValueError('A floor/elevator contrast requires explicit known access')
    if lower not in design.base.floor_levels or upper not in design.base.floor_levels or lower >= upper:
        raise ValueError('Ordered supported floor endpoints required')
    a, b = template.iloc[[0]].copy(), template.iloc[[0]].copy()
    a['listed_floor'], b['listed_floor'] = lower, upper
    a['elevator'], b['elevator'] = elevator, elevator
    return (design.matrix(b)-design.matrix(a))[0]
