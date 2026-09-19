"""Inspect sparse and directly corrected cases under both verified posteriors."""
import gc
import json
import math
from pathlib import Path

from apartments.bayesian_analysis import BayesianAnalysis
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def main():
    root = Path(__file__).resolve().parents[3]
    base = root/'data/model'
    comparison = base/'chelsea-reviewed-corrections-fit-comparison-20260919'
    _, files = _verified_bundle(comparison, retain={'comparison.json'})
    compared = json.loads(files['comparison.json'])
    datasets = [base/'chelsea-reviewed-current-analysis-20260918', base/'chelsea-reviewed-floor-masked-analysis-20260918']
    experiments = [base/'chelsea-bayesian-current-floor-disk-20260918', base/'chelsea-bayesian-reviewed-corrections-floor-disk-20260919']
    identifiers = ['4892020', '1306285', '4800947']
    sides = []
    for index, (experiment, dataset) in enumerate(zip(experiments, datasets, strict=True)):
        analysis = BayesianAnalysis.load(experiment, dataset)
        try:
            assert analysis.protocol == compared['fits'][index]['protocol']
            by_ad = {r['source_listing_id']: r['audit_id'] for r in analysis.rows if r['source_listing_id'] in identifiers}
            assert by_ad.keys() == set(identifiers)
            details = [analysis.detail(by_ad[ad]) for ad in identifiers]
            for detail in details:
                assert detail['contribution_diagnostics']['acceptable']
                assert math.isclose(sum(detail['grouped_contributions'].values()), detail['mean_log_rent'], abs_tol=1e-10, rel_tol=0)
            sides.append(details)
        finally:
            analysis.close()
        del analysis
        gc.collect()
    changes = []
    for before, after in zip(*sides, strict=True):
        assert before['audit_id'] == after['audit_id']
        assert before['source_record']['asking_rent'] == after['source_record']['asking_rent']
        a, b = before['grouped_contributions'], after['grouped_contributions']
        assert a.keys() == b.keys()
        grouped = sorted(({'group': k, 'reference_mean_log': a[k], 'candidate_mean_log': b[k],
                           'mean_log_change': b[k]-a[k]} for k in a), key=lambda r: -abs(r['mean_log_change']))
        assert math.isclose(sum(r['mean_log_change'] for r in grouped), after['mean_log_rent']-before['mean_log_rent'], abs_tol=1e-10, rel_tol=0)
        changes.append({'source_listing_id': before['source_record']['source_listing_id'],
            'audit_id': before['audit_id'], 'asking_rent': before['source_record']['asking_rent'],
            'reference_fitted_interval': before['fitted_median_rent'], 'candidate_fitted_interval': after['fitted_median_rent'],
            'reference_diagnostics': before['contribution_diagnostics'], 'candidate_diagnostics': after['contribution_diagnostics'],
            'group_changes': grouped})
    result = {'version': 'corrected-fit-movement-review-v1', 'cases': len(changes),
        'all_contribution_diagnostics_pass': True,
        'interpretation': 'Compare posterior mean log contribution groups, which add exactly. Feature inventories differ by the removed floor-9 threshold; no individual coefficients or independent posterior draws are paired. Fitted dollar medians do not decompose additively. Source changes, induced floor prior changes and Monte Carlo uncertainty all affect this comparison.'}
    publish_bundle(base/'chelsea-corrected-fit-movement-review-20260919', {
        'summary.json': canonical(result)+'\n', 'changes.jsonl': ''.join(canonical(r)+'\n' for r in changes),
        'reference-details.jsonl': ''.join(canonical(r)+'\n' for r in sides[0]),
        'candidate-details.jsonl': ''.join(canonical(r)+'\n' for r in sides[1]),
        Path(__file__).name: Path(__file__).read_text()},
        {'version': result['version'], 'comparison_manifest_sha256': digest(comparison/'complete.json'),
         'fits': [{'fit_manifest_sha256': digest(experiment/'fit/complete.json'), 'source_manifest_sha256': digest(dataset/'complete.json')}
                  for experiment, dataset in zip(experiments, datasets, strict=True)]})
    print(canonical(result), flush=True)
    print(canonical(changes), flush=True)


if __name__ == '__main__':
    main()
