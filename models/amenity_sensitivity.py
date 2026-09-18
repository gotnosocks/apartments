"""Matched sensitivity of amenity contrasts to building, unit and amenity shrinkage."""
from __future__ import annotations

import argparse
import fcntl
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import amenity_ablation as ablation
from . import amenity_ablation_contrasts as contrasts
from . import amenity_rent_model as model
from . import minimal_rent_model as baseline

VERSION = 'amenity-shrinkage-sensitivity-v2'


def specifications(settings):
    """Predeclared comparisons; no selection based on held-out performance."""
    specs = []
    for units in (True, False):
        for strength in (1., 10., 100.):
            specs.append({'name':f'building-{strength:g}-'+('units' if units else 'no-units'),
                          'unit_effect':units, 'settings':{**settings, 'building_penalty':strength}})
    for strength in (2., 32.):
        specs.append({'name':f'unit-{strength:g}', 'unit_effect':True,
                      'settings':{**settings, 'unit_penalty':strength}})
    for strength in (2.5, 40.):
        specs.append({'name':f'amenity-{strength:g}', 'unit_effect':True,
                      'settings':{**settings, 'amenity_penalty':strength}})
    return specs


def validate_checkpoint(manifest, result, *, protocol_sha256, split, specification, expected):
    """A valid artifact for a different grid cell must not silently substitute."""
    if manifest.get('protocol_sha256') != protocol_sha256:
        raise ValueError('Checkpoint protocol mismatch')
    if result.get('split') != split or result.get('specification') != specification:
        raise ValueError('Checkpoint split or specification identity mismatch')
    if result.get('metrics', {}).get('observations') != expected['test_rows']:
        raise ValueError('Checkpoint test row count mismatch')
    if manifest.get('version') == VERSION:
        identity = {'split':split, 'specification':specification,
                    'train_sha256':expected['train_sha256'], 'test_sha256':expected['test_sha256']}
        if manifest.get('grid_identity') != identity:
            raise ValueError('Checkpoint grid identity mismatch')


def verify_completed(root):
    """Independently bind every completed v1/v2 result to its declared grid cell."""
    root = Path(root)
    protocol = json.loads((root/'protocol.json').read_text())
    protocol_hash = digest(root/'protocol.json')
    if protocol.get('version') not in {'amenity-shrinkage-sensitivity-v1', VERSION}:
        raise ValueError('Unsupported sensitivity protocol')
    manifest, files = _verified_bundle(root/'summary', retain={'report.json'})
    report = json.loads(files['report.json'])
    if manifest.get('protocol_sha256') != protocol_hash or report.get('protocol') != protocol:
        raise ValueError('Summary protocol mismatch')
    expected_results = []
    manifests = {}
    for split in protocol['splits']:
        for spec in protocol['specifications']:
            name = split['name']+'/'+spec['name']
            checkpoint, artifacts = _verified_bundle(root/name, retain={'result.json','predictions.json'})
            result = json.loads(artifacts['result.json'])
            validate_checkpoint(checkpoint, result, protocol_sha256=protocol_hash,
                                split=split['name'], specification=spec, expected=split)
            prediction = np.asarray(json.loads(artifacts['predictions.json']))
            if prediction.shape != (split['test_rows'],) or not np.isfinite(prediction).all() or not (prediction>0).all():
                raise ValueError('Invalid checkpoint predictions')
            expected_results.append(result)
            manifests[name] = digest(root/name/'complete.json')
    if report.get('results') != expected_results:
        raise ValueError('Summary does not match every declared grid cell')
    return {'version':'sensitivity-grid-verification-v1', 'protocol_sha256':protocol_hash,
            'verified_grid_cells':len(expected_results), 'checkpoint_manifest_sha256':manifests,
            'implementation_sha256':digest(__file__)}


def run(dataset, reference, output, *, year=2024, building_fold=0, min_rows=100):
    if year not in range(2011, 2025) or building_fold not in range(5):
        raise ValueError('Choose a pre-2025 development year and building fold 0–4')
    root, reference = Path(output), Path(reference)
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.experiment.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reference_hash = digest(reference/'protocol.json')
        prior = json.loads((reference/'protocol.json').read_text())
        if prior.get('version') != ablation.VERSION:
            raise ValueError('Reference must use centered amenity encoding')
        source, verified = _verified_bundle(reference/'summary', retain={'results.json'})
        if source.get('protocol_sha256') != reference_hash or json.loads(verified['results.json'])['protocol'] != prior:
            raise ValueError('Reference summary differs from its protocol')
        paths = [Path(p) for p in (ablation.__file__, model.__file__, baseline.__file__, model.pricing.__file__)]
        core = {p.name:digest(p) for p in paths}
        if core != prior['implementation_sha256']:
            raise ValueError('Reference implementation changed')
        versions = {p:importlib.metadata.version(p) for p in prior['versions']}
        if versions != prior['versions']:
            raise ValueError('Reference library versions changed')
        data, analytical, coverage = model.load_analytical(dataset)
        if analytical != prior['source_manifest']:
            raise ValueError('Reference analytical source changed')
        data = data[data.period < '2025-01-01'].copy()
        names = [f'year-{year}', f'year-{year}-building-{building_fold}']
        split_map = {name:(train,test) for name,train,test in ablation.split_data(
            data, years=(year,), folds=(building_fold,), cross_years=(year,)) if name in names}
        split_records = []
        for name in names:
            train, test = split_map[name]
            expected = next((s for s in prior['splits'] if s['name'] == name), None)
            if expected is None or min(len(train),len(test)) < min_rows:
                raise ValueError('Insufficient or missing reference split')
            if (contrasts.membership(train) != expected['train_sha256']
                    or contrasts.membership(test) != expected['test_sha256']
                    or len(train) != expected['train_rows'] or len(test) != expected['test_rows']):
                raise ValueError('Reference split membership changed')
            split_records.append(expected)
        specs = specifications(prior['settings'])
        own_paths = paths + [Path(__file__), Path(contrasts.__file__)]
        implementation = {p.name:digest(p) for p in own_paths}
        protocol = {'version':VERSION, 'source_manifest':analytical,
                    'reference_protocol_sha256':reference_hash,
                    'implementation_sha256':implementation, 'versions':versions,
                    'coverage':coverage, 'splits':split_records, 'specifications':specs,
                    'iterations':20, 'maximum_objective_relative_change':1e-5,
                    'interpretation':'predeclared exploratory sensitivity; no held-out hyperparameter selection; contrasts are conditional regularized associations'}
        plan = root/'protocol.json'
        if plan.exists() and json.loads(plan.read_text()) != protocol:
            raise ValueError('Protocol changed; use a fresh output directory')
        if not plan.exists():
            plan.write_text(canonical(protocol)+'\n')
        publish_bundle(root/'implementation', {p.name:p.read_text() for p in own_paths},
                       {'version':VERSION, 'protocol_sha256':digest(plan)})
        results = []
        for name in names:
            train, test = split_map[name]
            for spec in specs:
                directory = root/name/spec['name']
                if (directory/'complete.json').exists():
                    manifest, files = _verified_bundle(directory, retain={'result.json','predictions.json'})
                    result = json.loads(files['result.json'])
                    expected = next(s for s in split_records if s['name'] == name)
                    validate_checkpoint(manifest, result, protocol_sha256=digest(plan),
                                        split=name, specification=spec, expected=expected)
                    prediction = np.asarray(json.loads(files['predictions.json']))
                else:
                    print(canonical({'phase':'fitting', 'split':name, 'specification':spec['name']}), flush=True)
                    fit = baseline.fit(train, spec['settings'], unit_effect=spec['unit_effect'],
                                       iterations=20, encoder_class=ablation.encoder_class('full'))
                    change = fit['robust_objective_relative_change']
                    if change is None or change > 1e-5:
                        raise ValueError('Sensitivity optimizer did not converge')
                    log_prediction = baseline.predict(fit, test)
                    prediction = np.exp(log_prediction)
                    result = {'split':name, 'specification':spec, 'metrics':baseline.metrics(test, log_prediction),
                              'contrasts':[contrasts.category_contrast(fit, train, *c) for c in contrasts.CONTRASTS],
                              'objective_relative_change':change, 'solves':fit['solves']}
                    saved = {'amenities':{'encoder':fit['encoder'].metadata(),
                                         'beta':fit['beta'].tolist(), 'center':fit['center']}}
                    expected = next(s for s in split_records if s['name'] == name)
                    publish_bundle(directory, {'result.json':canonical(result)+'\n',
                                               'models.json':canonical(saved)+'\n',
                                               'predictions.json':canonical(prediction.tolist())+'\n'},
                                   {'version':VERSION, 'protocol_sha256':digest(plan),
                                    'grid_identity':{'split':name, 'specification':spec,
                                                     'train_sha256':expected['train_sha256'],
                                                     'test_sha256':expected['test_sha256']}})
                if prediction.shape != (len(test),) or not np.isfinite(prediction).all() or not (prediction > 0).all():
                    raise ValueError('Invalid sensitivity predictions')
                results.append(result)
                (root/'progress.json').write_text(canonical({'phase':'running', 'completed':len(results), 'total':len(specs)*len(names)})+'\n')
        if any(digest(p) != implementation[p.name] for p in own_paths) or digest(reference/'protocol.json') != reference_hash:
            raise ValueError('Implementation or reference changed during sensitivity run')
        report = {'protocol':protocol, 'results':results,
                  'limitations':['These reused development folds are not untouched validation.',
                                 'Sensitivity ranges are not sampling uncertainty or causal estimates.',
                                 'The crossed comparison uses one predeclared building fold; it cannot establish all-fold hyperparameter superiority.']}
        manifest = publish_bundle(root/'summary', {'report.json':canonical(report)+'\n'},
                                  {'version':VERSION, 'protocol_sha256':digest(plan)})
        verify_completed(root)
        (root/'progress.json').write_text(canonical({'phase':'complete','completed':len(results),'total':len(results)})+'\n')
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--year', type=int, default=2024)
    parser.add_argument('--building-fold', type=int, default=0)
    args = parser.parse_args()
    run(args.dataset, args.reference, args.output, year=args.year, building_fold=args.building_fold)
