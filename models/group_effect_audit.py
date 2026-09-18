"""Rank fitted group offsets with support and reproducible source-linked cases."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

from apartments import robust_pricing
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'group-effect-source-audit-v1'


def summarize_group(kind, key, effect, rows, penalty):
    weights = [min(1.0, .20 / max(abs(r['log_residual']), 1e-12)) for r in rows]
    weight_sum = math.fsum(weights)
    return {'kind': kind, 'group_id': key, 'log_effect': effect,
            'conditional_multiplier_percent': 100 * math.expm1(effect),
            'rows': len(rows), 'units': len({r['unit_id'] for r in rows}),
            'advertisements': len({r['source_listing_id'] for r in rows}),
            'months': len({r['period'] for r in rows}),
            'first_month': min(r['period'] for r in rows), 'last_month': max(r['period'] for r in rows),
            'building_ids': sorted({r['building_id'] for r in rows}),
            'median_ask': statistics.median(r['asking_rent'] for r in rows),
            'median_log_residual': statistics.median(r['log_residual'] for r in rows),
            'maximum_absolute_log_residual': max(abs(r['log_residual']) for r in rows),
            'huber_weight_sum': weight_sum, 'downweighted_rows': sum(w < .999 for w in weights),
            'ridge_penalty': penalty,
            'conditional_shrinkage_factor': weight_sum / (weight_sum + penalty),
            'conditional_shrinkage_interpretation': 'Single-coordinate ridge factor holding all other effects and final Huber weights fixed; not effective sample size, uncertainty or marginal model shrinkage.'}


def select_groups(rankings, top):
    if not isinstance(top, int) or top < 1:
        raise ValueError('top must be a positive integer')
    selected = []
    for kind in ('building', 'unit'):
        group = [r for r in rankings if r['kind'] == kind]
        for tail, sign in [('positive', 1), ('negative', -1)]:
            candidates = sorted((r for r in group if sign * r['log_effect'] > 0),
                                key=lambda r: (-sign * r['log_effect'], r['group_id']))[:top]
            selected.extend({**r, 'tail': tail, 'tail_rank': i + 1} for i, r in enumerate(candidates))
    return selected


def representative_rows(rows):
    """One typical ask, one largest residual and one latest case, deduplicated."""
    median = statistics.median(r['asking_rent'] for r in rows)
    candidates = [('median_ask', min(rows, key=lambda r: (abs(r['asking_rent'] - median), r['audit_id']))),
                  ('largest_absolute_residual', min(rows, key=lambda r: (-abs(r['log_residual']), r['audit_id']))),
                  ('latest', min(rows, key=lambda r: (-int(r['period'].replace('-', '')), r['audit_id'])))]
    chosen = {}
    for reason, row in candidates:
        chosen.setdefault(row['audit_id'], {'row': row, 'selection_reasons': []})['selection_reasons'].append(reason)
    return list(chosen.values())


def run(model_bundle, dataset, descriptions, protocol, output, top=3):
    model = robust_pricing.RobustPricingModel.load(model_bundle)
    dm, df = _verified_bundle(dataset, retain={'observations.jsonl'})
    em, ef = _verified_bundle(descriptions, retain={'evidence.jsonl'})
    pm, pf = _verified_bundle(protocol, retain={'protocol.json'})
    if dm != model.artifact['training']['source_manifest'] or em['dataset_manifest'] != dm:
        raise ValueError('Exact model, dataset and description membership is required')
    if hashlib.sha256(canonical(json.loads(pf['protocol.json'])).encode()).hexdigest() != model.manifest['revision_protocol_sha256']:
        raise ValueError('Protocol does not belong to model')
    settings = json.loads(pf['protocol.json'])['settings']
    rows = [json.loads(line) for line in df['observations.jsonl'].decode().split('\n') if line]
    by_id = {r['audit_id']: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError('Duplicate analytical row')
    evidence = defaultdict(list)
    for line in ef['evidence.jsonl'].decode().split('\n'):
        if not line:
            continue
        item = json.loads(line)
        original = by_id.get(item['audit_id'])
        if original is None or any(item[k] != original[k] for k in ('unit_id', 'building_id', 'source_listing_id')):
            raise ValueError('Description identity mismatch')
        if item.get('description') is not None and hashlib.sha256(item['description'].encode()).hexdigest() != item['description_sha256']:
            raise ValueError('Description hash mismatch')
        evidence[item['audit_id']].append(item)
    groups = {'building': defaultdict(list), 'unit': defaultdict(list)}
    for row in rows:
        fitted = model.predict(row, row['period'])['predicted_rent']
        row['fitted_rent'] = fitted
        row['log_residual'] = math.log(row['asking_rent'] / fitted)
        for kind in groups:
            groups[kind][row[kind + '_id']].append(row)
    rankings = []
    for kind in groups:
        a, b = model.encoder['offsets'][kind]
        keys = model.encoder[kind + 's']
        if set(keys) != set(groups[kind]) or b - a != len(keys):
            raise ValueError('Group membership mismatch')
        rankings.extend(summarize_group(kind, key, float(effect), groups[kind][key], settings[kind + '_penalty'])
                        for key, effect in zip(keys, model.artifact['coefficients'][a:b]))
    rankings.sort(key=lambda r: (r['kind'], -r['log_effect'], r['group_id']))
    selected = select_groups(rankings, top)
    cases = []
    for group in selected:
        for case in representative_rows(groups[group['kind']][group['group_id']]):
            row = case['row']
            cases.append({'kind': group['kind'], 'group_id': group['group_id'], 'tail': group['tail'],
                          'tail_rank': group['tail_rank'], 'selection_reasons': case['selection_reasons'],
                          'source_record': row, 'descriptions': evidence[row['audit_id']],
                          'advertisement_url': 'https://streeteasy.com/rental/' + str(row['source_listing_id'])})
    summary = {'version': VERSION, 'rows': len(rows), 'buildings': len(groups['building']),
               'units': len(groups['unit']), 'selected_groups': len(selected), 'cases': len(cases),
               'unique_case_rows': len({r['source_record']['audit_id'] for r in cases}),
               'cases_without_description': sum(not r['descriptions'] for r in cases),
               'settings': settings,
               'interpretation': 'Offsets are regularized conditional log adjustments, not standalone market or causal premiums. Unit offsets are residual within building. Repeated advertisements are dependent support. Group offsets absorb omitted attributes and data errors; a small fitted residual does not establish correct data.'}
    lines = ['# Building and unit offset review queue', '', summary['interpretation'], '',
             '| Kind | Tail | Group | Offset | Rows | Units | Ads | First / last month | Median residual |',
             '| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: |']
    for r in selected:
        lines.append(f"| {r['kind']} | {r['tail']} | {r['group_id']} | {r['conditional_multiplier_percent']:+.1f}% | {r['rows']} | {r['units']} | {r['advertisements']} | {r['first_month'][:7]} / {r['last_month'][:7]} | {100 * math.expm1(r['median_log_residual']):+.1f}% |")
    return publish_bundle(output, {'rankings.jsonl': ''.join(canonical(r) + '\n' for r in rankings),
        'selected-groups.json': canonical(selected) + '\n', 'source-cases.jsonl': ''.join(canonical(r) + '\n' for r in cases),
        'summary.json': canonical(summary) + '\n', 'report.md': '\n'.join(lines) + '\n',
        'group_effect_audit.py': Path(__file__).read_text()},
        {'version': VERSION, 'model_manifest': model.manifest, 'dataset_manifest': dm,
         'description_manifest': em, 'protocol_manifest': pm, 'top_per_tail': top,
         'implementation_sha256': digest(__file__), 'runtime_sha256': digest(robust_pricing.__file__)})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('model', 'dataset', 'descriptions', 'protocol', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--top', type=int, default=3)
    args = p.parse_args()
    result = run(args.model, args.dataset, args.descriptions, args.protocol, args.output, args.top)
    print(canonical({'output': str(args.output), 'files': result['files']}))
