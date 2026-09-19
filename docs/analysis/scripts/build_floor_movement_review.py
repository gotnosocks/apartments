"""Freeze own-capture evidence for the largest accepted floor-fit movements."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def records(value):
    return [json.loads(line) for line in value.decode().splitlines() if line.strip()]


def run(comparison, dataset, evidence, output):
    comparison, dataset, evidence = map(Path, (comparison, dataset, evidence))
    _, files = _verified_bundle(comparison, retain={'comparison.json', 'residual-movements.jsonl'})
    result = json.loads(files['comparison.json'])
    if result['version'] != 'matched-label-floor-fit-comparison-v1':
        raise ValueError('Expected the accepted matched label-floor comparison')
    if result['fits'][1]['bindings']['source'] != digest(dataset/'complete.json'):
        raise ValueError('Movement review source differs from candidate fit')
    manifest, source = _verified_bundle(dataset, retain={'observations.jsonl', 'floor-label-projection.jsonl'})
    rows = records(source['observations.jsonl'])
    changes = records(source['floor-label-projection.jsonl'])
    by_id = {r['audit_id']: r for r in rows}
    by_change = {r['audit_id']: c for r, c in zip(rows, changes, strict=True)}
    movements = records(files['residual-movements.jsonl'])
    if len(movements) != len(rows) or {r['audit_id'] for r in movements} != set(by_id):
        raise ValueError('Movement and source membership differ')
    by_movement = {r['audit_id']: r for r in movements}
    for movement in movements:
        row = by_id[movement['audit_id']]
        if any(movement[k] != row[k] for k in ('unit_id', 'building', 'source_listing_id', 'asking_rent')):
            raise ValueError('Movement source identity or price differs')
    selected = defaultdict(list)
    for rank, movement in enumerate(result['largest_distinct_unit_movements'], 1):
        if by_movement[movement['audit_id']] != movement:
            raise ValueError('Ranked movement differs from bound full comparison')
        selected[movement['audit_id']].append({'reason': 'largest_distinct_unit_residual_movement', 'rank': rank})
    group_reviews = []
    for key, kind, field in [('largest_unit_offset_movements', 'unit', 'unit_id'),
                             ('largest_common_reference_building_movements', 'building', 'building')]:
        for rank, group in enumerate(result[key][:5], 1):
            choices = [m for m in movements if m[field] == group['id']]
            chosen = min(choices, key=lambda m: (-abs(m['fitted_rent_change']), m['audit_id']))
            selected[chosen['audit_id']].append({'reason': f'largest_{kind}_contribution_movement_example', 'rank': rank})
            group_reviews.append({'kind': kind, 'rank': rank, 'movement': group,
                                  'example_audit_id': chosen['audit_id']})
    captures = load_evidence(dataset, evidence)
    cases = []
    for identity in sorted(selected):
        row = by_id[identity]
        cases.append({'selection_reasons': selected[identity], 'observation': row,
            'movement': by_movement[identity], 'floor_projection': by_change[identity],
            'building_floor_evidence': manifest['building_floor_evidence'].get(row['building'], []),
            'descriptions': captures[identity]})
    return publish_bundle(output, {
        'cases.jsonl': ''.join(canonical(c)+'\n' for c in cases),
        'group-review-examples.json': canonical(group_reviews)+'\n',
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'accepted-floor-fit-movement-source-review-inputs-v1',
        'comparison_manifest_sha256': digest(comparison/'complete.json'),
        'source_manifest_sha256': digest(dataset/'complete.json'),
        'evidence_manifest_sha256': digest(evidence/'complete.json'),
        'cases': len(cases), 'selection_reasons': sum(map(len, selected.values())),
        'policy': 'Review all 25 largest distinct-unit fitted-rent movements, plus the five largest unit-offset and common-reference building-effect movements. Each group example is its largest absolute fitted-rent movement, with audit-ID tie breaking. Selected on in-sample model changes, not a representative panel or holdout. A single building example is not a building-wide adjudication. No corrections applied.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('comparison', 'dataset', 'evidence', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
