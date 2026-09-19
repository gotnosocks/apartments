"""Compare the reviewed floor/laundry refit to its exact unmasked predecessor.

This is a source-and-induced-prior sensitivity analysis, not a data-only effect
estimate. It requires completed, converged fits and reconstructs both designs.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from apartments import reviewed_source_lineage
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_report as report
from models import bayesian_feature_sensitivity as common
from models import bayesian_source_sensitivity as source
from models import bayesian_floor_sensitivity as floor
from models.bayesian_feature_design_v2 import load_design


def main():
    root = Path(__file__).resolve().parents[3]
    base = root/'data/model'
    datasets = [base/'chelsea-reviewed-current-analysis-20260918',
                base/'chelsea-reviewed-floor-masked-analysis-20260918']
    experiments = [base/'chelsea-bayesian-current-floor-disk-20260918',
                   base/'chelsea-bayesian-reviewed-corrections-floor-disk-20260919']
    sources = [_verified_bundle(path, retain={'observations.jsonl'}) for path in datasets]
    rows = [report.jsonl(payload['observations.jsonl']) for _, payload in sources]
    assert reviewed_source_lineage.source_lineage(sources[1][0], rows[1]) == sources[0][0]
    changed = []
    for before, after in zip(*rows, strict=True):
        fields = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        if fields:
            assert fields in [['advertised_floor', 'attribute_review_history'],
                              ['attribute_review_history', 'laundry_type']]
            changed.append({'audit_id': after['audit_id'], 'changed_fields': fields,
                            'review': after['attribute_review_history'][-1]})
        if before['analysis_price_basis'] == 'current_capture_gross_ask':
            assert before == after
    assert len(changed) == 18
    fits = []
    with threadpool_limits(limits=1, user_api='blas'):
        for experiment, dataset, records in zip(experiments, datasets, rows, strict=True):
            summary, provenance = report.build_report(experiment, dataset)
            protocol = json.loads(common.bound_bytes(experiment/'protocol', 'protocol.json', provenance['protocol_manifest']))
            reconstruction = source.verify_design(experiment, dataset, protocol, provenance)
            data = pd.DataFrame(records)
            data.period = pd.to_datetime(data.period)
            data.square_feet = pd.to_numeric(data.square_feet, errors='coerce')
            design = load_design(experiment/'fit', data, protocol)
            fits.append({'report': summary, 'protocol': protocol, 'design': design,
                         'reconstruction': reconstruction, 'provenance': provenance,
                         'residuals': report.jsonl(common.bound_bytes(experiment/'fit', 'residuals.jsonl', provenance['fit_manifest']))})
    a, b = fits
    variable = source.SOURCE_FIELDS | {'graph_verification', 'implementation_sha256', 'floor_levels', 'floor_thresholds'}
    assert {k: v for k, v in a['protocol'].items() if k not in variable} == {
        k: v for k, v in b['protocol'].items() if k not in variable}
    old_code, new_code = (f['protocol']['implementation_sha256'] for f in fits)
    assert set(new_code) - set(old_code) == {'reviewed_source_lineage.py'}
    assert set(old_code) <= set(new_code)
    assert {k for k in old_code if old_code[k] != new_code[k]} == {'bayesian_feature_experiment_v3.py'}
    for name in ('time-design.json', 'time-design.npz'):
        assert a['provenance']['fit_manifest']['files'][name] == b['provenance']['fit_manifest']['files'][name]
    # Compare supported common endpoints; never align floor coefficients by position.
    levels = sorted(set(a['design'].floor_levels) & set(b['design'].floor_levels))
    joint = [floor.joint_floor_contrasts(path, fit['protocol'], fit['design'], levels)
             for path, fit in zip(experiments, fits, strict=True)]
    contrasts = []
    for old, new in zip(joint[0]['contrasts'], joint[1]['contrasts'], strict=True):
        assert (old['lower_floor'], old['upper_floor']) == (new['lower_floor'], new['upper_floor'])
        contrasts.append({'lower_floor': old['lower_floor'], 'upper_floor': old['upper_floor'],
                          'reference': old, 'candidate': new,
                          'prior_changed': old['prior_log_sd'] != new['prior_log_sd']})
    indexed = [{r['audit_id']: r for r in fit['residuals']} for fit in fits]
    def movements(identities):
        return [{**{k: indexed[0][identity][k] for k in ('audit_id', 'source_listing_id', 'unit_id', 'building', 'asking_rent')},
                 'reference': indexed[0][identity], 'candidate': indexed[1][identity],
                 'fitted_rent_change': indexed[1][identity]['fitted_rent'] - indexed[0][identity]['fitted_rent']}
                for identity in identities]
    current = movements([r['audit_id'] for r in rows[1] if r['analysis_price_basis'] == 'current_capture_gross_ask'])
    current.sort(key=lambda r: (-abs(r['fitted_rent_change']), r['audit_id']))
    result = {'version': 'reviewed-floor-laundry-fit-comparison-v1', 'cohort': b['report']['cohort'],
        'source_changes': changed, 'joint_floor_contrasts': contrasts,
        'joint_floor_diagnostics': [j['diagnostics'] for j in joint],
        'fits': [{'protocol': f['protocol'], 'diagnostics': f['report']['diagnostics'],
                  'design_reconstruction': f['reconstruction']} for f in fits],
        'residuals': source.matched_residuals(a['residuals'], b['residuals'], a['report'], b['report'], rows[1], changed),
        'current_median_absolute_fitted_change': float(np.median([abs(r['fitted_rent_change']) for r in current])),
        'bathrooms': {name: source.compare_contrasts(a['report']['bathrooms'][name], b['report']['bathrooms'][name], fields)
            for name, fields in [('full_bath_increments', ('log_effect', 'percent_effect')),
                                 ('half_bath_increments', ('log_effect', 'percent_effect')), ('net_balance', ('difference',))]},
        'limitations': ['Removing unsupported floor 9 changes the joint 8-to-10 prior SD from sqrt(2)*0.15 to 0.15. This is not a prior-matched data-only experiment.',
                       'Differences between posterior summaries include Monte Carlo error. They are not paired posterior draws or causal effects.',
                       'Residuals are in-sample review signals; all 172 current observations contribute to both fits.'],
        'main_selection_changed': False}
    files = {'comparison.json': canonical(result)+'\n',
             'current-movements.jsonl': ''.join(canonical(r)+'\n' for r in current),
             'corrected-row-movements.jsonl': ''.join(canonical(r)+'\n' for r in movements([c['audit_id'] for c in changed])),
             Path(__file__).name: Path(__file__).read_text()}
    publish_bundle(base/'chelsea-reviewed-corrections-fit-comparison-20260919', files,
        {'version': result['version'], 'fits': [{'fit_manifest_sha256': digest(path/'fit/complete.json'),
            'protocol_manifest_sha256': digest(path/'protocol/complete.json'),
            'source_manifest_sha256': digest(dataset/'complete.json')} for path, dataset in zip(experiments, datasets)],
         'implementation_sha256': {Path(module.__file__).name: digest(module.__file__)
            for module in (report, common, source, floor, reviewed_source_lineage)}})
    print(canonical({'cohort': result['cohort'], 'current_median_absolute_fitted_change': result['current_median_absolute_fitted_change'],
                     'largest_current_movements': current[:5], 'floor_contrasts': contrasts}), flush=True)


if __name__ == '__main__':
    main()
