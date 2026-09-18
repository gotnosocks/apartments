"""Source-bound, matched descriptive experiments for advertised interior claims."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, UTC
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments import interior_projection, interior_evidence, pricing, corrections, research_pipeline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import interior_model, minimal_rent_model as baseline, amenity_rent_model as amenities, amenity_ablation

VERSION = 'advertised-interior-descriptive-experiment-v1'
FIELDS = ('advertised_ceiling_feet', 'advertised_levels', 'floor_through_mention', 'skylight_mention')
VARIANTS = ('baseline', 'reporting', 'values')
SETTINGS_GRID = {'standard': amenities.SETTINGS,
                 'weaker_groups': {**amenities.SETTINGS, 'building_penalty': 2., 'unit_penalty': 2.},
                 'stronger_groups': {**amenities.SETTINGS, 'building_penalty': 50., 'unit_penalty': 40.}}


def records(data):
    return [json.loads(s) for s in data.decode().split('\n') if s.strip()]


def ancestry_contains(manifest, ancestor):
    while manifest:
        if manifest == ancestor:
            return True
        manifest = manifest.get('parent_dataset_manifest')
    return False


def prepare(dataset, evidence, output):
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    em, ef = _verified_bundle(evidence, retain={'evidence.jsonl'})
    if not ancestry_contains(dm, em['dataset_manifest']):
        raise ValueError('Interior evidence must bind this dataset or its membership-only ancestor')
    previous = _verified_bundle(output)[0] if (Path(output)/'complete.json').exists() else None
    interpreted_at = previous.get('interpreted_at') if previous else datetime.now(UTC).isoformat()
    if interpreted_at is None or corrections.instant(interpreted_at) > datetime.now(UTC):
        raise ValueError('Missing or future interior interpretation clock; choose a new artifact version')
    rows = records(df['observations.jsonl'])
    grouped = defaultdict(list)
    for capture in records(ef['evidence.jsonl']):
        grouped[capture['audit_id']].append(capture)
    output_rows = []; decisions = []; support = {}
    for row in rows:
        captures = grouped.get(row['audit_id'], [])
        allowed = set(row.get('capture_ids') or []) | {row.get('capture_id')}
        for capture in captures:
            if (str(capture['source_listing_id']) != str(row['source_listing_id'])
                    or capture['unit_id'] != row['unit_id']
                    or capture['canonical_unit_url'] != row['canonical_unit_url']
                    or capture['period'] != row['period']
                    or capture['capture_id'] not in allowed
                    or corrections.instant(capture['known_at']) > corrections.instant(row['known_at'])):
                raise ValueError('Interior evidence row identity, capture scope or knowledge mismatch')
        projected = interior_projection.project(captures)
        if any(field in row for field in FIELDS):
            raise ValueError('Dataset already contains interior projection columns')
        output_rows.append({**row, **projected['features']})
        if captures:
            decisions.append({'audit_id': row['audit_id'], 'source_listing_id': str(row['source_listing_id']), **projected})
    frame = pd.DataFrame(output_rows)
    for field in FIELDS:
        known = frame[field].notna()
        support[field] = {'known_rows': int(known.sum()), 'unknown_rows': int((~known).sum()),
            'known_units': int(frame.loc[known, 'unit_id'].nunique()),
            'known_buildings': int(frame.loc[known, 'building'].nunique()),
            'value_counts': {str(float(k)): int(v) for k,v in frame.loc[known, field].value_counts().sort_index().items()},
            'buildings_with_known_value_variation': int(frame.loc[known].groupby('building')[field].nunique().gt(1).sum()),
            'units_with_known_value_variation': int(frame.loc[known].groupby('unit_id')[field].nunique().gt(1).sum())}
    code = {Path(p).name: digest(p) for p in (__file__, interior_projection.__file__, interior_evidence.__file__)}
    return publish_bundle(output, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in output_rows),
        'decisions.jsonl': ''.join(canonical(r)+'\n' for r in decisions), 'support.json': canonical(support)+'\n',
        'projection.py': Path(interior_projection.__file__).read_text()},
        {'version': VERSION, 'dataset_version': 'advertised-interior-claims-v1', 'parent_dataset_manifest': dm,
         'evidence_manifest': em, 'projection_version': interior_projection.VERSION, 'implementation_sha256': code,
         'rows': len(rows), 'support': support, 'interpreted_at': interpreted_at,
         'interpretation': 'Conservative advertised text claims, possibly room-specific; unknown does not mean absent. No backward fill across advertisements.'})


def run(dataset, review, output, settings_grid=None):
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    review_manifest, review_files = _verified_bundle(review, retain={'review.json'})
    reviewed = json.loads(review_files['review.json'])
    if (dm.get('dataset_version') != 'advertised-interior-claims-v1'
            or review_manifest.get('dataset_manifest') != dm or reviewed.get('decision') != 'proceed_exploratory'):
        raise ValueError('Verified projection and matching source review required')
    rows = records(df['observations.jsonl']); train = pd.DataFrame(rows)
    train['period'] = pd.to_datetime(train.period); train['log_rent'] = np.log(train.asking_rent)
    if len(train) < 100 or train.duplicated(['unit_id','period']).any():
        raise ValueError('Insufficient or duplicate analytical observations')
    grid = SETTINGS_GRID if settings_grid is None else settings_grid
    if not grid:
        raise ValueError('At least one matched settings configuration required')
    paths = [Path(m.__file__) for m in (interior_model, interior_projection, interior_evidence, baseline,
             amenities, amenity_ablation, pricing, corrections, research_pipeline)] + [Path(__file__)]
    hashes = {p.name: digest(p) for p in paths}
    protocol = {'version': VERSION, 'dataset_manifest': dm, 'review_manifest': review_manifest,
        'variants': list(VARIANTS), 'settings_grid': grid, 'iterations': 20, 'unit_effect': True,
        'implementation_sha256': hashes, 'versions': {p: importlib.metadata.version(p) for p in ('numpy','pandas','scipy')},
        'interior_interpreted_at': dm['interpreted_at'],
        'purpose': 'Matched current-cohort feature contributions and in-sample residuals, with reporting controls and group-shrinkage sensitivity; no forecast claim.'}
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    with (root/'.experiment.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish_bundle(root/'protocol', {'protocol.json': canonical(protocol)+'\n', **{p.name:p.read_text() for p in paths}},
                       {'version': VERSION, 'protocol_sha256': ph})
        summaries = []
        current = train.analysis_price_basis.eq('current_capture_gross_ask').to_numpy()
        for name, settings in grid.items():
            predictions = {}; results = {}
            for variant in VARIANTS:
                target = root/name/variant
                if (target/'complete.json').exists():
                    fm, ff = _verified_bundle(target, retain={'model.json','result.json','log-fitted.json'})
                    if fm.get('protocol_sha256') != ph:
                        raise ValueError('Saved fit differs from protocol')
                    saved = json.loads(ff['model.json']); result = json.loads(ff['result.json'])
                    pred = np.array(json.loads(ff['log-fitted.json']))
                    fitted = interior_model.load_saved(saved)
                    if not np.allclose(pred, baseline.predict(fitted,train), rtol=0,atol=1e-11):
                        raise ValueError('Saved coefficients and fitted values disagree')
                else:
                    print(canonical({'phase':'fitting','settings':name,'variant':variant,'rows':len(train)}),flush=True)
                    fitted = baseline.fit(train,settings,iterations=20,encoder_class=interior_model.encoder_class(variant))
                    change = fitted['robust_objective_relative_change']
                    if change is None or not np.isfinite(change) or change > 1e-5:
                        raise ValueError('Interior experiment did not converge')
                    pred = baseline.predict(fitted,train)
                    saved = {'encoder':fitted['encoder'].metadata(),'beta':fitted['beta'].tolist(),'center':fitted['center']}
                    replay = baseline.predict(interior_model.load_saved(saved),train)
                    if not np.allclose(pred,replay,rtol=0,atol=1e-11):
                        raise ValueError('Saved-model parity failed')
                    result = {'metrics':baseline.metrics(train,pred),
                        'current_metrics':baseline.metrics(train[current],pred[current]) if current.any() else None,
                        'contrasts':interior_model.contribution_contrasts(fitted),
                        'objective_relative_change':change,'solves':fitted['solves'],
                        'serialization_maximum_log_difference':float(max(abs(pred-replay)))}
                    publish_bundle(target, {'model.json':canonical(saved)+'\n','result.json':canonical(result)+'\n',
                        'log-fitted.json':canonical(pred.tolist())+'\n'},
                        {'version':VERSION,'protocol_sha256':ph,'variant':variant,'settings':name})
                if len(pred)!=len(train) or not np.isfinite(pred).all():
                    raise ValueError('Invalid fitted values')
                predictions[variant]=pred;results[variant]=result
            table = []
            for i,row in enumerate(rows):
                table.append({k:row[k] for k in ('audit_id','source_listing_id','unit_id','building','period','asking_rent','analysis_price_basis',*FIELDS)} |
                    {variant+'_fitted_rent':float(np.exp(predictions[variant][i])) for variant in VARIANTS})
            compared = {}
            for reference in ('baseline','reporting'):
                delta = predictions['values']-predictions[reference]
                compared['values_minus_'+reference] = {'median_absolute_fitted_change_dollars':float(np.median(abs(np.exp(predictions['values'])-np.exp(predictions[reference])))),
                    'maximum_absolute_fitted_change_dollars':float(max(abs(np.exp(predictions['values'])-np.exp(predictions[reference])))),
                    'mean_absolute_log_residual_change':float(np.mean(abs(train.log_rent-predictions['values'])-abs(train.log_rent-predictions[reference]))),
                    'known_feature_subsets':{field:{'rows':int(train[field].notna().sum()),
                        'reference':baseline.metrics(train[train[field].notna()],predictions[reference][train[field].notna()]) if train[field].notna().any() else None,
                        'values':baseline.metrics(train[train[field].notna()],predictions['values'][train[field].notna()]) if train[field].notna().any() else None} for field in FIELDS}}
            summary = {'settings':name,'results':results,'comparisons':compared}
            publish_bundle(root/name/'comparison', {'result.json':canonical(summary)+'\n',
                'fitted-values.jsonl':''.join(canonical(r)+'\n' for r in table)}, {'version':VERSION,'protocol_sha256':ph})
            summaries.append(summary)
        if any(digest(p)!=hashes[p.name] for p in paths):
            raise ValueError('Experiment implementation changed during run')
        return publish_bundle(root/'summary', {'results.json':canonical(summaries)+'\n'},
            {'version':VERSION,'protocol_sha256':ph,'rows':len(train),'fits':len(grid)*len(VARIANTS)})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    prepare_parser=sub.add_parser('prepare'); fit_parser=sub.add_parser('fit')
    for name in ('dataset','evidence','output'):prepare_parser.add_argument('--'+name,type=Path,required=True)
    for name in ('dataset','review','output'):fit_parser.add_argument('--'+name,type=Path,required=True)
    args=vars(parser.parse_args());command=args.pop('command')
    result=prepare(**args) if command=='prepare' else run(**args)
    print(canonical({'version':result['version'],'rows':result['rows']}))
