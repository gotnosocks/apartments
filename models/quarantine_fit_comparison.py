"""Compare converged floor models across an exactly reversible source quarantine.

Compare residuals on common rows and building offsets against a common building
reference within each posterior. Never pair draws from independent fits.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from apartments import reviewed_cohort_quarantine as quarantine
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_report as report, bayesian_feature_sensitivity as common
from . import bayesian_source_sensitivity as source, bayesian_floor_sensitivity as floors
from . import bayesian_disk_protocol as disk, laundry_floor_fit_comparison as laundry
from .bayesian_feature_design_v2 import load_design

VERSION = 'reviewed-quarantine-fit-comparison-v1'


def check_protocols(a, b):
    if (a.get('version') != floors.V4 or b.get('version') != floors.V4
            or a.get('source_version') != quarantine.PARENT or b.get('source_version') != quarantine.VERSION
            or a.get('residual_scale') != 'shared' or b.get('residual_scale') != 'shared'):
        raise ValueError('Expected shared-noise floor fits before and after reviewed quarantine')
    if not disk.verify_protocol(a) or not disk.verify_protocol(b): raise ValueError('Durable fitted protocols required')
    variable = source.SOURCE_FIELDS | {'graph_verification', 'implementation_sha256'}
    if {k: v for k, v in a.items() if k not in variable} != {k: v for k, v in b.items() if k not in variable}:
        raise ValueError('Sampler, model, prior, floor support or numerical environment changed')
    old, new = a['implementation_sha256'], b['implementation_sha256']
    helpers = {'laundry_floor_split.py', 'reviewed_cohort_quarantine.py'}
    if not old.keys() <= new.keys() or not (new.keys()-old.keys()) <= helpers:
        raise ValueError('Unexpected implementation inventory change')
    if 'reviewed_cohort_quarantine.py' not in new: raise ValueError('Missing quarantine implementation')
    changed = {k for k in old if old[k] != new[k]}
    if changed - {'bayesian_feature_experiment_v3.py', 'reviewed_source_lineage.py'}:
        raise ValueError('Mathematical or sampling implementation changed')
    return sorted(changed)


def verify_revision(reference, candidate):
    bundles = [_verified_bundle(p, retain={'observations.jsonl', quarantine.SIDECAR}) for p in (reference, candidate)]
    before, after = [report.jsonl(f['observations.jsonl']) for _, f in bundles]
    if quarantine.SIDECAR not in bundles[1][1]:
        raise ValueError('Missing quarantine sidecar')
    excluded = report.jsonl(bundles[1][1][quarantine.SIDECAR])
    if quarantine.parent_rows(bundles[1][0], after, excluded) != (bundles[0][0], before):
        raise ValueError('Quarantine does not restore the exact reference source')
    current = lambda rows: [r for r in rows if r['analysis_price_basis'] == 'current_capture_gross_ask']
    if current(before) != current(after): raise ValueError('Current observations changed')
    return before, after, excluded


def residual_index(values, rows):
    result = {r['audit_id']: r for r in values}
    if len(result) != len(values) or set(result) != {r['audit_id'] for r in rows}:
        raise ValueError('Residual membership differs from its exact source')
    fields = ('audit_id', 'unit_id', 'building', 'source_listing_id', 'period', 'asking_rent')
    if any(result[r['audit_id']][k] != r[k] for r in rows for k in fields):
        raise ValueError('Residual source identity or target changed')
    return result


def compare_residuals(before, after, original, kept):
    a, b = residual_index(before, original), residual_index(after, kept)
    if not b.keys() <= a.keys(): raise ValueError('Candidate adds observations')
    movements = [{**{k: r[k] for k in ('audit_id', 'unit_id', 'building', 'source_listing_id', 'period',
                                      'asking_rent', 'analysis_price_basis')},
        'reference': a[r['audit_id']], 'candidate': b[r['audit_id']],
        'fitted_rent_change': b[r['audit_id']]['fitted_rent']-a[r['audit_id']]['fitted_rent']} for r in kept]
    movements.sort(key=lambda r: (-abs(r['fitted_rent_change']), r['audit_id']))
    current = [r for r in movements if r['analysis_price_basis'] == 'current_capture_gross_ask']
    return movements, {'common_rows': laundry.summarize_slice(movements),
        'current_rows': laundry.summarize_slice(current), 'largest_current_movements': current[:20],
        'excluded_reference_rows': [a[k] for k in sorted(a.keys()-b.keys())]}


def group_index(values, rows):
    expected = {('building', r['building']) for r in rows} | {('unit', r['unit_id']) for r in rows}
    index = {(r['kind'], r['id']): r for r in values}
    if len(index) != len(values) or index.keys() != expected: raise ValueError('Group summary membership differs')
    return index


def compare_groups(before, after, original, kept):
    a, b = group_index(before, original), group_index(after, kept)
    if not b.keys() <= a.keys(): raise ValueError('Candidate adds groups')
    shared = [{'kind': kind, 'id': identity,
        'log_effect': common.interval_change(a[(kind, identity)]['log_effect'], b[(kind, identity)]['log_effect'])}
        for kind, identity in sorted(b)]
    shared.sort(key=lambda r: (-abs(r['log_effect']['median_change']), r['kind'], r['id']))
    return shared, [a[k] for k in sorted(a.keys()-b.keys())]


def common_building_draws(values, labels, shared):
    if (values.ndim != 3 or values.shape[-1] != len(labels) or len(set(labels)) != len(labels)
            or len(shared) < 2 or len(set(shared)) != len(shared) or not set(shared) <= set(labels)
            or not np.isfinite(values).all()):
        raise ValueError('Invalid building posterior or common reference population')
    selected = values[:, :, [labels.index(k) for k in shared]]
    return selected-selected.mean(axis=-1, keepdims=True)


def building_contrasts(fit, shared):
    import xarray as xr
    from . import bayesian_rent_model as base, bayesian_feature_experiment as summaries
    root, protocol = fit['root'], fit['protocol']
    with xr.open_dataset(root/'fit/posterior.nc', group='posterior', engine='h5netcdf', cache=False) as p, \
         xr.open_dataset(root/'fit/posterior.nc', group='sample_stats', engine='h5netcdf', cache=False) as s:
        if (p.building_effect.dims != ('chain', 'draw', 'building')
                or p.sizes['chain'] != protocol['chains'] or p.sizes['draw'] != protocol['draws']
                or set(p.building.values.tolist()) != set(fit['data'].building)):
            raise ValueError('Building draw dimensions or source coordinates differ')
        values = common_building_draws(p.building_effect.values, p.building.values.tolist(), shared)
        posterior = xr.Dataset({'common_building_contrast': (('chain', 'draw', 'building'), values)},
                               coords={'building': shared})
        diagnostics, _ = base.diagnostics(xr.DataTree.from_dict({'posterior': posterior, 'sample_stats': s.load()}))
    if not diagnostics['acceptable']: raise ValueError('Common-reference building contrasts fail convergence')
    return {'diagnostics': diagnostics, 'contrasts': [{'id': name, 'log_effect': summaries.interval(values[:, :, i].ravel())}
                                                     for i, name in enumerate(shared)]}


def compare_categories(a, b):
    indexed = [{r['id']: r for r in value['contrasts']} for value in (a, b)]
    if any(len(x) != len(v['contrasts']) for x, v in zip(indexed, (a, b))) or indexed[0].keys() != indexed[1].keys():
        raise ValueError('Category contrast membership changed')
    output = []
    for key in sorted(indexed[0]):
        x, y = [v[key] for v in indexed]
        if (any(x[k] != y[k] for k in ('field', 'before', 'after'))
                or np.shape(x['design_vector']) != np.shape(y['design_vector'])
                or not np.allclose(x['design_vector'], y['design_vector'], rtol=0, atol=1e-12)):
            raise ValueError('Category contrast semantics changed')
        output.append({'id': key, 'reference': x, 'candidate': y,
                       'percent_effect': common.interval_change(x['percent_effect'], y['percent_effect'])})
    return output


def compare_floors(a, b):
    def index(value):
        result = {(r['lower_floor'], r['upper_floor']): r for r in value['contrasts']}
        if len(result) != len(value['contrasts']):
            raise ValueError('Duplicate floor contrast')
        return result
    before, after = index(a), index(b)
    if before.keys() != after.keys():
        raise ValueError('Floor contrast endpoints changed')
    return [{'lower_floor': low, 'upper_floor': high,
        'reference': before[(low, high)], 'candidate': after[(low, high)],
        'percent_effect': common.interval_change(before[(low, high)]['percent_effect'], after[(low, high)]['percent_effect'])}
        for low, high in sorted(before)]


def build_comparison(reference, candidate, reference_dataset, candidate_dataset, reference_categories, candidate_categories):
    before, after, excluded = verify_revision(reference_dataset, candidate_dataset)
    fits = []
    for root, dataset, rows in zip(map(Path, (reference, candidate)), map(Path, (reference_dataset, candidate_dataset)),
                                   (before, after), strict=True):
        verified, provenance = report.build_report(root, dataset)
        protocol = json.loads(common.bound_bytes(root/'protocol', 'protocol.json', provenance['protocol_manifest']))
        reconstructed = source.verify_design(root, dataset, protocol, provenance)
        frame = pd.DataFrame(rows)
        frame.period = pd.to_datetime(frame.period); frame.square_feet = pd.to_numeric(frame.square_feet, errors='coerce')
        fits.append({'root': root, 'dataset': dataset, 'data': frame, 'report': verified, 'protocol': protocol,
            'provenance': provenance, 'reconstruction': reconstructed, 'design': load_design(root/'fit', frame, protocol),
            **{key: report.jsonl(common.bound_bytes(root/'fit', filename, provenance['fit_manifest']))
               for key, filename in [('residuals', 'residuals.jsonl'), ('groups', 'group-effects.jsonl')]}})
    a, b = fits
    changed_code = check_protocols(a['protocol'], b['protocol'])
    if a['design'].features != b['design'].features or not np.array_equal(a['design'].prior_scales, b['design'].prior_scales):
        raise ValueError('Feature support or coefficient prior scales changed')
    movements, residuals = compare_residuals(a['residuals'], b['residuals'], before, after)
    group_movements, removed_groups = compare_groups(a['groups'], b['groups'], before, after)
    shared = sorted(set(a['data'].building) & set(b['data'].building))
    building = [building_contrasts(f, shared) for f in fits]
    building_changes = [{'id': x['id'], 'log_effect': common.interval_change(x['log_effect'], y['log_effect'])}
                        for x, y in zip(building[0]['contrasts'], building[1]['contrasts'], strict=True)]
    building_changes.sort(key=lambda r: (-abs(r['log_effect']['median_change']), r['id']))
    category = [laundry.category_result(Path(path), f['root'], f['dataset'], f) for path, f in
                zip((reference_categories, candidate_categories), fits, strict=True)]
    floor = [floors.joint_floor_contrasts(f['root'], f['protocol'], f['design'], f['design'].floor_levels) for f in fits]
    affected = Counter(r['observation']['building'] for r in excluded)
    result = {'version': VERSION, 'main_selection_changed': False,
        'source_rows': len(before), 'retained_rows': len(after), 'excluded_rows': len(excluded),
        'affected_buildings': dict(affected), 'changed_loader_implementations': changed_code,
        'fits': [{'protocol': f['protocol'], 'diagnostics': f['report']['diagnostics'],
                  'design_reconstruction': f['reconstruction']} for f in fits],
        'normalization': [{'numeric': f['design'].numeric, 'centering': f['design'].means.tolist(),
            'categories': f['design'].categories, 'size_medians': f['design'].time.size_medians,
            'size_default': f['design'].time.size_default} for f in fits],
        'residuals': residuals, 'removed_groups': removed_groups,
        'building_reference': {'definition': 'Unweighted arithmetic mean of the identical shared buildings, subtracted within each posterior draw.',
            'buildings': shared, 'diagnostics': [v['diagnostics'] for v in building]},
        'largest_common_reference_building_movements': building_changes[:25],
        'affected_common_reference_building_movements': [r for r in building_changes if r['id'] in affected],
        'largest_unit_movements': [r for r in group_movements if r['kind'] == 'unit'][:25],
        'category_contrasts': compare_categories(*category),
        'floor_contrasts': compare_floors(*floor),
        'floor_diagnostics': [value['diagnostics'] for value in floor],
        'bathrooms': {name: source.compare_contrasts(a['report']['bathrooms'][name], b['report']['bathrooms'][name], fields)
            for name, fields in [('full_bath_increments', ('log_effect','percent_effect')),
                ('half_bath_increments', ('log_effect','percent_effect')), ('net_balance', ('difference',))]},
        'limitations': [common.LIMITATION, 'Residual comparison uses exactly the retained common observations; excluded rows have reference-only residuals.',
            'Normalization, category frequencies and group support are refitted. Equal coefficient scales do not imply identical induced priors.',
            'Building contrasts use a common reference population; raw group-offset summaries remain in the separate audit file.',
            'Associations remain conditional on the model and surviving source records. Excluding unresolved price bases is not proof of historical net terms.']}
    # Refuse a posterior changed between verification and the last joint analysis.
    for f in fits:
        if digest(f['root']/'fit/posterior.nc') != f['provenance']['fit_manifest']['files']['posterior.nc']:
            raise ValueError('Posterior changed during comparison')
    return result, movements, group_movements, building_changes, [v['bindings'] for v in category]


def run(output, **kwargs):
    result, movements, groups, buildings, bindings = build_comparison(**kwargs)
    modules = (quarantine, report, source, common, floors, laundry)
    files = {Path(m.__file__).name: Path(m.__file__).read_text() for m in modules}
    files.update({Path(__file__).name: Path(__file__).read_text(), 'comparison.json': canonical(result)+'\n',
        'residual-movements.jsonl': ''.join(canonical(r)+'\n' for r in movements),
        'raw-group-movements.jsonl': ''.join(canonical(r)+'\n' for r in groups),
        'common-reference-building-movements.jsonl': ''.join(canonical(r)+'\n' for r in buildings)})
    publish_bundle(output, files, {'version': VERSION, 'fits': bindings,
        'category_manifests': [digest(Path(kwargs[k])/'complete.json') for k in ('reference_categories', 'candidate_categories')]})
    print(canonical({'retained_rows': result['retained_rows'], 'excluded_rows': result['excluded_rows']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference','candidate','reference_dataset','candidate_dataset','reference_categories','candidate_categories','output'):
        parser.add_argument('--'+name.replace('_','-'), type=Path, required=True)
    with threadpool_limits(limits=1, user_api='blas'): run(**vars(parser.parse_args()))
