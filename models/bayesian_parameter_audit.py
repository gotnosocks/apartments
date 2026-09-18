"""Source-bound support and representation audit; no fitting or parameter selection.

Variation within a group is descriptive support, not causal identification.
Unknown indicators are explicitly distinguished from observed physical contrasts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from . import bayesian_feature_experiment_v3 as experiment
from . import bayesian_feature_model as features
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle

VERSION = 'bayesian-parameter-support-audit-v1'


def support(data):
    return {'rows': len(data), 'units': int(data.unit_id.nunique()),
            'buildings': int(data.building.nunique())}


def variation(values, groups):
    """Group-centered sum of squares divided by total, and varying group count."""
    frame = pd.DataFrame({'value': np.asarray(values, dtype=float),
                          'group': np.asarray(groups)})
    frame = frame[np.isfinite(frame.value)]
    if frame.empty:
        return {'known_groups': 0, 'varying_groups': 0, 'within_ss_fraction': None}
    grouped = frame.groupby('group').value
    centered = frame.value-frame.value.mean()
    total = float(centered @ centered)
    within = frame.value-grouped.transform('mean')
    return {'known_groups': int(grouped.ngroups),
            'varying_groups': int((grouped.max()-grouped.min() > 1e-10).sum()),
            'within_ss_fraction': float(within @ within / total) if total > 1e-20 else None}


def inventory(data, design):
    records = [features.amenity.feature_record(r) for r in data.to_dict('records')]
    raw = [features.pricing._raw_features(r, '2000-01-01') for r in records]
    measurements = {}
    for name in features.amenity.NUMERIC:
        values = np.array([r[name] if r[name] is not None else np.nan for r in raw], dtype=float)
        known = np.isfinite(values)
        levels = np.unique(values[known])
        measurements[name] = {'known': support(data.loc[known]), 'unknown': support(data.loc[~known]),
            'levels': levels.tolist(),
            'level_support': [{'value': float(level), **support(data.loc[values == level])} for level in levels],
            'known_within_building': variation(values, data.building),
            'known_within_unit': variation(values, data.unit_id),
            'physical_contrast_observed': bool(len(levels) > 1)}
    for name in features.amenity.CATEGORIES:
        values = np.array([features.pricing._category(r.get(name)) for r in records])
        levels = sorted(set(values)-{'__unknown__'})
        known = values != '__unknown__'
        pairs = []
        for i, left in enumerate(levels):
            for right in levels[i+1:]:
                a, b = data.loc[values == left], data.loc[values == right]
                pairs.append({'left': left, 'right': right,
                    'shared_buildings': len(set(a.building) & set(b.building)),
                    'shared_units': len(set(a.unit_id) & set(b.unit_id))})
        measurements[name] = {'known': support(data.loc[known]), 'unknown': support(data.loc[~known]),
            'levels': levels,
            'level_support': [{'value': level, **support(data.loc[values == level])} for level in levels],
            'pair_overlap': pairs}

    matrix = design.matrix(data)
    columns = []
    for index, name in enumerate(design.features):
        values = matrix[:, index]
        reporting = name.endswith('.unknown') or name in {'size_missing', 'bathroom_composition_unknown'}
        columns.append({'feature': name, 'role': 'reporting_nuisance' if reporting else 'physical_or_basis_term',
            'prior_sd': float(design.prior_scales[index]), 'distinct_encoded_values': len(np.unique(values)),
            'within_building': variation(values, data.building),
            'within_unit': variation(values, data.unit_id)})
    correlations = np.corrcoef(matrix, rowvar=False)
    pairs = [{'left': design.features[i], 'right': design.features[j],
              'correlation': float(correlations[i, j])}
             for i in range(len(design.features)) for j in range(i+1, len(design.features))
             if abs(correlations[i, j]) >= .8]
    floors = measurements['listed_floor']['levels']
    floor_values = np.array([r['listed_floor'] if r['listed_floor'] is not None else np.nan for r in raw])
    floor_pairs = []
    for low, high in zip(floors[:-1], floors[1:]):
        a, b = data.loc[floor_values == low], data.loc[floor_values == high]
        floor_pairs.append({'threshold': low, 'next_observed_floor': high,
            'gap': high-low, 'lower': support(a), 'upper': support(b),
            'shared_buildings': len(set(a.building) & set(b.building)),
            'shared_units': len(set(a.unit_id) & set(b.unit_id))})
    by_unit = data.groupby('unit_id').size()
    by_building = data.groupby('building').unit_id.nunique()
    return {'version': VERSION, 'cohort': support(data), 'features': columns,
        'measurements': measurements, 'floor_adjacent_observed_levels': floor_pairs,
        'high_absolute_correlations': pairs,
        'design': design.support,
        'groups': {'single_observation_units': int(by_unit.eq(1).sum()),
                   'single_unit_buildings': int(by_building.eq(1).sum()),
                   'unit_observation_quantiles': {str(q): float(by_unit.quantile(q)) for q in (0, .5, .9, 1)}},
        'time': {'first': str(data.period.min()), 'last': str(data.period.max()),
                 'months': len(design.time.periods),
                 'trend_coefficients': design.time.time_matrix.shape[1],
                 'season_coefficients': 11, 'annual_drift': True},
        'interpretation': [
            'Rows can repeat units and source advertisements; they are not independent physical comparisons.',
            'Within-group variation includes source inconsistency and reporting changes, not just real changes.',
            'Full feature-matrix rank does not identify feature allocation separately from building/unit effects.',
            'Positive-versus-unknown exposure evidence supports a reporting indicator, not a presence-versus-absence premium.',
            'This audit proposes scrutiny; it does not automatically include/drop terms or estimate new coefficients.']}


def run(dataset, output):
    data, source = experiment.load_data(dataset)
    with threadpool_limits(limits=1, user_api='blas'):
        design = features.FeatureDesign(data, 'full_half_balance')
        result = inventory(data, design)
    code = [Path(__file__), *experiment.implementation_paths()]
    hashes = {str(p.resolve().relative_to(Path(__file__).resolve().parents[1])): digest(p) for p in code}
    return publish_bundle(output, {'audit.json': canonical(result)+'\n',
        'bayesian_parameter_audit.py': Path(__file__).read_text()},
        {'version': VERSION, 'source_manifest_sha256': digest(Path(dataset)/'complete.json'),
         'source_observations_sha256': source['files']['observations.jsonl'],
         'implementation_sha256': hashes})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(canonical(run(args.dataset, args.output)))
