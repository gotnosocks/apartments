"""Research outdoor-type contrasts conditional on the interior values model.

Unmentioned outdoor space is unknown, never physical absence. Known categories
are frequency centered among known training observations, so their contrast block
cannot supply a second known-versus-unknown intercept. Rare categories are pooled
using training counts only. A known scoring category absent from training has
zero known contrast and zero unknown flag; that fallback is not estimated support.
"""
from __future__ import annotations

from collections import Counter
import re

import numpy as np
import pandas as pd
from scipy import sparse

from . import interior_model as interior
from . import minimal_rent_model as baseline

VERSION = 'chelsea-outdoor-encoder-v1'
FIELDS = ('private_outdoor_category', 'shared_outdoor_category')
OUTDOOR = FIELDS
VARIANTS = ('interior', 'reporting', 'types')
MIN_CATEGORY_ROWS = 25


def _values(data, field):
    if field not in data:
        return [None]*len(data)
    result = []
    for value in data[field]:
        if value is None or value is pd.NA or (isinstance(value, (float, np.floating)) and np.isnan(value)):
            result.append(None)
            continue
        if not isinstance(value, str):
            raise ValueError(f'Invalid outdoor category: {field}')
        if value != 'unspecified':
            tokens = value.split('+')
            if tokens != sorted(set(tokens)) or any(not re.fullmatch(r'[A-Z][A-Z_]*', token) for token in tokens):
                raise ValueError(f'Invalid outdoor category: {field}')
        result.append(value)
    return result


def encoder_class(variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown outdoor variant')

    class OutdoorEncoder(interior.encoder_class('values')):
        def __init__(self, train, unit_effect=True):
            super().__init__(train, unit_effect)
            self.outdoor_variant = variant
            self.outdoor_min_category_rows = MIN_CATEGORY_ROWS
            self.outdoor_category_counts = {}
            self.outdoor_category_mapping = {}
            self.outdoor_categories = {}
            self.outdoor_category_centers = {}
            self.outdoor_support = {}
            self.outdoor_features = []
            for field in FIELDS:
                values = _values(train, field)
                counts = dict(sorted(Counter(value for value in values if value is not None).items()))
                mapping = {value: value if count >= MIN_CATEGORY_ROWS else '__rare__'
                           for value, count in counts.items()}
                pooled = Counter()
                for value, count in counts.items():
                    pooled[mapping[value]] += count
                known = sum(counts.values())
                self.outdoor_category_counts[field] = counts
                self.outdoor_category_mapping[field] = mapping
                self.outdoor_categories[field] = sorted(pooled)
                self.outdoor_category_centers[field] = {value: pooled[value]/known for value in sorted(pooled)}
                self.outdoor_support[field] = {'known': known, 'unknown': len(values)-known,
                                              'raw_categories': len(counts), 'pooled_categories': len(pooled)}
                if variant == 'types':
                    self.outdoor_features.extend(f'{field}={value}' for value in sorted(pooled))
                if variant != 'interior':
                    self.outdoor_features.append(field+'.unknown')
            start = self.n_parameters
            self.n_parameters += len(self.outdoor_features)
            self.offsets['outdoor'] = (start, self.n_parameters)

        def matrix(self, data):
            core = super().matrix(data)
            columns = []
            if self.outdoor_variant != 'interior':
                for field in FIELDS:
                    values = _values(data, field)
                    mapping = self.outdoor_category_mapping[field]
                    pooled = [mapping.get(value) for value in values]
                    if self.outdoor_variant == 'types':
                        for category in self.outdoor_categories[field]:
                            center = self.outdoor_category_centers[field][category]
                            columns.append(np.asarray([float(value == category)-center if value is not None else 0.
                                                       for value in pooled]))
                    columns.append(np.asarray([float(value is None) for value in values]))
            extra = (sparse.csr_matrix(np.column_stack(columns)) if columns
                     else sparse.csr_matrix((len(data), 0)))
            return sparse.hstack([core, extra], format='csr')

        def penalty(self, settings):
            # Base ridge/smoothing uses the final width. Add each derived family
            # directly; calling inherited append-only penalties would narrow it.
            blocks = [baseline.Encoder.penalty(self, settings)]
            for family in ('amenities', 'interior', 'outdoor'):
                key = 'amenity_penalty' if family == 'amenities' else family+'_penalty'
                penalty = settings.get(key, settings['amenity_penalty'])
                if not np.isfinite(penalty) or penalty < 0:
                    raise ValueError(f'Invalid {family} penalty')
                start, stop = self.offsets[family]
                count = stop-start
                if count:
                    blocks.append(sparse.csr_matrix(
                        (np.full(count, np.sqrt(penalty)), (np.arange(count), np.arange(start, stop))),
                        shape=(count, self.n_parameters)))
            return sparse.vstack(blocks, format='csr')

        def metadata(self):
            return {**super().metadata(), 'model_version': VERSION,
                    **{name: getattr(self, name) for name in (
                        'outdoor_variant', 'outdoor_min_category_rows', 'outdoor_category_counts',
                        'outdoor_category_mapping', 'outdoor_categories', 'outdoor_category_centers',
                        'outdoor_support', 'outdoor_features')}}

    return OutdoorEncoder


def load_saved(saved):
    metadata = saved['encoder']
    if metadata.get('model_version') != VERSION:
        raise ValueError('Unsupported outdoor encoder version')
    cls = encoder_class(metadata['outdoor_variant'])
    encoder = cls.__new__(cls)
    for key, value in metadata.items():
        setattr(encoder, key, value)
    encoder.periods = pd.DatetimeIndex(pd.to_datetime(metadata['periods']))
    beta = np.asarray(saved['beta'], dtype=float)
    center = float(saved['center'])
    if beta.shape != (encoder.n_parameters,) or not np.isfinite(beta).all() or not np.isfinite(center):
        raise ValueError('Invalid saved outdoor fit coefficients')
    return {'encoder': encoder, 'beta': beta, 'center': center}


def category_contrasts(fitted):
    """Known-to-known conditional associations, not private-space presence premiums."""
    encoder = fitted['encoder']
    start, _ = encoder.offsets['outdoor']
    results = []
    for field, before, after in [('private_outdoor_category', 'BALCONY', 'TERRACE'),
                                 ('private_outdoor_category', 'BALCONY', 'GARDEN'),
                                 ('shared_outdoor_category', 'ROOF_DECK', 'GARDEN')]:
        counts = encoder.outdoor_category_counts[field]
        supported = encoder.outdoor_variant == 'types' and all(
            counts.get(value, 0) >= encoder.outdoor_min_category_rows for value in (before, after))
        effect = None
        if supported:
            indices = [start+encoder.outdoor_features.index(f'{field}={value}') for value in (before, after)]
            effect = float(fitted['beta'][indices[1]]-fitted['beta'][indices[0]])
        results.append({'field': field, 'before': before, 'after': after, 'supported': supported,
                        'log_rent_change': effect,
                        'rent_percent_change': float(100*np.expm1(effect)) if supported else None,
                        'support': {value: counts.get(value, 0) for value in (before, after)},
                        'interpretation': 'conditional advertised-type association; known-to-known; not causal',
                        'caution': 'Outdoor size, quality and selection into reporting remain uncontrolled.'})
    return results
