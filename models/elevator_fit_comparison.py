"""Compare exact PyMC fits across reversible elevator source corrections."""
import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments import elevator_corrections as correction
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import quarantine_fit_comparison as q, bayesian_category_contrasts as categories

VERSION = 'reviewed-elevator-fit-comparison-v1'


def check_protocols(a, b):
    if (a.get('version') != q.floors.V4 or b.get('version') != q.floors.V4
            or a.get('source_version') != correction.PARENT or b.get('source_version') != correction.VERSION
            or a.get('residual_scale') != 'shared' or b.get('residual_scale') != 'shared'):
        raise ValueError('Expected shared-noise floor fits before and after elevator corrections')
    if not q.disk.verify_protocol(a) or not q.disk.verify_protocol(b):
        raise ValueError('Durable fitted protocols required')
    variable = q.source.SOURCE_FIELDS | {'graph_verification', 'implementation_sha256'}
    if {k: v for k, v in a.items() if k not in variable} != {k: v for k, v in b.items() if k not in variable}:
        raise ValueError('Sampler, model, prior, floor support or numerical environment changed')
    if any(a.get(k) != b.get(k) for k in ('rows', 'units', 'buildings')):
        raise ValueError('Elevator correction changed cohort membership')
    old, new = a['implementation_sha256'], b['implementation_sha256']
    if (not old.keys() <= new.keys() or new.keys()-old.keys() != {'elevator_corrections.py'}):
        raise ValueError('Unexpected implementation inventory change')
    changed = {k for k in old if old[k] != new[k]}
    if changed - {'bayesian_feature_experiment_v3.py', 'reviewed_source_lineage.py'}:
        raise ValueError('Mathematical or sampling implementation changed')
    return sorted(changed)


def verify_revision(reference, candidate):
    bundles = [_verified_bundle(p, retain={'observations.jsonl', correction.SIDECAR}) for p in (reference, candidate)]
    before, after = [q.report.jsonl(f['observations.jsonl']) for _, f in bundles]
    if correction.SIDECAR not in bundles[1][1]:
        raise ValueError('Missing elevator correction sidecar')
    changes = q.report.jsonl(bundles[1][1][correction.SIDECAR])
    if correction.parent_rows(bundles[1][0], after, changes) != (bundles[0][0], before):
        raise ValueError('Elevator corrections do not restore the exact reference source')
    return before, after, changes


def check_designs(a, b):
    left, right = a['design'], b['design']
    if left.features != right.features or not np.array_equal(left.prior_scales, right.prior_scales):
        raise ValueError('Feature support or coefficient prior scales changed')
    unaffected = [i for i, name in enumerate(left.features) if name not in ('elevator', 'elevator.unknown')]
    if (left.categories != right.categories
            or {k: v for k, v in left.numeric.items() if k != 'elevator'} !=
               {k: v for k, v in right.numeric.items() if k != 'elevator'}
            or not np.allclose(left.matrix(a['data'])[:, unaffected], right.matrix(b['data'])[:, unaffected], rtol=0, atol=1e-12)):
        raise ValueError('Source correction changed unrelated feature columns')


def elevator_vectors(design, data):
    """Known endpoints and reporting-state changes in the fitted design units."""
    required = ('elevator', 'elevator.unknown')
    if any(k not in design.features for k in required):
        raise ValueError('Elevator value and missingness columns required')
    meta = design.numeric['elevator']
    center, scale = meta['center'], meta['scale']
    if not np.isfinite([center, scale]).all() or not 0 <= center <= 1 or scale <= 0:
        raise ValueError('Invalid elevator normalization')
    output = []
    for before, after, label in [(False, True, 'no->yes'), (False, None, 'no->unknown'), (True, None, 'yes->unknown')]:
        left, right = data.iloc[[0]].copy(), data.iloc[[0]].copy()
        left['elevator'], right['elevator'] = before, after
        vector = (design.matrix(right)-design.matrix(left))[0]
        expected = np.zeros(len(design.features))
        encoded = lambda value: 0 if value is None else (int(value)-center)/scale
        expected[design.features.index('elevator')] = encoded(after)-encoded(before)
        expected[design.features.index('elevator.unknown')] = int(after is None)-int(before is None)
        if not np.allclose(vector, expected, rtol=0, atol=1e-12):
            raise ValueError('Elevator scenario altered unrelated features')
        endpoint = lambda value: data.loc[data.elevator.isna() if value is None else data.elevator.eq(value)]
        output.append({'id': 'elevator:'+label, 'before': before, 'after': after,
            'interpretation': 'Conditional known-elevator association' if after is not None else
                              'Reporting-state contrast; unknown does not mean no elevator',
            'design_vector': vector.tolist(),
            'support_before': categories.support(endpoint(before)), 'support_after': categories.support(endpoint(after)),
            'raw_contrast_prior_sd': float(np.linalg.norm(vector*design.prior_scales))})
    return output


def elevator_contrasts(fit):
    design, protocol = fit['design'], fit['protocol']
    contrasts = elevator_vectors(design, fit['data'])
    for item in contrasts:
        item['raw_contrast_prior_sd'] *= protocol['prior_multiplier']
    with xr.open_dataset(fit['root']/'fit/posterior.nc', group='posterior', engine='h5netcdf', cache=False) as p:
        if (p.beta.dims != ('chain', 'draw', 'feature') or p.feature.values.tolist() != design.features
                or p.sizes['chain'] != protocol['chains'] or p.sizes['draw'] != protocol['draws']):
            raise ValueError('Posterior beta dimensions or coordinates differ')
        results, _ = categories.calculate(p.beta.values, contrasts)
    if not all(r['diagnostics']['acceptable'] for r in results):
        raise ValueError('Elevator joint contrasts fail convergence')
    return results


def build_comparison(reference, candidate, reference_dataset, candidate_dataset, reference_categories, candidate_categories):
    before, after, changes = verify_revision(reference_dataset, candidate_dataset)
    fits = q.load_fits(reference, candidate, reference_dataset, candidate_dataset, before, after)
    a, b = fits
    changed_code = check_protocols(a['protocol'], b['protocol'])
    check_designs(a, b)
    movements, residuals = q.compare_residuals(a['residuals'], b['residuals'], before, after)
    group_movements, removed = q.compare_groups(a['groups'], b['groups'], before, after)
    if removed or residuals['excluded_reference_rows']:
        raise ValueError('Feature correction removed groups or observations')
    shared = sorted(set(a['data'].building))
    building = [q.building_contrasts(f, shared) for f in fits]
    building_changes = [{'id': x['id'], 'log_effect': q.common.interval_change(x['log_effect'], y['log_effect'])}
        for x, y in zip(building[0]['contrasts'], building[1]['contrasts'], strict=True)]
    building_changes.sort(key=lambda r: (-abs(r['log_effect']['median_change']), r['id']))
    category = [q.laundry.category_result(Path(path), f['root'], f['dataset'], f)
        for path, f in zip((reference_categories, candidate_categories), fits, strict=True)]
    floor = [q.floors.joint_floor_contrasts(f['root'], f['protocol'], f['design'], f['design'].floor_levels) for f in fits]
    elevator = [elevator_contrasts(f) for f in fits]
    affected = Counter(r['observation']['building'] for r in changes)
    changed_ids = {r['observation']['audit_id'] for r in changes}
    result = {'version': VERSION, 'main_selection_changed': False,
        'source_rows': len(before), 'retained_rows': len(after), 'excluded_rows': 0, 'changed_rows': len(changes),
        'changed_current_rows': sum(r['audit_id'] in changed_ids and r['analysis_price_basis'] == 'current_capture_gross_ask' for r in after),
        'affected_buildings': dict(affected), 'changed_loader_implementations': changed_code,
        'fits': [{'protocol': f['protocol'], 'diagnostics': f['report']['diagnostics'],
                  'design_reconstruction': f['reconstruction']} for f in fits],
        'elevator_normalization': [f['design'].numeric['elevator'] for f in fits],
        'elevator_contrasts': [{'id': x['id'], 'reference': x, 'candidate': y,
            'percent_effect': q.common.interval_change(x['percent_effect'], y['percent_effect'])}
            for x, y in zip(*elevator, strict=True)],
        'residuals': {**residuals, 'corrected_rows': q.laundry.summarize_slice([r for r in movements if r['audit_id'] in changed_ids])},
        'building_reference': {'definition': 'Unweighted mean of all identical buildings, subtracted within each posterior draw.',
            'buildings': shared, 'diagnostics': [v['diagnostics'] for v in building]},
        'largest_common_reference_building_movements': building_changes[:25],
        'affected_common_reference_building_movements': [r for r in building_changes if r['id'] in affected],
        'largest_unit_movements': [r for r in group_movements if r['kind'] == 'unit'][:25],
        'category_contrasts': q.compare_categories(*category), 'floor_contrasts': q.compare_floors(*floor),
        'floor_diagnostics': [v['diagnostics'] for v in floor],
        'bathrooms': {name: q.source.compare_contrasts(a['report']['bathrooms'][name], b['report']['bathrooms'][name], fields)
            for name, fields in [('full_bath_increments', ('log_effect','percent_effect')),
                ('half_bath_increments', ('log_effect','percent_effect')), ('net_balance', ('difference',))]},
        'limitations': [q.common.LIMITATION,
            'Same observations and asking prices; only reviewed elevator values and their provenance change.',
            'Elevator normalization is refitted. Equal coefficient scales imply slightly different raw contrast priors, reported explicitly.',
            'Unknown elevator reporting is not absence; reporting-state contrasts are not physical amenity premiums.',
            'Intervals are conditional posterior associations; source corrections do not establish causal effects or resolve all elevator conflicts.',
            'Changes compare summaries of independent fits. Their draws are never paired into a posterior of the change.']}
    for f in fits:
        if digest(f['root']/'fit/posterior.nc') != f['provenance']['fit_manifest']['files']['posterior.nc']:
            raise ValueError('Posterior changed during comparison')
    return result, movements, group_movements, building_changes, [v['bindings'] for v in category]


def run(output, **kwargs):
    result, movements, groups, buildings, bindings = build_comparison(**kwargs)
    modules = (correction, q, q.report, q.source, q.common, q.floors, q.laundry, categories)
    files = {Path(m.__file__).name: Path(m.__file__).read_text() for m in modules}
    files.update({Path(__file__).name: Path(__file__).read_text(), 'comparison.json': canonical(result)+'\n',
        'residual-movements.jsonl': ''.join(canonical(r)+'\n' for r in movements),
        'raw-group-movements.jsonl': ''.join(canonical(r)+'\n' for r in groups),
        'common-reference-building-movements.jsonl': ''.join(canonical(r)+'\n' for r in buildings)})
    publish_bundle(output, files, {'version': VERSION, 'fits': bindings,
        'category_manifests': [digest(Path(kwargs[k])/'complete.json') for k in ('reference_categories', 'candidate_categories')]})
    print(canonical({'retained_rows': result['retained_rows'], 'changed_rows': result['changed_rows'], 'excluded_rows': 0}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'reference_dataset', 'candidate_dataset', 'reference_categories', 'candidate_categories', 'output'):
        parser.add_argument('--'+name.replace('_','-'), type=Path, required=True)
    with threadpool_limits(limits=1, user_api='blas'):
        run(**vars(parser.parse_args()))
