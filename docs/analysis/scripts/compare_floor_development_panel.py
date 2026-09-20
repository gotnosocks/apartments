"""Compare the frozen coverage panel without selecting units by new residuals."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def summarize(rows):
    return {'rows': len(rows),
        'reference_median_absolute_log_residual': median(abs(r['reference']['residual_log']) for r in rows),
        'candidate_median_absolute_log_residual': median(abs(r['candidate']['residual_log']) for r in rows),
        'median_absolute_fitted_change': median(abs(r['fitted_rent_change']) for r in rows),
        'maximum_absolute_fitted_change': max(abs(r['fitted_rent_change']) for r in rows)}


def run(panel, comparison, output):
    panel, comparison = Path(panel), Path(comparison)
    pm, pf = _verified_bundle(panel, retain={'cases.jsonl'})
    _, cf = _verified_bundle(comparison, retain={'comparison.json', 'residual-movements.jsonl'})
    result = json.loads(cf['comparison.json'])
    if (pm['version'] != 'floor-source-development-panel-v1' or result['version'] not in
            {'matched-label-floor-fit-comparison-v1', 'matched-floor-elevator-fit-comparison-v1', 'matched-floor-spline-fit-comparison-v1',
             'matched-expanded-floor-spline-fit-comparison-v1'}):
        raise ValueError('Expected frozen coverage panel and accepted matched floor comparison')
    # The expanded comparison proves an exact inverse to the reference source.
    # Retain the original panel's membership and cells, rather than rebuilding
    # them using post-expansion coverage or residual ranks.
    panel_source_index = 0 if result['version'] == 'matched-expanded-floor-spline-fit-comparison-v1' else 1
    if result['fits'][panel_source_index]['bindings']['source'] != pm['dataset_manifest_sha256']:
        raise ValueError('Panel source differs from the bound comparison source')
    cases = [json.loads(line) for line in pf['cases.jsonl'].decode().splitlines()]
    movements = [json.loads(line) for line in cf['residual-movements.jsonl'].decode().splitlines()]
    index = {r['audit_id']: r for r in movements}
    if len(index) != len(movements) or len({c['observation']['unit_id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate comparison observation or panel unit')
    selected, cells = [], defaultdict(list)
    for case in cases:
        source = case['observation']
        movement = index.get(source['audit_id'])
        if movement is None or any(movement[k] != source[k] for k in
                ('audit_id', 'unit_id', 'building', 'source_listing_id', 'period', 'asking_rent')):
            raise ValueError('Fixed panel member absent or source identity/target changed')
        item = {'panel_cell': case['panel_cell'], **movement}
        selected.append(item)
        cells[case['panel_cell']].append(item)
    summary = {**summarize(selected), 'cells': {k: summarize(v) for k, v in sorted(cells.items())},
        'membership_unchanged': True, 'panel_source_fit_index': panel_source_index,
        'interpretation': 'The same 26 preselected source observations, with two units per nonempty floor-band/elevator cell. Coverage development panel, not representative market sampling, a holdout, or a validation accuracy estimate. Aggregates are descriptive only.'}
    return publish_bundle(output, {
        'cases.jsonl': ''.join(canonical(r)+'\n' for r in selected),
        'summary.json': canonical(summary)+'\n',
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'fixed-floor-development-panel-comparison-v1',
        'panel_manifest_sha256': digest(panel/'complete.json'),
        'comparison_manifest_sha256': digest(comparison/'complete.json'),
        'fit_bindings': [f['bindings'] for f in result['fits']], 'rows': len(selected)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('panel', 'comparison', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
