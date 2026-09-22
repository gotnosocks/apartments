"""Location terms beyond the frozen v3 mean, keyed by experiment version.

Readers that reconstruct mu (the main analysis page, counterfactuals) ask this
module which extra posterior variables a fit carries and how they enter a row's
latent median. Fits without extra terms return nothing, so older selections
reconstruct exactly as before.
"""
from __future__ import annotations

import numpy as np

BEDROOM_TIME_EXPERIMENT = 'observable-bayesian-bedroom-time-experiment-v1'
BEDROOM_GROUPS = ('studio', 'one_bedroom', 'two_bedroom', 'three_plus_bedroom')


def bedroom_group(bedrooms):
    value = float(bedrooms)
    if not np.isfinite(value) or value < 0 or value != int(value):
        raise ValueError('Bedroom-time term requires a nonnegative integer bedroom count')
    return min(int(value), len(BEDROOM_GROUPS)-1)


def variable_dims(protocol):
    """Extra posterior variables and their non-sample dimensions."""
    if protocol.get('version') == BEDROOM_TIME_EXPERIMENT:
        return {'bedroom_time': ('bedroom_group', 'period')}
    return {}


def expected_coords(protocol, design):
    if protocol.get('version') == BEDROOM_TIME_EXPERIMENT:
        return {'bedroom_group': list(BEDROOM_GROUPS),
                'period': [p.strftime('%Y-%m') for p in design.time.periods]}
    return {}


def row_terms(protocol, draws, frame, design):
    """Named extra log contributions for a one-row frame; draws are flattened samples."""
    if protocol.get('version') != BEDROOM_TIME_EXPERIMENT:
        return {}
    if len(frame) != 1:
        raise ValueError('Location terms are reconstructed one row at a time')
    period = design.time.arrays(frame)['period'][0]
    return {'bedroom_time': draws['bedroom_time'][:, bedroom_group(frame.bedrooms.iloc[0]), period]}
