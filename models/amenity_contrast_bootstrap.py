"""Exploratory building-cluster sampling stability of fixed-model contrasts.

Whole buildings are sampled with replacement. Repeated cluster copies receive
independent building/unit IDs. Every replicate refits the centered encoder and
robust estimator. Percentiles are conditional stability summaries, not causal or
calibrated confidence intervals.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import fcntl
import hashlib
import importlib.metadata
import json
import multiprocessing
import os
from pathlib import Path

# Spawned workers import numerical libraries only after these bounded settings.
for _name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
import numpy as np
import pandas as pd

from . import amenity_ablation as ablation
from . import amenity_ablation_contrasts as contrast_report
from . import amenity_rent_model as model
from . import minimal_rent_model as baseline
from apartments import research_pipeline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'amenity-building-bootstrap-v1'
SOURCE_BUILDING = '__bootstrap_source_building'
SOURCE_UNIT = '__bootstrap_source_unit'
COPY_POSITION = '__bootstrap_copy_position'
CATEGORY_PREFIX = '__bootstrap_category_'
CONTRASTS = contrast_report.CONTRASTS
_TRAIN = _GROUPS = _GROUP_STATS = _PROTOCOL = _ROOT = None


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def code_paths():
    return [Path(__file__), Path(contrast_report.__file__), Path(ablation.__file__),
            Path(model.__file__), Path(baseline.__file__), Path(model.pricing.__file__),
            Path(research_pipeline.__file__)]


def code_hashes():
    return {path.name: digest(path) for path in code_paths()}


def prepare_frame(train):
    reserved = [SOURCE_BUILDING, SOURCE_UNIT, COPY_POSITION,
                *(CATEGORY_PREFIX+field for field in model.CATEGORIES)]
    if any(name in train for name in reserved):
        raise ValueError('Source contains reserved bootstrap provenance columns')
    result = train.copy()
    result[SOURCE_BUILDING] = result.building.astype(str)
    result[SOURCE_UNIT] = result.unit_id.astype(str)
    normalized = [model.feature_record(row) for row in train.to_dict('records')]
    for field in model.CATEGORIES:
        result[CATEGORY_PREFIX+field] = [model.pricing._category(row.get(field)) for row in normalized]
    return result


def draw_buildings(buildings, seed, replicate):
    """Seeds and RNG draws do not depend on worker scheduling or resumption."""
    ordered = sorted(str(value) for value in buildings)
    rng = np.random.default_rng(np.random.SeedSequence([seed, replicate]))
    indices = rng.integers(0, len(ordered), size=len(ordered))
    return [ordered[int(index)] for index in indices]


def resample_clusters(train, selected, replicate, groups=None):
    """Retain source columns while making each selected cluster independent."""
    if SOURCE_BUILDING not in train:
        train = prepare_frame(train)
    groups = groups or {str(key): rows for key, rows in train.groupby('building', sort=False)}
    frames, evidence = [], []
    for position, original in enumerate(selected):
        copy = groups[str(original)].copy()
        building = canonical(['bootstrap-building', replicate, position, str(original)])
        copy['building'] = building
        if 'building_id' in copy:
            copy['building_id'] = building
        copy['unit_id'] = copy[SOURCE_UNIT].map(lambda unit: canonical(['bootstrap-unit', replicate, position, unit]))
        copy[COPY_POSITION] = position
        frames.append(copy)
        evidence.append({'position': position, 'source_building': str(original),
                         'sampled_building': building, 'unit_months': len(copy),
                         'source_units': int(copy[SOURCE_UNIT].nunique())})
    sampled = pd.concat(frames, ignore_index=True)
    return sampled, evidence


def category_support(sample, field, before, after):
    groups, output = {}, {}
    for level in (before, after):
        part = sample[sample[CATEGORY_PREFIX+field].eq(level)]
        groups[level] = part
        output[level] = {'unit_months': len(part), 'unit_copies': int(part.unit_id.nunique()),
                         'cluster_copies': int(part.building.nunique()),
                         'source_units': int(part[SOURCE_UNIT].nunique()),
                         'source_buildings': int(part[SOURCE_BUILDING].nunique())}
    return {'categories': output,
            'cluster_copies_with_both': len(set(groups[before].building)&set(groups[after].building)),
            'source_buildings_with_both': len(set(groups[before][SOURCE_BUILDING])&set(groups[after][SOURCE_BUILDING])),
            'source_units_with_both': len(set(groups[before][SOURCE_UNIT])&set(groups[after][SOURCE_UNIT]))}


def _contrast_estimates(fitted, sample, supports, status):
    results = []
    encoder = fitted['encoder'] if fitted is not None else None
    for (field, before, after), support in zip(CONTRASTS, supports):
        result = {'field': field, 'from': before, 'to': after, 'support': support,
                  'log_difference': None, 'percent_difference': None}
        if any(support['categories'][level]['unit_months'] == 0 for level in (before, after)):
            result['status'] = 'absent_category'
        elif status != 'converged':
            result['status'] = status
        else:
            start, _ = encoder.offsets['amenities']
            indices = [encoder.amenity_features.index(f'{field}={level}') for level in (before, after)]
            effective = [float(fitted['beta'][start+index])*float(encoder.amenity_active_columns[index]) for index in indices]
            difference = effective[1]-effective[0]
            pair = pd.concat([sample.iloc[:1], sample.iloc[:1]], ignore_index=True)
            pair[field] = [before, after]
            prediction = baseline.predict(fitted, pair)
            direct = float(prediction[1]-prediction[0])
            if not np.isfinite(difference) or not np.isclose(difference, direct, rtol=1e-10, atol=1e-12):
                raise ValueError('Replicate contrast disagrees with the refitted encoder')
            result.update(status='estimated', log_difference=difference,
                          percent_difference=float(np.expm1(difference)*100),
                          centering_cancellation_error=abs(difference-direct))
        results.append(result)
    return results


def fit_replicate(train, protocol, replicate, groups=None):
    selected = draw_buildings(train.building.unique(), protocol['seed'], replicate)
    sampled, selection = resample_clusters(train, selected, replicate, groups)
    supports = [category_support(sampled, *contrast) for contrast in CONTRASTS]
    result = {'replicate': replicate, 'seed_components': [protocol['seed'], replicate],
              'source_cluster_draw_sha256': _hash(selected),
              'sampled_cluster_instances': len(selected), 'unique_source_buildings': len(set(selected)),
              'sampled_unit_months': len(sampled), 'sampled_unit_copies': int(sampled.unit_id.nunique()),
              'source_units': int(sampled[SOURCE_UNIT].nunique()),
              'sampled_rows_sha256': _hash(sorted((str(row.unit_id), str(row.period), str(row.audit_id))
                                                for row in sampled.itertuples())),
              'settings': protocol['settings']}
    fitted = None
    try:
        fitted = baseline.fit(sampled, protocol['settings'], unit_effect=protocol['unit_effect'],
                              iterations=protocol['max_irls_iterations'],
                              encoder_class=ablation.encoder_class('full'))
        change = fitted['robust_objective_relative_change']
        converged = change is not None and np.isfinite(change) and change <= protocol['convergence_tolerance']
        result['status'] = 'converged' if converged else 'not_converged'
        result['convergence'] = {'objective_relative_change': float(change) if change is not None and np.isfinite(change) else None, 'solves': fitted['solves'],
                                 'maximum_irls_iterations': protocol['max_irls_iterations']}
        if not np.isfinite(fitted['beta']).all():
            raise ValueError('Non-finite fitted coefficients')
        if replicate < 2:
            result['stationarity_diagnostic'] = stationarity(fitted, sampled)
        metadata = fitted['encoder'].metadata()
        result['encoder'] = {key: metadata[key] for key in ('amenity_features', 'amenity_numeric',
            'amenity_categories', 'amenity_category_counts', 'amenity_category_centers',
            'amenity_active_columns', 'ablation_variant')}
        start, stop = fitted['encoder'].offsets['amenities']
        result['amenity_coefficients'] = fitted['beta'][start:stop].tolist()
        result['contrasts'] = _contrast_estimates(fitted, sampled, supports, result['status'])
    except Exception as error:
        # A failed replicate remains in the denominator and in an immutable
        # checkpoint. It is never replaced by a zero or a fresh favorable draw.
        result.update(status='fit_failed', error={'type': type(error).__name__, 'message': str(error)})
        result['contrasts'] = _contrast_estimates(None, sampled, supports, 'fit_failed')
    return result, selection


def stationarity(fitted, sample):
    """Penalized-Huber gradient diagnostic on the two preflight replicates."""
    encoder = fitted['encoder']
    design = encoder.matrix(sample)
    penalty = encoder.penalty(fitted['settings'])
    residual = sample.log_rent.to_numpy()-fitted['center']-design@fitted['beta']
    score = np.asarray(design.T@np.clip(residual,-.2,.2)).ravel()
    shrinkage = np.asarray(penalty.T@(penalty@fitted['beta'])).ravel()
    gradient = score-shrinkage
    start, stop = encoder.offsets['amenities']
    return {'max_absolute_penalized_huber_gradient': float(np.max(np.abs(gradient))),
            'max_absolute_amenity_gradient': float(np.max(np.abs(gradient[start:stop]))),
            'relative_infinity_norm': float(np.max(np.abs(gradient))/max(1.,np.max(np.abs(score)),np.max(np.abs(shrinkage)))),
            'interpretation': 'diagnostic only; the declared acceptance gate remains finite objective relative change <=1e-5'}


def summarize(records, protocol):
    results = []
    for index, (field, before, after) in enumerate(CONTRASTS):
        entries = [record['contrasts'][index] for record in records]
        counts = Counter(entry['status'] for entry in entries)
        values = np.array([entry['log_difference'] for entry in entries if entry['status'] == 'estimated'], dtype=float)
        if len(values) and not np.isfinite(values).all():
            raise ValueError('Non-finite successful bootstrap estimate')
        quantiles = np.quantile(values, [.025, .5, .975], method='linear') if len(values) >= 20 else None
        results.append({'field': field, 'from': before, 'to': after, 'status_counts': dict(counts),
                        'available_estimates': len(values), 'completed_replicates': len(records),
                        'planned_replicates': protocol['draws'],
                        'percentile_log_difference_2_5_50_97_5': quantiles.tolist() if quantiles is not None else None,
                        'percentile_percent_difference_2_5_50_97_5': (np.expm1(quantiles)*100).tolist() if quantiles is not None else None,
                        'positive_fraction_among_available': float(np.mean(values>0)) if len(values) else None,
                        'negative_fraction_among_available': float(np.mean(values<0)) if len(values) else None,
                        'zero_fraction_among_available': float(np.mean(values==0)) if len(values) else None,
                        'approximate_replicates_in_each_2_5_percent_tail': len(values)*.025,
                        'interval_scope': 'exploratory percentile sampling stability conditional on this selected regularized model and replicates where both categories are present and optimization converges'})
    return {'version': VERSION, 'planned_replicates': protocol['draws'], 'completed_replicates': len(records),
            'replicate_status_counts': dict(Counter(record['status'] for record in records)),
            'contrasts': results, 'limitations': [
                'These are conditional sampling-stability summaries, not causal effects or calibrated confidence intervals.',
                'Model choice, penalty choice, historical source validity, extraction error and NYC sampling bias are not resampled.',
                'Whole buildings are treated as exchangeable clusters; spatial and market-wide dependence may remain.',
                'Fixed penalties and a variable number of sampled rows allow effective shrinkage to vary with cluster composition.',
                'Category absence and convergence failures are explicit; quantiles use available estimates and can be selective.',
                'With 200 successful draws each 2.5% tail contains only about five replicates; Monte Carlo precision is limited.',
            ]}


def verify_source(dataset, experiment):
    root = Path(experiment)
    protocol_bytes = (root/'protocol.json').read_bytes()
    parent = json.loads(protocol_bytes)
    parent_hash = hashlib.sha256(protocol_bytes).hexdigest()
    if parent.get('version') != 'chelsea-amenity-ablation-v2':
        raise ValueError('Centered amenity ablation v2 required')
    selected = next((entry for entry in parent['splits'] if entry['name']=='year-2024'), None)
    if selected is None:
        raise ValueError('Reference experiment must contain year-2024')
    fitted_manifest, _ = _verified_bundle(root/'year-2024'/'full')
    if fitted_manifest.get('protocol_sha256') != parent_hash or fitted_manifest.get('split_sha256') != selected['test_sha256']:
        raise ValueError('Reference fit does not match protocol/split')
    for path in (Path(ablation.__file__), Path(model.__file__), Path(baseline.__file__), Path(model.pricing.__file__)):
        if digest(path) != parent['implementation_sha256'].get(path.name):
            raise ValueError('Reference fitting implementation changed')
    versions = {name: importlib.metadata.version(name) for name in parent['versions']}
    if versions != parent['versions']:
        raise ValueError('Reference library versions changed')
    data, source, _ = model.load_analytical(dataset)
    if source != parent['source_manifest']:
        raise ValueError('Reference analytical source manifest changed')
    train = data[data.period < '2024-01-01'].copy()
    test = data[(data.period >= '2024-01-01')&(data.period < '2025-01-01')]
    if (len(train) != selected['train_rows'] or len(test) != selected['test_rows']
            or contrast_report.membership(train) != selected['train_sha256']
            or contrast_report.membership(test) != selected['test_sha256']):
        raise ValueError('Reference training/test memberships changed')
    reference = model.load_fit(root/'year-2024'/'full')
    if getattr(reference['encoder'], 'ablation_variant', None) != 'full' or not hasattr(reference['encoder'], 'amenity_category_centers'):
        raise ValueError('Reference model is not the centered full model')
    point_contrasts = [contrast_report.category_contrast(reference, train, *contrast) for contrast in CONTRASTS]
    return prepare_frame(train), {'parent_protocol_sha256': parent_hash,
        'parent_fit_manifest': fitted_manifest, 'source_manifest': source, 'versions': versions,
        'training_membership_sha256': selected['train_sha256'], 'training_rows': len(train),
        'training_buildings': int(train.building.nunique()), 'training_units': int(train.unit_id.nunique()),
        'unit_effect': parent['unit_effect'], 'settings': parent['settings'],
        'reference_point_contrasts': point_contrasts}


def prepare_protocol(train, verified, *, draws=200, seed=2026091801):
    if not isinstance(draws, int) or draws < 1 or not isinstance(seed, int) or seed < 0:
        raise ValueError('Positive integer draws and nonnegative integer seed required')
    return {'version': VERSION, **verified, 'draws': draws, 'seed': seed,
            'rng': 'numpy.default_rng(SeedSequence([seed, zero_based_replicate]))',
            'cluster_rule': 'B whole-building draws with replacement, all rows retained; independent canonical-array building and unit IDs per draw position',
            'building_vocabulary_sha256': _hash(sorted(train.building.astype(str).unique())),
            'max_irls_iterations': 20, 'convergence_tolerance': 1e-5,
            'contrasts': [list(contrast) for contrast in CONTRASTS],
            'implementation_sha256': code_hashes(),
            'interpretation': 'exploratory conditional sampling stability; fixed selected penalties, not causal or calibrated confidence intervals'}


def replicate_identity(train, protocol, replicate, group_stats=None):
    stats = group_stats or {str(key): (len(rows), int(rows.unit_id.nunique()))
                            for key, rows in train.groupby('building', sort=False)}
    selected = draw_buildings(stats, protocol['seed'], replicate)
    return {'version': VERSION, 'protocol_sha256': _hash(protocol), 'replicate': replicate,
            'seed_components': [protocol['seed'], replicate],
            'source_cluster_draw_sha256': _hash(selected),
            'sampled_cluster_instances': len(selected),
            'sampled_unit_months': sum(stats[building][0] for building in selected),
            'sampled_unit_copies': sum(stats[building][1] for building in selected)}


def read_checkpoint(directory, train, protocol, replicate, group_stats=None):
    expected = replicate_identity(train, protocol, replicate, group_stats)
    manifest, files = _verified_bundle(directory, retain={'result.json', 'cluster-draw.json'})
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError('Replicate checkpoint identity/seed/draw/count mismatch')
    result = json.loads(files['result.json'])
    for key in ('replicate', 'seed_components', 'source_cluster_draw_sha256',
                'sampled_cluster_instances', 'sampled_unit_months', 'sampled_unit_copies'):
        if result.get(key) != expected[key]:
            raise ValueError('Replicate result identity/seed/draw/count mismatch')
    selection = json.loads(files['cluster-draw.json'])
    selected = draw_buildings(train.building.unique(), protocol['seed'], replicate)
    if len(selection) != len(selected) or any(
            row.get('position') != position or row.get('source_building') != source
            or row.get('sampled_building') != canonical(['bootstrap-building', replicate, position, source])
            for position, (row, source) in enumerate(zip(selection, selected))):
        raise ValueError('Replicate cluster draw does not match its deterministic seed')
    if [(entry.get('field'), entry.get('from'), entry.get('to')) for entry in result['contrasts']] != list(CONTRASTS):
        raise ValueError('Replicate contrast identities mismatch')
    if result.get('status') not in {'converged', 'not_converged', 'fit_failed'}:
        raise ValueError('Unknown replicate status')
    return result


def _worker_init(train, protocol, root):
    global _TRAIN, _GROUPS, _GROUP_STATS, _PROTOCOL, _ROOT
    _TRAIN, _PROTOCOL, _ROOT = train, protocol, Path(root)
    _GROUPS = {str(key): rows for key, rows in train.groupby('building', sort=False)}
    _GROUP_STATS = {key: (len(rows), int(rows.unit_id.nunique())) for key, rows in _GROUPS.items()}


def _worker(replicate):
    if code_hashes() != _PROTOCOL['implementation_sha256']:
        raise ValueError('Bootstrap implementation changed during run')
    result, selected = fit_replicate(_TRAIN, _PROTOCOL, replicate, _GROUPS)
    if code_hashes() != _PROTOCOL['implementation_sha256']:
        raise ValueError('Bootstrap implementation changed during fitting')
    output = _ROOT/'replicates'/f'{replicate:05d}'
    publish_bundle(output, {'result.json': canonical(result)+'\n',
                            'cluster-draw.json': canonical(selected)+'\n'},
                   replicate_identity(_TRAIN, _PROTOCOL, replicate, _GROUP_STATS))
    return replicate, result['status']


def run(dataset, experiment, output, *, draws=200, seed=2026091801, workers=2,
        prepare_only=False, max_new_replicates=None):
    if workers not in (1, 2):
        raise ValueError('Use one or two bounded workers')
    if max_new_replicates is not None and max_new_replicates < 0:
        raise ValueError('max_new_replicates cannot be negative')
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.bootstrap.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        train, verified = verify_source(dataset, experiment)
        protocol = prepare_protocol(train, verified, draws=draws, seed=seed)
        protocol_hash = _hash(protocol)
        snapshots = {f'source-{path.name}': path.read_text() for path in code_paths()}
        if code_hashes() != protocol['implementation_sha256']:
            raise ValueError('Implementation changed during protocol snapshot')
        publish_bundle(root/'protocol', {'protocol.json': canonical(protocol)+'\n', **snapshots}, {'version': VERSION})
        if prepare_only:
            return {'status': 'prepared', 'protocol_sha256': protocol_hash, 'draws': draws}
        records = {}
        for replicate in range(draws):
            directory = root/'replicates'/f'{replicate:05d}'
            if (directory/'complete.json').exists():
                records[replicate] = read_checkpoint(directory, train, protocol, replicate)
        pending = [replicate for replicate in range(draws) if replicate not in records]
        if max_new_replicates is not None:
            pending = pending[:max_new_replicates]
        progress = lambda: {'version': VERSION, 'planned': draws, 'completed': len(records),
                            'status_counts': dict(Counter(result['status'] for result in records.values())),
                            'protocol_sha256': protocol_hash}
        (root/'progress.json').write_text(canonical(progress())+'\n')
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn'),
                                 initializer=_worker_init, initargs=(train, protocol, str(root))) as pool:
            futures = {pool.submit(_worker, replicate): replicate for replicate in pending}
            for future in as_completed(futures):
                replicate, status = future.result()
                records[replicate] = read_checkpoint(root/'replicates'/f'{replicate:05d}', train, protocol, replicate)
                (root/'progress.json').write_text(canonical(progress())+'\n')
                print(canonical({'phase': 'bootstrap', 'replicate': replicate, 'status': status,
                                 'completed': len(records), 'planned': draws}), flush=True)
        if code_hashes() != protocol['implementation_sha256']:
            raise ValueError('Bootstrap implementation changed during run')
        ordered = [records[index] for index in sorted(records)]
        summary = summarize(ordered, protocol)
        if len(records) == draws:
            publish_bundle(root/'summary', {'summary.json': canonical(summary)+'\n'},
                           {'version': VERSION, 'protocol_sha256': protocol_hash})
        else:
            (root/'partial-summary.json').write_text(canonical(summary)+'\n')
        (root/'progress.json').write_text(canonical({**progress(), 'phase': 'complete' if len(records)==draws else 'partial'})+'\n')
        return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--draws', type=int, default=200)
    parser.add_argument('--seed', type=int, default=2026091801)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--max-new-replicates', type=int)
    args = parser.parse_args()
    result = run(args.dataset, args.experiment, args.output, draws=args.draws, seed=args.seed,
                 workers=args.workers, prepare_only=args.prepare_only, max_new_replicates=args.max_new_replicates)
    print(canonical({'phase': 'returned', 'completed': result.get('completed_replicates', 0),
                     'status': result.get('status', 'complete' if result.get('completed_replicates')==args.draws else 'partial')}), flush=True)
