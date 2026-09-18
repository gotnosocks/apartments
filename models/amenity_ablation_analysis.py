"""Summarize verified matched predictions without averaging fold percentages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import amenity_rent_model as model
from . import minimal_rent_model as baseline


def analyze(experiment, output):
    root = Path(experiment)
    protocol = json.loads((root/'protocol.json').read_text())
    expected = digest(root/'protocol.json')
    manifest, files = _verified_bundle(root/'summary', retain={'results.json'})
    if manifest.get('protocol_sha256') != expected:
        raise ValueError('Summary protocol mismatch')
    summary = json.loads(files['results.json'])
    if summary['protocol'] != protocol:
        raise ValueError('Summary protocol contents differ')
    tables = {}
    for split in protocol['splits']:
        name = split['name']
        manifest, files = _verified_bundle(root/name/'comparison', retain={'predictions.jsonl'})
        if manifest.get('protocol_sha256') != expected:
            raise ValueError('Prediction protocol mismatch')
        table = pd.DataFrame(json.loads(line) for line in files['predictions.jsonl'].decode().split('\n') if line.strip())
        if len(table) != split['test_rows'] or table.duplicated(['unit_id','period']).any():
            raise ValueError('Prediction row identity/count mismatch')
        for field in ('asking_rent', *protocol['variants']):
            if not np.isfinite(table[field]).all() or not table[field].gt(0).all():
                raise ValueError('Invalid prediction or target')
        tables[name] = table
    def pool(names, expected_rows, expected_table=None):
        combined = pd.concat([tables[name] for name in names], ignore_index=True)
        if combined.duplicated(['unit_id','period']).any():
            raise ValueError('Building holdouts overlap')
        seen = set()
        for name in names:
            buildings = set(tables[name].building)
            if seen & buildings:
                raise ValueError('Building appears in multiple held-out folds')
            seen.update(buildings)
        if len(combined) != expected_rows:
            raise ValueError('Five building folds do not cover the expected cohort')
        if expected_table is not None:
            identities = lambda frame: set(zip(frame.unit_id, frame.period, frame.audit_id))
            if identities(combined) != identities(expected_table):
                raise ValueError('Crossed folds differ from annual holdout identities')
        metrics = {variant:baseline.metrics(combined, np.log(combined[variant].to_numpy()))
                   for variant in protocol['variants']}
        comparisons = {}
        for reference in ('baseline','missingness'):
            paired = combined[['building','asking_rent']].copy()
            paired['baseline_rent'] = combined[reference]
            paired['amenity_rent'] = combined['full']
            comparisons['full_minus_'+reference] = model.paired_building_comparison(paired, draws=2000)
        return {'rows':len(combined), 'buildings':len(seen), 'metrics':metrics,
                  'comparisons':comparisons,
                  'interpretation':'one held-out prediction per unit-month across five building folds; resampling buildings conditions on already fitted models'}
    names = [f'building-{i}' for i in range(5)]
    pooled = pool(names, protocol['development_rows']) if all(name in tables for name in names) else None
    crossed = {}
    years = sorted({name.split('-')[1] for name in tables if name.startswith('year-') and '-building-' in name})
    for year in years:
        names = [f'year-{year}-building-{i}' for i in range(5)]
        if all(name in tables for name in names):
            annual = tables.get(f'year-{year}')
            expected_rows = len(annual) if annual is not None else sum(len(tables[name]) for name in names)
            crossed[year] = pool(names, expected_rows, annual)
    report = {'version':'amenity-ablation-analysis-v1', 'protocol':protocol,
              'pooled_building_holdouts':pooled, 'pooled_crossed_holdouts':crossed, 'splits':summary['results'],
              'limitations':['Retrospective reconstructed asking rents and later-collected attributes.',
                             'Reused development periods; neither causal effects nor untouched prospective validation.',
                             'Error-difference intervals are not coefficient or individual-prediction intervals.']}
    return publish_bundle(output, {'report.json':canonical(report)+'\n'},
                          {'version':report['version'], 'protocol_sha256':expected,
                           'implementation_sha256':digest(__file__)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.experiment, args.output)
