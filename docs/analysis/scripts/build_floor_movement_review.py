"""Freeze own-capture evidence for the largest accepted floor-fit movements."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from apartments import floor_label_projection, expanded_floor_projection, residual_scope_projection
from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments.reviewed_cohort_quarantine import records_hash, sha


def records(value):
    return [json.loads(line) for line in value.decode().split('\n') if line.strip()]


EXPANDED_COMPARISON = 'matched-expanded-floor-spline-fit-comparison-v1'
SCOPE_COMPARISON = 'matched-residual-scope-spline-fit-comparison-v1'
LEGACY_COMPARISONS = {'matched-label-floor-fit-comparison-v1', 'matched-floor-spline-fit-comparison-v1'}


def verified_floor_source(manifest, source, comparison_version):
    """Bind both displayed floor stages to the exact ordered source revision."""
    if comparison_version == SCOPE_COMPARISON:
        if (manifest.get('version') != residual_scope_projection.VERSION
                or residual_scope_projection.SIDECAR not in source):
            raise ValueError('Missing residual-scope source or quarantine sidecar')
        kept = records(source['observations.jsonl'])
        parent, restored = residual_scope_projection.parent_rows(manifest, kept,
            records(source[residual_scope_projection.SIDECAR]))
        inherited = {**source, 'observations.jsonl': ''.join(canonical(r)+'\n' for r in restored).encode()}
        inherited.pop(residual_scope_projection.SIDECAR)
        rows, old_changes, expanded_changes, evidence = verified_floor_source(parent, inherited, EXPANDED_COMPARISON)
        # Inherited floor sidecars still include the quarantined observations.
        # Index them by restored identity before selecting retained rows.
        index = {r['audit_id']: (old, new) for r, old, new in
                 zip(rows, old_changes, expanded_changes, strict=True)}
        return kept, [index[r['audit_id']][0] for r in kept], [index[r['audit_id']][1] for r in kept], evidence
    if residual_scope_projection.SIDECAR in source:
        raise ValueError('Unexpected residual-scope sidecar for floor comparison')
    expanded = comparison_version == EXPANDED_COMPARISON
    expected = expanded_floor_projection.VERSION if expanded else floor_label_projection.VERSION
    if comparison_version not in LEGACY_COMPARISONS | {EXPANDED_COMPARISON} or manifest.get('version') != expected:
        raise ValueError('Floor comparison and candidate source versions differ')
    required = {'observations.jsonl', floor_label_projection.SIDECAR}
    if expanded:
        required.add(expanded_floor_projection.SIDECAR)
    if not required <= source.keys():
        raise ValueError('Missing bound floor projection observations or sidecar')
    rows = records(source['observations.jsonl'])
    changes = records(source[floor_label_projection.SIDECAR])
    if len({row['audit_id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate source observation identity')
    expanded_changes = None
    if expanded:
        expanded_changes = records(source[expanded_floor_projection.SIDECAR])
        parent, _ = expanded_floor_projection.parent_rows(manifest, rows, expanded_changes)
        embedded = [change['original_change'] for change in expanded_changes]
        if (records_hash(changes) != parent['files'][floor_label_projection.SIDECAR]
                or sha(changes) != sha(embedded)):
            raise ValueError('Displayed original floor sidecar differs from expanded source ancestry')
        building_evidence = manifest['policy']['building_floor_evidence']
    else:
        if expanded_floor_projection.SIDECAR in source:
            raise ValueError('Unexpected expanded floor sidecar for legacy comparison')
        floor_label_projection.parent_rows(manifest, rows, changes)
        building_evidence = manifest['building_floor_evidence']
    return rows, changes, expanded_changes, building_evidence


def run(comparison, dataset, evidence, output):
    comparison, dataset, evidence = map(Path, (comparison, dataset, evidence))
    _, files = _verified_bundle(comparison, retain={'comparison.json', 'residual-movements.jsonl'})
    result = json.loads(files['comparison.json'])
    if result['version'] not in LEGACY_COMPARISONS | {EXPANDED_COMPARISON, SCOPE_COMPARISON}:
        raise ValueError('Expected the accepted matched label-floor comparison')
    if result['fits'][1]['bindings']['source'] != digest(dataset/'complete.json'):
        raise ValueError('Movement review source differs from candidate fit')
    manifest, source = _verified_bundle(dataset, retain={'observations.jsonl', floor_label_projection.SIDECAR,
        expanded_floor_projection.SIDECAR, residual_scope_projection.SIDECAR})
    rows, changes, expanded_changes, building_evidence = verified_floor_source(manifest, source, result['version'])
    by_id = {r['audit_id']: r for r in rows}
    by_change = {r['audit_id']: c for r, c in zip(rows, changes, strict=True)}
    by_expanded = ({r['audit_id']: c for r, c in zip(rows, expanded_changes, strict=True)}
                   if expanded_changes is not None else None)
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
    floor_manifest = manifest['source_manifest'] if result['version'] == SCOPE_COMPARISON else manifest
    by_mask = {mask['audit_id']: mask for mask in floor_manifest.get('policy', {}).get('floor_masks', [])}
    cases = []
    for identity in sorted(selected):
        row = by_id[identity]
        case = {'selection_reasons': selected[identity], 'observation': row,
            'movement': by_movement[identity], 'floor_projection': by_change[identity],
            'building_floor_evidence': building_evidence.get(row['building'], []),
            'descriptions': captures[identity]}
        if by_expanded is not None:
            case['expanded_floor_projection'] = by_expanded[identity]
            case['expanded_floor_mask'] = by_mask.get(identity)
        cases.append(case)
    return publish_bundle(output, {
        'cases.jsonl': ''.join(canonical(c)+'\n' for c in cases),
        'group-review-examples.json': canonical(group_reviews)+'\n',
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'accepted-floor-fit-movement-source-review-inputs-v1',
        'comparison_manifest_sha256': digest(comparison/'complete.json'),
        'source_manifest_sha256': digest(dataset/'complete.json'),
        'source_projection_version': manifest['version'],
        'evidence_manifest_sha256': digest(evidence/'complete.json'),
        'cases': len(cases), 'selection_reasons': sum(map(len, selected.values())),
        'policy': 'Review all 25 largest distinct-unit fitted-rent movements, plus the five largest unit-offset and common-reference building-effect movements. Each group example is its largest absolute fitted-rent movement, with audit-ID tie breaking. Selected on in-sample model changes, not a representative panel or holdout. A single building example is not a building-wide adjudication. No corrections applied.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('comparison', 'dataset', 'evidence', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
