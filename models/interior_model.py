"""Experimental descriptive interior terms, separate from the serving runtime.

Values are source-supported advertised attributes. Missing text is unknown, not
physical absence. Known-only centering separates value contrasts from reporting
patterns; a constant known value cannot identify a physical feature premium.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse

from . import amenity_ablation as ablation
from . import minimal_rent_model as baseline

VERSION = 'chelsea-interior-encoder-v1'
FIELDS = ('advertised_ceiling_feet', 'advertised_levels',
          'floor_through_mention', 'skylight_mention')
VARIANTS = ('baseline', 'reporting', 'values')


def _values(data, field):
    """Reject malformed evidence rather than silently treating it as missing."""
    if field not in data:
        return np.full(len(data), np.nan)
    values = data[field].to_numpy(dtype=float, na_value=np.nan)
    known = values[~np.isnan(values)]
    if not np.isfinite(known).all():
        raise ValueError(f'Nonfinite interior evidence: {field}')
    if field.endswith('_mention'):
        valid = np.isin(known, [0., 1.]).all()
    elif field == 'advertised_levels':
        valid = ((known > 0) & (known == np.floor(known))).all()
    else:
        valid = (known > 0).all()
    if not valid:
        raise ValueError(f'Invalid interior evidence: {field}')
    return values


def encoder_class(variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown interior variant')

    class InteriorEncoder(ablation.encoder_class('full')):
        def __init__(self, train, unit_effect=True):
            super().__init__(train, unit_effect)
            self.interior_variant = variant
            self.interior_numeric = {}
            for field in FIELDS:
                values = _values(train, field)
                known = values[~np.isnan(values)]
                self.interior_numeric[field] = {
                    'known': len(known), 'unknown': len(values)-len(known),
                    'unique_values': len(np.unique(known)),
                    'center': float(known.mean()) if len(known) else 0.,
                    'scale': max(float(known.std()), 1e-8) if len(known) else 1.,
                    'minimum': float(known.min()) if len(known) else None,
                    'maximum': float(known.max()) if len(known) else None,
                }
            self.interior_features = []
            if variant != 'baseline':
                for field in FIELDS:
                    if variant == 'values':
                        self.interior_features.append(field)
                    self.interior_features.append(field+'.unknown')
            start = self.n_parameters
            self.n_parameters += len(self.interior_features)
            self.offsets['interior'] = (start, self.n_parameters)

        def matrix(self, data):
            core = super().matrix(data)
            columns = []
            if self.interior_variant != 'baseline':
                for field in FIELDS:
                    values = _values(data, field)
                    missing = np.isnan(values)
                    support = self.interior_numeric[field]
                    if self.interior_variant == 'values':
                        magnitude = np.zeros(len(data))
                        if support['unique_values'] > 1:
                            magnitude[~missing] = (values[~missing]-support['center'])/support['scale']
                        columns.append(magnitude)
                    columns.append(missing.astype(float))
            extra = (sparse.csr_matrix(np.column_stack(columns)) if columns
                     else sparse.csr_matrix((len(data), 0)))
            return sparse.hstack([core, extra], format='csr')

        def penalty(self, settings):
            # The base penalty respects final n_parameters. The existing amenity
            # wrapper appends a narrower block, so extend both families directly.
            core = baseline.Encoder.penalty(self, settings)
            blocks = [core]
            for family, penalty in [('amenities', settings['amenity_penalty']),
                                    ('interior', settings.get('interior_penalty', settings['amenity_penalty']))]:
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
                    'interior_variant': self.interior_variant,
                    'interior_numeric': self.interior_numeric,
                    'interior_features': self.interior_features}

    return InteriorEncoder


def load_saved(saved):
    """Reload one research fit from its JSON-compatible serialized dictionary."""
    metadata = saved['encoder']
    if metadata.get('model_version') != VERSION:
        raise ValueError('Unsupported interior encoder version')
    cls = encoder_class(metadata['interior_variant'])
    encoder = cls.__new__(cls)
    for key, value in metadata.items():
        setattr(encoder, key, value)
    encoder.periods = pd.DatetimeIndex(pd.to_datetime(metadata['periods']))
    beta = np.asarray(saved['beta'], dtype=float)
    center = float(saved['center'])
    if beta.shape != (encoder.n_parameters,) or not np.isfinite(beta).all() or not np.isfinite(center):
        raise ValueError('Invalid saved interior fit coefficients')
    return {'encoder': encoder, 'beta': beta, 'center': center}


def contribution_contrasts(fitted):
    """Conditional +1 contrasts with known evidence; never an unknown→known effect.

These describe the fitted linear association, not causal renovation values.
Holding building and unit effects fixed may also limit physical interpretation.
"""
    encoder = fitted['encoder']
    start, _ = encoder.offsets['interior']
    results = []
    for field, unit in [('advertised_ceiling_feet', 'foot'), ('advertised_levels', 'level')]:
        support = encoder.interior_numeric[field]
        supported = encoder.interior_variant == 'values' and support['unique_values'] > 1
        effect = (float(fitted['beta'][start+encoder.interior_features.index(field)])/support['scale']
                  if supported else None)
        results.append({'field': field, 'change': 1., 'unit': unit, 'supported': supported,
                        'log_rent_change': effect,
                        'rent_percent_change': float(100*np.expm1(effect)) if supported else None,
                        'support': support,
                        'interpretation': 'conditional advertised-value association; known-to-known; not causal',
                        'caution': 'A +1 change beyond observed bounds is extrapolation.'})
    return results
