"""Supported conditional amenity contrasts from a matched Chelsea experiment."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from . import amenity_rent_model as model
from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle

CONTRASTS = [('laundry_type','in_building','in_unit'),
             ('doorman_type','part_time','full_time'),
             ('pet_rules','not_allowed','allowed_restrictions_unknown'),
             ('hvac_type','room_ac','central_ac')]


def category_contrast(fitted, field, before, after, *, baseline_rent=4000.):
    """Exact conditional contrast; interaction-free category effects only."""
    enc = fitted['encoder']
    levels = enc.amenity_categories.get(field, [])
    if before not in levels or after not in levels or '__unknown__' in (before,after):
        raise ValueError('Both explicitly known categories must occur in training')
    start, _ = enc.offsets['amenities']
    positions = [start+enc.amenity_features.index(f'{field}={level}') for level in (before,after)]
    delta = float(fitted['beta'][positions[1]]-fitted['beta'][positions[0]])
    return {'log_rent_difference':delta,'percent_difference':float(100*np.expm1(delta)),
            'dollar_difference_at_reference':float(baseline_rent*np.expm1(delta)),
            'reference_monthly_rent':baseline_rent,
            'interpretation':'conditional fitted association; no causal or statistical-significance claim'}


def analyze(dataset, experiment, output, *, year=2024):
    data, source, _ = model.load_analytical(dataset)
    experiment = Path(experiment)
    protocol = json.loads((experiment/'protocol.json').read_text())
    if source != protocol['source_manifest']:
        raise ValueError('Analytical input differs from the experiment')
    train = data[data.period < f'{year}-01-01']
    rows = [model.feature_record(row) for row in train.to_dict('records')]
    fits, hashes = {}, {}
    for variant in ('buildings','units'):
        root = experiment/f'year-{year}-{variant}'
        fits[variant] = model.load_fit(root)
        hashes[variant] = digest(root/'complete.json')
    contrasts = []
    for field, before, after in CONTRASTS:
        support, buildings = {}, {}
        for level in (before,after):
            matching = [row for row in rows if row.get(field) == level]
            buildings[level] = {r['building'] for r in matching}
            support[level] = {'unit_months':len(matching),
                'units':len({r['unit_id'] for r in matching}), 'buildings':len(buildings[level])}
        effects = {}
        for variant,fitted in fits.items():
            try:
                effects[variant] = category_contrast(fitted,field,before,after)
            except ValueError as error:
                effects[variant] = {'supported':False,'reason':str(error)}
        contrasts.append({'field':field,'before':before,'after':after,'support':support,
                          'buildings_observed_in_both_categories':len(buildings[before]&buildings[after]),
                          'effects':effects})
    report = {'training_end_exclusive':f'{year}-01-01','contrasts':contrasts,
              'limitations':[
                'No coefficient uncertainty estimated in this report; prediction-error bootstrap is a separate quantity.',
                'Building and unit effects compete with correlated amenities; reported contrasts depend on regularization.',
                'Rows reconstruct source advertisements retrospectively; literal evidence does not independently verify historic service.',
                'Room AC has sparse observed support; do not interpret its sign as established market preference.',
                'Physical-floor premiums remain unsupported because no physical floor evidence was recovered.']}
    return publish_bundle(output, {'contrasts.json':canonical(report)+'\n'}, {
        'version':'chelsea-supported-contrasts-v1','experiment_protocol_sha256':digest(experiment/'protocol.json'),
        'fit_manifest_sha256':hashes,'implementation_sha256':digest(__file__),
        'runtime_versions':{p:importlib.metadata.version(p) for p in ('numpy','pandas','scipy','duckdb')}})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--year',type=int,default=2024)
    args=parser.parse_args()
    print(json.dumps(analyze(args.dataset,args.experiment,args.output,year=args.year),indent=2))
