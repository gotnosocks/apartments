"""Matched robust baseline/amenity experiments on verified historical observations.

Run as uv run --locked --extra model python -m models.amenity_rent_model. This is retrospective research:
advertisement attributes were collected later than their source price dates.
"""
from __future__ import annotations

import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
os.environ.setdefault('OMP_NUM_THREADS', '2')
import numpy as np
import pandas as pd
from scipy import sparse

from . import minimal_rent_model as baseline
from apartments import pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'chelsea-matched-amenities-v1'
NUMERIC = ('listed_floor', 'physical_floor', 'elevator', 'physical_floor_x_elevator',
           'floor_label_gap', *[f'{field}.{level}' for field, levels in pricing.EXPOSURES.items() for level in levels])
CATEGORIES = ('laundry_type', 'doorman_type', 'hvac_type', 'pet_rules')
SETTINGS = {'building_penalty': 10., 'unit_penalty': 8., 'trend_penalty': 1000., 'amenity_penalty': 10.}


def feature_record(row):
    cleaned = {key: None if value is None or (not isinstance(value,(dict,list,tuple,set)) and pd.isna(value)) else value
               for key,value in row.items()}
    record = pricing._normalize(cleaned)
    record['observed_at'] = str(row.get('period', row.get('observed_at')))
    return record


class AmenityEncoder(baseline.Encoder):
    """Extend the proven robust design; preserve train-only means/vocabularies."""
    def __init__(self, train, unit_effect=True):
        super().__init__(train, unit_effect)
        rows = [feature_record(row) for row in train.to_dict('records')]
        raw = [pricing._raw_features(row, '2000-01-01') for row in rows]
        self.amenity_numeric = {}
        for key in NUMERIC:
            values = [r[key] for r in raw if r[key] is not None]
            self.amenity_numeric[key] = {
                'center': float(np.mean(values)) if values else 0.,
                'scale': max(float(np.std(values)), 1e-8) if values else 1.,
                'known': len(values), 'unknown': len(raw)-len(values),
                'unique_values': len(set(values)),
            }
        self.amenity_categories = {
            key: sorted({pricing._category(row.get(key)) for row in rows}) for key in CATEGORIES}
        self.amenity_features = [item for key in NUMERIC for item in (key, key+'.unknown')]
        self.amenity_features.extend(f'{key}={value}' for key, values in self.amenity_categories.items() for value in values)
        start = self.n_parameters
        self.n_parameters += len(self.amenity_features)
        self.offsets['amenities'] = (start, self.n_parameters)
        self.amenity_category_counts = {key: dict(Counter(pricing._category(r.get(key)) for r in rows)) for key in CATEGORIES}

    def matrix(self, data):
        core = super().matrix(data)
        rows = []
        for original in data.to_dict('records'):
            row = feature_record(original)
            raw = pricing._raw_features(row, '2000-01-01')
            values = []
            for key in NUMERIC:
                support = self.amenity_numeric[key]
                value = raw[key]
                # No magnitude effect for constant or entirely unobserved evidence.
                values.extend([(value-support['center'])/support['scale']
                               if value is not None and support['unique_values'] > 1 else 0.,
                               float(value is None)])
            for key in CATEGORIES:
                levels = self.amenity_categories[key]
                value = pricing._category(row.get(key))
                centers = getattr(self, 'amenity_category_centers', {}).get(key)
                if centers is None:
                    values.extend(float(value == level) for level in levels)
                else:
                    # Known-only contrasts cannot encode the known/unknown mean
                    # difference a second time with a different ridge penalty.
                    values.extend(float(value == '__unknown__') if level == '__unknown__'
                                  else float(value == level)-centers[level] if value in centers
                                  else 0. for level in levels)
            rows.append(values)
        extra = sparse.csr_matrix(np.asarray(rows).reshape(len(data), len(self.amenity_features)))
        if hasattr(self,'amenity_active_columns'):
            extra = extra.multiply(np.asarray(self.amenity_active_columns,dtype=float))
        return sparse.hstack([core, extra], format='csr')

    def penalty(self, settings):
        core = super().penalty(settings)
        start, stop = self.offsets['amenities']
        extra = sparse.hstack([sparse.csr_matrix((stop-start, start)),
                               sparse.eye(stop-start)*np.sqrt(settings['amenity_penalty'])], format='csr')
        return sparse.vstack([core, extra], format='csr')

    def metadata(self):
        result = {**super().metadata(), 'amenity_features': self.amenity_features,
                'amenity_numeric': self.amenity_numeric, 'amenity_categories': self.amenity_categories,
                'amenity_category_counts': self.amenity_category_counts, 'model_version': VERSION}
        if hasattr(self,'amenity_active_columns'):
            result['amenity_active_columns'] = self.amenity_active_columns
            result['ablation_variant'] = self.ablation_variant
        if hasattr(self,'amenity_category_centers'):
            result['amenity_category_centers'] = self.amenity_category_centers
        return result


def load_analytical(root):
    manifest, content = _verified_bundle(root, retain={'observations.jsonl'})
    if manifest.get('dataset_version') != 'historical-own-advertisement-v1':
        raise ValueError('Verified historical own-advertisement analytical data required')
    rows = [json.loads(line) for line in content['observations.jsonl'].decode().split('\n') if line.strip()]
    data = pd.DataFrame(rows)
    data['period'] = pd.to_datetime(data.price_at, utc=True).dt.tz_localize(None).dt.to_period('M').dt.to_timestamp()
    data['building'] = data.building_id
    data['asking_rent'] = pd.to_numeric(data.rent, errors='coerce')
    data['square_feet'] = pd.to_numeric(data.get('square_feet'), errors='coerce')
    reasons = pd.Series('', index=data.index)
    def exclude(reason, condition):
        reasons.loc[reasons.eq('') & condition.fillna(True)] = reason
    exclude('invalid_identity', data.unit_id.isna() | data.building.isna())
    exclude('invalid_rent', ~data.asking_rent.between(750, 50000) | ~np.isfinite(data.asking_rent))
    exclude('invalid_layout', ~data.bedrooms.between(0, 5) | data.bedrooms.mod(1).ne(0)
            | ~data.bathrooms.between(1, 5) | data.bathrooms.mul(2).mod(1).ne(0))
    for flag in ('furnished', 'short_term', 'concession'):
        if flag in data:
            exclude(flag, data[flag].map(lambda x: pricing._boolean(x) == 1))
    data['exclusion_reason'] = reasons
    good = data[reasons.eq('')].copy()
    # Own-advertisement observations can repeat a unit/month. Retain one whole
    # row, never construct amenities from unrelated rows. Conflicting layout is
    # excluded; equivalent layouts use the latest initial-ask date in that month.
    layouts = good.groupby(['unit_id','period'])[['bedrooms','bathrooms']].nunique()
    conflicts = layouts[(layouts.bedrooms > 1) | (layouts.bathrooms > 1)].index
    mask = pd.MultiIndex.from_frame(good[['unit_id','period']]).isin(conflicts)
    conflict_rows = int(mask.sum())
    good = good[~mask].sort_values(['price_at','unit_id','source_listing_id','audit_id'], kind='stable')
    before = len(good)
    good = good.drop_duplicates(['unit_id','period'], keep='last').sort_values(['period','unit_id']).reset_index(drop=True)
    good.loc[~good.square_feet.between(150, 6000), 'square_feet'] = np.nan
    good['log_rent'] = np.log(good.asking_rent)
    good['listing_ids'] = good.source_listing_id.map(lambda value:json.dumps([str(value)]))
    coverage = {'input_rows': len(data), 'exclusions': dict(Counter(reasons[reasons.ne('')])),
                'conflicting_unit_month_rows': conflict_rows, 'superseded_unit_month_rows': before-len(good),
                'retained_unit_months': len(good), 'units': int(good.unit_id.nunique()),
                'buildings': int(good.building.nunique()),
                'sample_rule': 'latest-initial-own-advertisement-in-unit-month; conflicting-layout-months-excluded',
                'time_basis': 'retrospective_source_event_dates; later_collected_attributes'}
    return good, manifest, coverage


def paired_building_comparison(table, *, draws=400, seed=20260918):
    """Paired uncertainty on mean absolute log error, resampling whole buildings."""
    table = table.copy()
    table['difference'] = abs(np.log(table.amenity_rent/table.asking_rent)) - abs(np.log(table.baseline_rent/table.asking_rent))
    groups = table.groupby('building').difference.agg(['sum','count'])
    rng = np.random.default_rng(seed)
    samples = []
    sums, counts = groups['sum'].to_numpy(), groups['count'].to_numpy()
    for _ in range(draws):
        index = rng.integers(0, len(groups), size=len(groups))
        samples.append(float(sums[index].sum()/counts[index].sum()))
    return {'metric': 'amenity_minus_baseline_mean_absolute_log_error',
            'difference': float(table.difference.mean()), 'interval_95': np.quantile(samples,[.025,.975]).tolist(),
            'buildings': len(groups), 'resamples': draws,
            'interpretation': 'negative favors amenities; exploratory conditional on this cohort and protocol'}


def load_fit(root, variant='amenities'):
    _, files = _verified_bundle(root, retain={'models.json'})
    saved = json.loads(files['models.json'])[variant]
    metadata = saved['encoder']
    cls = AmenityEncoder if metadata.get('model_version') == VERSION else baseline.Encoder
    enc = cls.__new__(cls)
    for key, value in metadata.items():
        setattr(enc,key,value)
    enc.periods = pd.DatetimeIndex(pd.to_datetime(metadata['periods']))
    return {'encoder':enc,'beta':np.array(saved['beta']),'center':saved['center']}


def run(dataset, output, *, years=(2019, 2021, 2023, 2024), min_rows=100):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.experiment.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _run(dataset,root,years=years,min_rows=min_rows)


def _run(dataset, output, *, years, min_rows):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    data, source, coverage = load_analytical(dataset)
    # All 2025+ outcomes are outside this development experiment. Those periods
    # already informed earlier models and are not newly untouched final tests.
    data = data[data.period < '2025-01-01'].copy()
    implementation = hashlib.sha256(''.join(digest(p) for p in [__file__,baseline.__file__,pricing.__file__]).encode()).hexdigest()
    protocol = {'version': VERSION, 'source_manifest': source, 'coverage': coverage,
                'settings': SETTINGS, 'years': list(years), 'min_rows': min_rows,
                'implementation_sha256': implementation,
                'evaluation': 'exploratory retrospective development; not historical information-set forecasting',
                'historical_data_end_exclusive': '2025-01-01',
                'building_holdout': 'sha256(unit-independent building identity) mod 5 == 0',
                'unit_effect_variants': [False, True]}
    plan = root/'protocol.json'
    if plan.exists() and json.loads(plan.read_text()) != protocol:
        raise ValueError('Experiment protocol changed; choose a new directory')
    if not plan.exists():
        plan.write_text(canonical(protocol)+'\n')
    splits = []
    for year in years:
        train = data[data.period < f'{year}-01-01']
        test = data[(data.period >= f'{year}-01-01') & (data.period < f'{year+1}-01-01')]
        splits.append((f'year-{year}', train, test))
    held = {b for b in data.building.unique() if int(hashlib.sha256(b.encode()).hexdigest()[:8],16)%5 == 0}
    splits.append(('unseen-buildings', data[~data.building.isin(held)], data[data.building.isin(held)]))
    results = []
    for name, train, test in splits:
        if min(len(train),len(test)) < min_rows:
            raise ValueError(f'Insufficient rows in {name}')
        for units in (False, True):
            run_id = name + ('-units' if units else '-buildings')
            destination = root/run_id
            if (destination/'complete.json').exists():
                m, content = _verified_bundle(destination, retain={'result.json'})
                if m.get('protocol_sha256') != digest(plan):
                    raise ValueError('Existing result belongs to another protocol')
                results.append(json.loads(content['result.json']))
                continue
            print(canonical({'phase':'fitting','fold':run_id,'train':len(train),'test':len(test)}),flush=True)
            fits = {}
            for key, encoder in [('baseline', baseline.Encoder), ('amenities', AmenityEncoder)]:
                fits[key] = baseline.fit(train, SETTINGS, unit_effect=units, iterations=12, encoder_class=encoder)
                change = fits[key]['robust_objective_relative_change']
                if change is None or change > 1e-5:
                    raise ValueError(f'Robust objective has not converged: {run_id}/{key}: {change}')
            table = test[['unit_id','building','period','asking_rent']].copy()
            table['baseline_rent'] = np.exp(baseline.predict(fits['baseline'], test))
            table['amenity_rent'] = np.exp(baseline.predict(fits['amenities'], test))
            result = {'fold':run_id,'training_rows':len(train),'test_rows':len(test),
                      'training_end':str(train.period.max().date()),'test_start':str(test.period.min().date()),
                      'metrics': {key:baseline.metrics(test,baseline.predict(model,test)) for key,model in fits.items()},
                      'paired_building_comparison':paired_building_comparison(table),
                      'amenity_support':fits['amenities']['encoder'].metadata(),
                      'convergence':{key:{'solves':model['solves'],'objective_relative_change':model['robust_objective_relative_change']} for key,model in fits.items()}}
            serialized = {}
            for key, model in fits.items():
                serialized[key] = {'encoder':model['encoder'].metadata(),'beta':model['beta'].tolist(),'center':model['center']}
            table['period'] = table.period.dt.strftime('%Y-%m-%d')
            publish_bundle(destination, {'result.json':canonical(result)+'\n',
                'models.json':canonical(serialized)+'\n','predictions.jsonl':table.to_json(orient='records',lines=True)},
                {'version':VERSION,'protocol_sha256':digest(plan)})
            results.append(result)
            (root/'progress.json').write_text(canonical({'phase':'running','completed_folds':[r['fold'] for r in results]})+'\n')
    summary = {'protocol':protocol,'folds':[{k:v for k,v in r.items() if k != 'amenity_support'} for r in results]}
    publish_bundle(root/'summary', {'results.json':canonical(summary)+'\n'}, {'version':VERSION,'protocol_sha256':digest(plan)})
    (root/'progress.json').write_text(canonical({'phase':'complete','completed_folds':[r['fold'] for r in results]})+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--years', type=int, nargs='+', default=[2019,2021,2023,2024])
    args = parser.parse_args()
    run(args.dataset,args.output,years=tuple(args.years))
