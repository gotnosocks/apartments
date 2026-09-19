"""Compare the bounded reported-laundry split with its accepted parent fit.

Posterior intervals are kept within each fit. Between-fit changes are descriptive
differences of summaries, never paired draws or causal facility premiums.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from apartments import laundry_floor_split as split
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_category_contrasts as categories
from . import bayesian_feature_report as report
from . import bayesian_feature_sensitivity as common
from . import bayesian_source_sensitivity as source
from .bayesian_feature_design_v2 import load_design

VERSION = 'bounded-laundry-floor-fit-comparison-v1'


def check_protocols(a, b):
    if (a.get('version') != 'observable-bayesian-floor-experiment-v4'
            or b.get('version') != a['version'] or a.get('source_version') != split.PARENT
            or b.get('source_version') != split.VERSION):
        raise ValueError('Expected accepted floor fit and bounded laundry split')
    variable = source.SOURCE_FIELDS | {'graph_verification', 'implementation_sha256'}
    if {k: v for k, v in a.items() if k not in variable} != {k: v for k, v in b.items() if k not in variable}:
        raise ValueError('Sampling, prior, floor, likelihood or environment settings changed')
    old, new = a['implementation_sha256'], b['implementation_sha256']
    if set(new)-set(old) != {'laundry_floor_split.py'} or not set(old) <= set(new):
        raise ValueError('Unexpected implementation inventory change')
    changed = {k for k in old if old[k] != new[k]}
    if changed - {'bayesian_feature_experiment_v3.py', 'reviewed_source_lineage.py'}:
        raise ValueError('Mathematical or sampler implementation changed')
    return sorted(changed)


def check_designs(a, b, before, after):
    names = [n for n in a.features if not n.startswith('laundry_type.contrast_')]
    if names != [n for n in b.features if not n.startswith('laundry_type.contrast_')]:
        raise ValueError('Nonlaundry feature inventory changed')
    matrices = [a.matrix(before), b.matrix(after)]
    for name in names:
        i, j = a.features.index(name), b.features.index(name)
        if (a.prior_scales[i] != b.prior_scales[j] or a.means[i] != b.means[j]
                or not np.array_equal(matrices[0][:, i], matrices[1][:, j])):
            raise ValueError('Nonlaundry column, centering or prior changed: '+name)
    for name in ('floor_levels', 'floor_thresholds', 'floor_support', 'numeric'):
        if getattr(a, name) != getattr(b, name):
            raise ValueError('Nonlaundry design metadata changed: '+name)
    if {k: v for k, v in a.categories.items() if k != 'laundry_type'} != {
            k: v for k, v in b.categories.items() if k != 'laundry_type'}:
        raise ValueError('Other categorical designs changed')
    return names


def category_result(directory, experiment, dataset, fit):
    _, files = _verified_bundle(directory, retain={'contrasts.json'})
    value = json.loads(files['contrasts.json'])
    expected = {k: digest(p/'complete.json') for k, p in
                [('fit', experiment/'fit'), ('protocol', experiment/'protocol'), ('source', dataset)]}
    if (value.get('version') != categories.VERSION or value.get('bindings') != expected
            or value.get('protocol_sha256') != fit['report']['protocol_sha256']
            or value.get('posterior_sha256') != fit['provenance']['fit_manifest']['files']['posterior.nc']
            or value.get('source_observations_sha256') != fit['protocol']['source_observations_sha256']
            or value.get('status') != 'all_supported_contrasts_converged'
            or value.get('all_joint_beta_draws') is not True
            or value.get('chains') != fit['protocol']['chains']
            or value.get('draws_per_chain') != fit['protocol']['draws']
            or value.get('design_features') != fit['design'].features):
        raise ValueError('Category posterior analysis differs from the completed fit')
    if any(not r['diagnostics']['acceptable'] or r['log_effect'] is None or r['percent_effect'] is None
           for r in value['contrasts']):
        raise ValueError('Category intervals did not pass convergence gates')
    return value


def movement_rows(before, after, rows):
    def index(values):
        result = {r['audit_id']: r for r in values}
        if len(result) != len(values): raise ValueError('Duplicate residual identity')
        return result
    a, b, source_rows = map(index, (before, after, rows))
    if a.keys() != b.keys() or a.keys() != source_rows.keys():
        raise ValueError('Residual/source membership differs')
    fixed = ('audit_id', 'unit_id', 'building', 'source_listing_id', 'period', 'asking_rent')
    result = []
    for key, row in source_rows.items():
        if any(a[key][k] != row[k] or b[key][k] != row[k] for k in fixed):
            raise ValueError('Residual target or source identity differs')
        result.append({**{k: row[k] for k in fixed},
            'analysis_price_basis': row['analysis_price_basis'], 'candidate_laundry_type': row['laundry_type'],
            'source_changed': split.FIELD in row, 'reference': a[key], 'candidate': b[key],
            'fitted_rent_change': b[key]['fitted_rent']-a[key]['fitted_rent']})
    return sorted(result, key=lambda r: (-abs(r['fitted_rent_change']), r['audit_id']))


def summarize_slice(rows):
    if not rows: return {'rows': 0}
    return {'rows': len(rows), 'units': len({r['unit_id'] for r in rows}),
        'reference_median_absolute_log_residual': float(np.median([abs(r['reference']['residual_log']) for r in rows])),
        'candidate_median_absolute_log_residual': float(np.median([abs(r['candidate']['residual_log']) for r in rows])),
        'reference_median_signed_log_residual': float(np.median([r['reference']['residual_log'] for r in rows])),
        'candidate_median_signed_log_residual': float(np.median([r['candidate']['residual_log'] for r in rows])),
        'median_absolute_fitted_change': float(np.median([abs(r['fitted_rent_change']) for r in rows])),
        'maximum_absolute_fitted_change': float(max(abs(r['fitted_rent_change']) for r in rows))}


def group_changes(a, b):
    before = {(r['kind'], r['id']): r for r in a}
    after = {(r['kind'], r['id']): r for r in b}
    if len(before) != len(a) or len(after) != len(b) or before.keys() != after.keys():
        raise ValueError('Group-effect identities differ')
    return sorted([{'kind': kind, 'id': identity,
        'log_effect': common.interval_change(before[(kind, identity)]['log_effect'], after[(kind, identity)]['log_effect'])}
        for kind, identity in before], key=lambda r: (-abs(r['log_effect']['median_change']), r['kind'], r['id']))


def run(reference, candidate, reference_dataset, candidate_dataset, reference_categories, candidate_categories, output):
    experiments = list(map(Path, (reference, candidate)))
    datasets = list(map(Path, (reference_dataset, candidate_dataset)))
    bundles = [_verified_bundle(p, retain={'observations.jsonl'}) for p in datasets]
    rows = [report.jsonl(files['observations.jsonl']) for _, files in bundles]
    parent, restored = split.parent_rows(bundles[1][0], rows[1])
    if parent != bundles[0][0] or restored != rows[0]: raise ValueError('Exact source parent differs')
    fits, data = [], []
    for experiment, dataset, records in zip(experiments, datasets, rows, strict=True):
        verified, provenance = report.build_report(experiment, dataset)
        protocol = json.loads(common.bound_bytes(experiment/'protocol', 'protocol.json', provenance['protocol_manifest']))
        reconstruction = source.verify_design(experiment, dataset, protocol, provenance)
        frame = pd.DataFrame(records)
        frame.period = pd.to_datetime(frame.period); frame.square_feet = pd.to_numeric(frame.square_feet, errors='coerce')
        data.append(frame)
        fits.append({'report': verified, 'protocol': protocol, 'provenance': provenance,
            'design': load_design(experiment/'fit', frame, protocol), 'reconstruction': reconstruction,
            **{key: report.jsonl(common.bound_bytes(experiment/'fit', filename, provenance['fit_manifest']))
               for key, filename in [('residuals', 'residuals.jsonl'), ('groups', 'group-effects.jsonl')]}})
    a, b = fits
    changed_code = check_protocols(a['protocol'], b['protocol'])
    other_columns = check_designs(a['design'], b['design'], *data)
    for name in ('time-design.json', 'time-design.npz'):
        if a['provenance']['fit_manifest']['files'][name] != b['provenance']['fit_manifest']['files'][name]:
            raise ValueError('Saved time design changed')
    category_outputs = [category_result(directory, experiment, dataset, fit) for directory, experiment, dataset, fit in
        zip((reference_categories, candidate_categories), experiments, datasets, fits, strict=True)]
    cats = [{r['id']: r for r in value['contrasts']} for value in category_outputs]
    shared = [{'id': key, 'field': cats[0][key]['field'],
        'percent_effect': common.interval_change(cats[0][key]['percent_effect'], cats[1][key]['percent_effect'])}
        for key in sorted(cats[0].keys() & cats[1].keys())]
    new = [cats[1][key] for key in sorted(cats[1].keys()-cats[0].keys())]
    if cats[0].keys()-cats[1].keys() or len(new) != 2 or any(r['field'] != 'laundry_type' for r in new):
        raise ValueError('Unexpected category contrast inventory change')
    movements = movement_rows(a['residuals'], b['residuals'], rows[1])
    groups = group_changes(a['groups'], b['groups'])
    affected_buildings = {r['building'] for r in movements if r['source_changed']}
    current = [r for r in movements if r['analysis_price_basis'] == 'current_capture_gross_ask']
    slices = {'all': movements, 'changed': [r for r in movements if r['source_changed']], 'current': current,
        'unchanged': [r for r in movements if not r['source_changed']]}
    by_building = [{'building': building, **summarize_slice([r for r in movements if r['building'] == building])}
                   for building in sorted(affected_buildings)]
    result = {'version': VERSION, 'cohort': b['report']['cohort'], 'changed_source_rows': len(slices['changed']),
        'verified_nonlaundry_columns': other_columns, 'changed_loader_implementations': changed_code,
        'fits': [{'protocol': f['protocol'], 'diagnostics': f['report']['diagnostics'],
                  'design_reconstruction': f['reconstruction']} for f in fits],
        'residual_slices': {k: summarize_slice(v) for k, v in slices.items()},
        'common_category_contrasts': shared, 'new_category_contrasts': new,
        'largest_current_movements': current[:10], 'affected_building_residuals': by_building,
        'affected_building_effects': [g for g in groups if g['kind'] == 'building' and g['id'] in affected_buildings],
        'largest_building_effect_movements': [g for g in groups if g['kind'] == 'building'][:20],
        'largest_unit_effect_movements': [g for g in groups if g['kind'] == 'unit'][:20],
        'limitations': [common.LIMITATION, 'Reported same-floor access versus generic building access is not a physical-access premium.',
            'The category family has an additional dimension and different centering. Nonlaundry columns/priors are unchanged.',
            'All residuals are in-sample review signals. Improved residuals alone do not justify adding the factor.',
            'The Thomas Eddy and 101 West 23rd Street supply 82.4% of newly classified observations.'],
        'main_selection_changed': False}
    paths = [Path(module.__file__) for module in (split, report, common, source, categories)] + [Path(__file__)]
    publish_bundle(output, {'comparison.json': canonical(result)+'\n',
        'residual-movements.jsonl': ''.join(canonical(r)+'\n' for r in movements),
        'group-movements.jsonl': ''.join(canonical(r)+'\n' for r in groups),
        **{p.name: p.read_text() for p in paths}},
        {'version': VERSION, 'fits': [value['bindings'] for value in category_outputs],
         'category_manifests': [digest(Path(p)/'complete.json') for p in (reference_categories, candidate_categories)]})
    print(canonical({'residual_slices': result['residual_slices'], 'new_category_contrasts': new}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'reference_dataset', 'candidate_dataset', 'reference_categories', 'candidate_categories', 'output'):
        parser.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    with threadpool_limits(limits=1, user_api='blas'): run(**vars(parser.parse_args()))
