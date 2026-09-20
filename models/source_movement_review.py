"""Decompose the largest source-refit movements using verified joint posteriors."""
from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path

from apartments import bayesian_analysis
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'bayesian-source-movement-review-v1'


def select_cases(report, top):
    if report.get('version') == 'matched-expanded-floor-spline-fit-comparison-v1':
        candidates = report['largest_distinct_unit_movements']
        scope = 'largest_common_distinct_unit_movements'
    elif report.get('version') == 'verified-bayesian-source-sensitivity-v1':
        candidates = report['residuals']['largest_distinct_unit_movements']
        scope = 'largest_common_distinct_unit_movements'
    elif report.get('version') in ('reviewed-quarantine-fit-comparison-v1', 'reviewed-elevator-fit-comparison-v1'):
        candidates = report['residuals']['largest_current_movements']
        scope = 'largest_current_distinct_unit_movements'
    else:
        raise ValueError('Verified source comparison required')
    selected, seen = [], set()
    for case in candidates:
        if case['unit_id'] not in seen:
            selected.append(case)
            seen.add(case['unit_id'])
        if len(selected) == top: break
    if not selected: raise ValueError('No source movement cases available')
    return selected, scope


def compare_details(before, after):
    if (before['audit_id'] != after['audit_id']
            or before['source_record']['asking_rent'] != after['source_record']['asking_rent']):
        raise ValueError('Movement review requires the same observation and asking price')
    for detail in (before, after):
        total = sum(r['mean_log_contribution'] for r in detail['contributions'])
        if not math.isclose(total, detail['mean_log_rent'], rel_tol=0, abs_tol=1e-10):
            raise ValueError('Contribution means do not reconstruct mean log rent')
    a = {r['term']: r for r in before['contributions']}
    b = {r['term']: r for r in after['contributions']}
    if a.keys() != b.keys(): raise ValueError('Contribution representations differ')
    terms = [{'term': key, 'reference_mean_log_contribution': a[key]['mean_log_contribution'],
        'candidate_mean_log_contribution': b[key]['mean_log_contribution'],
        'mean_log_change': b[key]['mean_log_contribution']-a[key]['mean_log_contribution']} for key in a]
    terms.sort(key=lambda r: (-abs(r['mean_log_change']), r['term']))
    groups = sorted(set(before['grouped_contributions']) | set(after['grouped_contributions']))
    grouped = [{'group': k, 'reference': before['grouped_contributions'].get(k, 0.),
        'candidate': after['grouped_contributions'].get(k, 0.),
        'mean_log_change': after['grouped_contributions'].get(k, 0.)-before['grouped_contributions'].get(k, 0.)} for k in groups]
    mean_change = after['mean_log_rent']-before['mean_log_rent']
    if not math.isclose(sum(r['mean_log_change'] for r in terms), mean_change, rel_tol=0, abs_tol=1e-10):
        raise ValueError('Contribution changes do not add up')
    return {'audit_id': before['audit_id'], 'source_listing_id': before['source_record']['source_listing_id'],
        'unit_id': before['source_record']['unit_id'], 'building': before['source_record']['building'],
        'asking_rent': before['source_record']['asking_rent'],
        'reference_fitted_interval': before['fitted_median_rent'], 'candidate_fitted_interval': after['fitted_median_rent'],
        'reference_contribution_diagnostics': before['contribution_diagnostics'],
        'candidate_contribution_diagnostics': after['contribution_diagnostics'],
        'mean_log_rent_change': mean_change, 'group_changes': grouped, 'term_changes': terms,
        'semantics': 'Additive posterior mean log terms, not dollar allocations or causal premiums. Changes compare separate posterior means; draws from different fits are never paired. Median fitted dollars need not decompose as sums of mean-log changes.'}


def run(comparison, reference, candidate, reference_dataset, candidate_dataset, output, *, top=3):
    if type(top) is not int or not 1 <= top <= 10: raise ValueError('Choose 1–10 movement cases')
    cm, cf = _verified_bundle(comparison, retain={'comparison.json'})
    report = json.loads(cf['comparison.json'])
    cases, scope = select_cases(report, top)
    details, sources = [], []
    for index, (experiment, dataset) in enumerate(((reference, reference_dataset), (candidate, candidate_dataset))):
        model = bayesian_analysis.BayesianAnalysis.load(experiment, dataset)
        try:
            if model.protocol != report['fits'][index]['protocol']:
                raise ValueError('Loaded fit differs from comparison')
            reviewed = [model.detail(case['audit_id']) for case in cases]
            details.append(reviewed)
            sources.append({'protocol_manifest_sha256': digest(Path(experiment)/'protocol/complete.json'),
                'fit_manifest_sha256': digest(Path(experiment)/'fit/complete.json'),
                'dataset_manifest_sha256': digest(Path(dataset)/'complete.json')})
        finally:
            model.close()
        del model
        gc.collect()
    changes = [compare_details(a, b) for a, b in zip(*details, strict=True)]
    files = {'changes.jsonl': ''.join(canonical(r)+'\n' for r in changes),
        'reference-details.jsonl': ''.join(canonical(r)+'\n' for r in details[0]),
        'candidate-details.jsonl': ''.join(canonical(r)+'\n' for r in details[1]),
        Path(__file__).name: Path(__file__).read_text(),
        Path(bayesian_analysis.__file__).name: Path(bayesian_analysis.__file__).read_text()}
    return publish_bundle(output, files, {'version': VERSION, 'comparison_manifest_sha256': digest(Path(comparison)/'complete.json'),
        'cases': len(changes), 'case_selection_scope': scope, 'fits': sources,
        'all_case_contribution_diagnostics_pass': all(d['contribution_diagnostics']['acceptable'] for side in details for d in side),
        'implementation_sha256': {Path(p).name: digest(p) for p in (__file__, bayesian_analysis.__file__)}})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('comparison', 'reference', 'candidate', 'reference_dataset', 'candidate_dataset', 'output'):
        p.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    p.add_argument('--top', type=int, default=3)
    result = run(**vars(p.parse_args()))
    print(canonical({k: result[k] for k in ('version', 'cases', 'all_case_contribution_diagnostics_pass')}))
