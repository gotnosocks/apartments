"""Matched known-value blocks added separately to all amenity missingness controls.

This is additive block evaluation, not leave-one-out importance. Reference
baseline/missingness/full predictions are verified and reused without refitting.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments import corrections, research_pipeline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import amenity_ablation as ablation
from . import amenity_ablation_contrasts as contrasts
from . import amenity_rent_model as model
from . import minimal_rent_model as baseline

VERSION = 'amenity-additive-feature-blocks-v1'
REFERENCES = ('baseline', 'missingness', 'full')


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _verify_predictions(prediction, count):
    values = np.asarray(prediction, dtype=float)
    if values.shape != (count,) or not np.isfinite(values).all() or not (values > 0).all():
        raise ValueError('Invalid matched predictions')
    return values


def _reference_predictions(reference, name, expected, test, reference_hash):
    manifest, files = _verified_bundle(reference/name/'comparison', retain={'predictions.jsonl'})
    if manifest.get('protocol_sha256') != reference_hash:
        raise ValueError('Reference comparison protocol mismatch')
    table = pd.DataFrame(json.loads(line) for line in files['predictions.jsonl'].decode().split('\n') if line.strip())
    if len(table) != len(test):
        raise ValueError('Reference comparison row count mismatch')
    for field in ('unit_id', 'building', 'audit_id'):
        if table[field].tolist() != test[field].tolist():
            raise ValueError('Reference prediction row identity/order mismatch')
    if table.period.tolist() != test.period.dt.strftime('%Y-%m-%d').tolist():
        raise ValueError('Reference prediction period/order mismatch')
    if not np.allclose(table.asking_rent, test.asking_rent, rtol=0, atol=1e-8):
        raise ValueError('Reference prediction target mismatch')
    predictions, manifests = {}, {'comparison': manifest}
    for variant in REFERENCES:
        fit_manifest, fit_files = _verified_bundle(reference/name/variant, retain={'predictions.json'})
        if (fit_manifest.get('protocol_sha256') != reference_hash
                or fit_manifest.get('split_sha256') != expected['test_sha256']):
            raise ValueError('Reference fitted prediction membership mismatch')
        values = _verify_predictions(json.loads(fit_files['predictions.json']), len(test))
        # Comparison JSONL uses pandas decimal rounding; preserve the full-precision fit output.
        if not np.allclose(values, table[variant], rtol=1e-12, atol=1e-7):
            raise ValueError('Reference comparison disagrees with fitted predictions')
        predictions[variant] = values
        manifests[variant] = fit_manifest
    return predictions, manifests


def _exposure_support(data):
    result = {}
    for field, levels in model.pricing.EXPOSURES.items():
        source = data[field] if field in data else [None] * len(data)
        for level in levels:
            values = [model.pricing._exposure(value, field, level) for value in source]
            result[field+'.'+level] = {
                'positive': sum(value == 1 for value in values),
                'negative': sum(value == 0 for value in values),
                'unknown': sum(value is None for value in values),
            }
    return result


def _exposure_zero_check(encoder, train, test):
    start, _ = encoder.offsets['amenities']
    columns = [start+i for i, name in enumerate(encoder.amenity_features)
               if name.startswith(('window_exposures.', 'view_exposures.')) and not name.endswith('.unknown')]
    magnitudes = {}
    for label, data in [('train', train), ('test', test)]:
        values = encoder.matrix(data)[:, columns]
        magnitudes[label] = float(np.max(np.abs(values.data))) if values.nnz else 0.
    return {'known_value_columns': len(columns), 'maximum_absolute_encoded_value': magnitudes,
            'zero_value_design': all(value == 0 for value in magnitudes.values())}


def _summarize(table, variants, *, draws):
    metrics = {variant: baseline.metrics(table, np.log(table[variant].to_numpy()))
               for variant in (*REFERENCES, *variants)}
    differences = {}
    for variant in variants:
        # These compare errors of fixed already-fitted models, not refitted parameter uncertainty.
        comparisons = {}
        for reference in ('missingness', 'full'):
            paired = table[['building', 'asking_rent']].copy()
            paired['baseline_rent'] = table[reference]
            paired['amenity_rent'] = table[variant]
            comparisons['block_minus_'+reference] = model.paired_building_comparison(paired, draws=draws)
        differences[variant] = comparisons
    return {'rows': len(table), 'buildings': int(table.building.nunique()),
            'metrics': metrics, 'paired_error_differences': differences}


def run(dataset, reference, output, *, year=2024, folds=(0,1,2,3,4),
        blocks=tuple(ablation.BLOCKS), min_rows=100, error_draws=2000):
    if year not in range(2011,2025) or not folds or len(set(folds)) != len(folds) or any(f not in range(5) for f in folds):
        raise ValueError('Choose a pre-2025 year and distinct building folds 0–4')
    if not blocks or len(set(blocks)) != len(blocks) or any(b not in ablation.BLOCKS for b in blocks):
        raise ValueError('Choose distinct existing feature blocks')
    if error_draws < 20:
        raise ValueError('At least 20 error-comparison resamples required')
    root, reference = Path(output), Path(reference)
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.experiment.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reference_bytes = (reference/'protocol.json').read_bytes()
        prior = json.loads(reference_bytes)
        reference_hash = hashlib.sha256(reference_bytes).hexdigest()
        if prior.get('version') != ablation.VERSION or not set(REFERENCES) <= set(prior['variants']):
            raise ValueError('Reference must contain centered baseline/missingness/full experiment')
        summary_manifest, summary_files = _verified_bundle(reference/'summary', retain={'results.json'})
        if (summary_manifest.get('protocol_sha256') != reference_hash
                or json.loads(summary_files['results.json'])['protocol'] != prior):
            raise ValueError('Reference summary/protocol mismatch')
        core_paths = [Path(p) for p in (ablation.__file__, model.__file__, baseline.__file__, model.pricing.__file__)]
        if {p.name:digest(p) for p in core_paths} != prior['implementation_sha256']:
            raise ValueError('Reference core implementation changed')
        versions = {package: importlib.metadata.version(package) for package in prior['versions']}
        if versions != prior['versions']:
            raise ValueError('Reference runtime versions changed')
        data, analytical, coverage = model.load_analytical(dataset)
        if analytical != prior['source_manifest']:
            raise ValueError('Reference analytical source changed')
        data = data[data.period < '2025-01-01'].copy()
        names = [f'building-{fold}' for fold in folds] + [f'year-{year}']
        split_map = {name:(train,test) for name,train,test in ablation.split_data(data, years=(year,), folds=folds, cross_years=())}
        splits, reference_values, reference_manifests = [], {}, {}
        for name in names:
            train, test = split_map[name]
            expected = next((split for split in prior['splits'] if split['name'] == name), None)
            if expected is None or min(len(train),len(test)) < min_rows:
                raise ValueError('Insufficient or missing reference split')
            if (len(train) != expected['train_rows'] or len(test) != expected['test_rows']
                    or contrasts.membership(train) != expected['train_sha256']
                    or contrasts.membership(test) != expected['test_sha256']):
                raise ValueError('Reference split membership changed')
            splits.append(expected)
            reference_values[name], reference_manifests[name] = _reference_predictions(
                reference, name, expected, test, reference_hash)
        paths = core_paths + [Path(__file__), Path(contrasts.__file__), Path(corrections.__file__), Path(research_pipeline.__file__)]
        source_code = {path.name:path.read_bytes().decode() for path in paths}
        implementation = {name:hashlib.sha256(content.encode()).hexdigest() for name,content in source_code.items()}
        support = _exposure_support(data)
        positive_or_unknown_only = not any(counts['negative'] for counts in support.values())
        protocol = {'version':VERSION, 'source_manifest':analytical,
                    'reference_protocol_sha256':reference_hash, 'reference_manifests':reference_manifests,
                    'implementation_sha256':implementation, 'versions':versions, 'coverage':coverage,
                    'settings':prior['settings'], 'unit_effect':prior['unit_effect'], 'splits':splits,
                    'blocks':list(blocks), 'iterations':20, 'maximum_objective_relative_change':1e-5,
                    'error_comparison_draws':error_draws, 'development_rows':len(data),
                    'exposure_source_support':support, 'exposure_positive_or_unknown_only':positive_or_unknown_only,
                    'interpretation':'each known-value block added to all amenity missingness controls; not leave-one-out importance; all comparisons reuse exploratory development data'}
        plan = root/'protocol.json'
        if plan.exists() and json.loads(plan.read_text()) != protocol:
            raise ValueError('Protocol changed; use a fresh output directory')
        if not plan.exists():
            plan.write_text(canonical(protocol)+'\n')
        protocol_hash = digest(plan)
        publish_bundle(root/'source', {**source_code, 'reference-protocol.json':reference_bytes.decode(),
                       'analytical-manifest.json':canonical(analytical)+'\n'},
                       {'version':VERSION, 'protocol_sha256':protocol_hash})
        completed, tables, results = 0, {}, []
        for expected in splits:
            name = expected['name']; train,test = split_map[name]
            table = test[['unit_id','building','period','asking_rent','audit_id']].copy().reset_index(drop=True)
            for variant, prediction in reference_values[name].items():
                table[variant] = prediction
            split_results = {}
            for block in blocks:
                directory = root/name/block
                binding = {'version':VERSION, 'protocol_sha256':protocol_hash, 'split':name, 'block':block,
                           'train_sha256':expected['train_sha256'], 'test_sha256':expected['test_sha256'],
                           'settings_sha256':_hash({'settings':prior['settings'],'unit_effect':prior['unit_effect']})}
                if (directory/'complete.json').exists():
                    checkpoint, content = _verified_bundle(directory, retain={'result.json','predictions.json'})
                    if {key:checkpoint.get(key) for key in binding} != binding:
                        raise ValueError('Checkpoint split/block/membership mismatch')
                    result = json.loads(content['result.json'])
                    if result['split'] != name or result['block'] != block:
                        raise ValueError('Checkpoint result identity mismatch')
                    prediction = _verify_predictions(json.loads(content['predictions.json']), len(test))
                else:
                    print(canonical({'phase':'fitting','split':name,'block':block,'train':len(train),'test':len(test)}), flush=True)
                    fitted = baseline.fit(train, prior['settings'], unit_effect=prior['unit_effect'],
                                          iterations=20, encoder_class=ablation.encoder_class(block))
                    change = fitted['robust_objective_relative_change']
                    if change is None or change > 1e-5:
                        raise ValueError('Feature block optimizer did not converge')
                    prediction = _verify_predictions(np.exp(baseline.predict(fitted,test)),len(test))
                    result = {'split':name,'block':block,'metrics':baseline.metrics(test,np.log(prediction)),
                              'objective_relative_change':change,'solves':fitted['solves'],
                              'encoder':fitted['encoder'].metadata()}
                    if block == 'exposures':
                        diagnostic = _exposure_zero_check(fitted['encoder'],train,test)
                        diagnostic['maximum_prediction_difference_from_missingness'] = float(np.max(abs(prediction-reference_values[name]['missingness'])))
                        diagnostic['predictions_match_missingness'] = bool(np.allclose(prediction,reference_values[name]['missingness'],rtol=1e-10,atol=1e-7))
                        if positive_or_unknown_only and (not diagnostic['zero_value_design'] or not diagnostic['predictions_match_missingness']):
                            raise ValueError('Positive/unknown exposure block unexpectedly adds a value effect')
                        result['exposure_diagnostic'] = diagnostic
                    saved = {'amenities':{'encoder':fitted['encoder'].metadata(),'beta':fitted['beta'].tolist(),'center':fitted['center']}}
                    publish_bundle(directory, {'result.json':canonical(result)+'\n','models.json':canonical(saved)+'\n',
                                               'predictions.json':canonical(prediction.tolist())+'\n'}, binding)
                table[block] = prediction; split_results[block] = result; completed += 1
                (root/'progress.json').write_text(canonical({'phase':'running','completed':completed,'total':len(splits)*len(blocks)})+'\n')
            table['period'] = table.period.dt.strftime('%Y-%m-%d')
            summary = {'split':name, **_summarize(table,blocks,draws=error_draws), 'block_fits':split_results}
            publish_bundle(root/name/'comparison', {'result.json':canonical(summary)+'\n',
                           'predictions.jsonl':table.to_json(orient='records',lines=True)},
                           {'version':VERSION,'protocol_sha256':protocol_hash,'split':name,'test_sha256':expected['test_sha256']})
            tables[name]=table;results.append(summary)
        pooled = None
        if set(folds) == set(range(5)):
            combined = pd.concat([tables[f'building-{fold}'] for fold in folds], ignore_index=True)
            if len(combined) != len(data) or combined.duplicated(['unit_id','period']).any():
                raise ValueError('Pooled building folds fail complete nonoverlapping coverage')
            identity = lambda frame:set(zip(frame.unit_id,frame.period,frame.audit_id))
            actual_data = data.copy(); actual_data['period'] = actual_data.period.dt.strftime('%Y-%m-%d')
            if identity(combined) != identity(actual_data):
                raise ValueError('Pooled held-out row identities differ from development data')
            seen = set()
            for fold in folds:
                buildings = set(tables[f'building-{fold}'].building)
                if seen & buildings:
                    raise ValueError('Pooled held-out buildings overlap')
                seen.update(buildings)
            pooled = _summarize(combined,blocks,draws=error_draws)
        if (digest(reference/'protocol.json') != reference_hash or digest(plan) != protocol_hash
                or any(digest(path) != implementation[path.name] for path in paths)):
            raise ValueError('Reference protocol or implementation changed during block run')
        report = {'version':VERSION,'protocol':protocol,'splits':results,'pooled_building_holdouts':pooled,
                  'limitations':['Blocks add known values to every missingness control; this is not leave-one-block-out importance.',
                                 'Retrospective reconstructed asking rents; exploratory reused development cohorts.',
                                 'Building-resampled paired error ranges condition on fitted models and are not parameter or causal intervals.',
                                 'A positive/unknown-only exposure has no observed positive-versus-negative contrast; a zero block effect is a design limitation, not zero amenity value.']}
        manifest = publish_bundle(root/'summary', {'report.json':canonical(report)+'\n'},
                                  {'version':VERSION,'protocol_sha256':protocol_hash})
        (root/'progress.json').write_text(canonical({'phase':'complete','completed':completed,'total':completed})+'\n')
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.dataset,args.reference,args.output)
