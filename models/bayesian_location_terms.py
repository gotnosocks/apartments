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
    """Extra posterior variables loaded whole, with their non-sample dimensions."""
    version = protocol.get('version')
    if version == BEDROOM_TIME_EXPERIMENT:
        return {'bedroom_time': ('bedroom_group', 'period')}
    if version == STRUCTURE_EXPERIMENT:
        return {'bedroom_time': ('bedroom_group', 'period'), 'building_time_scale': ()}
    return {}


def lazy_variable_dims(protocol):
    """Extra posterior variables read one building slice at a time."""
    if protocol.get('version') == STRUCTURE_EXPERIMENT:
        return {'building_time_z': ('building_knot',)}
    return {}


def prepare(protocol, design, data):
    """Fit-constant reconstruction context from the verified training rows."""
    if protocol.get('version') != STRUCTURE_EXPERIMENT:
        return {}
    basis, _ = building_knots(design.time.periods, protocol['building_knot_years'])
    a = design.time.arrays(data)
    return {'basis': basis, 'centers': building_centers(a['building'], a['period'], len(design.time.buildings), basis)}


def expected_coords(protocol, design):
    version = protocol.get('version')
    coords = {}
    if version in (BEDROOM_TIME_EXPERIMENT, STRUCTURE_EXPERIMENT):
        coords.update(bedroom_group=list(BEDROOM_GROUPS),
                      period=[p.strftime('%Y-%m') for p in design.time.periods])
    if version == STRUCTURE_EXPERIMENT:
        basis, _ = building_knots(design.time.periods, protocol['building_knot_years'])
        coords['building_knot'] = list(range(len(design.time.buildings)*basis.shape[1]))
    return coords


def row_terms(protocol, draws, frame, design, select=None, context=None):
    """Named extra log contributions for a one-row frame; draws are flattened samples.

    ``select(name, start, stop)`` returns samples x (stop-start) draws of a lazy
    variable; ``context`` comes from ``prepare``.
    """
    version = protocol.get('version')
    if version not in (BEDROOM_TIME_EXPERIMENT, STRUCTURE_EXPERIMENT):
        return {}
    if len(frame) != 1:
        raise ValueError('Location terms are reconstructed one row at a time')
    a = design.time.arrays(frame)
    period = a['period'][0]
    terms = {'bedroom_time': draws['bedroom_time'][:, bedroom_group(frame.bedrooms.iloc[0]), period]}
    if version == STRUCTURE_EXPERIMENT:
        building = a['building'][0]
        if building < 0:
            raise ValueError('Building walk requires a fitted building')
        width = context['basis'].shape[1]
        z = select('building_time_z', building*width, (building+1)*width)
        terms['building_time'] = building_walk(z, draws['building_time_scale'], protocol['building_knot_years'],
                                               context['basis'][[period]], context['centers'][building])[:, 0]
    return terms


STRUCTURE_EXPERIMENT = 'observable-bayesian-structure-experiment-v1'


def building_knots(periods, years):
    """Piecewise-linear building-walk basis with knots every ``years`` (plus the last month)."""
    months = np.arange(len(periods), dtype=float)
    knots = list(np.arange(0., months[-1], 12*years))
    if knots[-1] != months[-1]:
        knots.append(months[-1])
    knots = np.asarray(knots)
    basis = np.zeros((len(periods), len(knots)))
    for k in range(len(knots)):
        unit = np.zeros(len(knots)); unit[k] = 1.
        basis[:, k] = np.interp(months, knots, unit)
    return basis, knots


def building_centers(building_index, period_index, n_buildings, basis):
    """Each building's training-month weights projected onto the knot basis (B x K)."""
    weights = np.zeros((n_buildings, basis.shape[0]))
    np.add.at(weights, (building_index, period_index), 1.)
    weights /= np.maximum(weights.sum(1, keepdims=True), 1.)
    return weights @ basis


def building_walk(z, scale, years, basis_rows, center):
    """Walk contribution for one building: z (samples x K), scale (samples,),
    basis_rows (rows x K), center (K,) -> (samples x rows)."""
    levels = scale[:, None]*np.sqrt(years)*np.cumsum(z, axis=1)
    return levels @ basis_rows.T - (levels @ center)[:, None]
