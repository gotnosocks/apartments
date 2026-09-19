"""Quantify source-interpretation sensitivities without choosing source truth."""
import argparse
import json
import math
from pathlib import Path

from apartments.bayesian_analysis import BayesianAnalysis
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(experiment, dataset, candidates, output):
    experiment, dataset, candidates = map(Path, (experiment, dataset, candidates))
    _, cf = _verified_bundle(candidates, retain={'cases.jsonl'})
    cases = [json.loads(s) for s in cf['cases.jsonl'].decode().split('\n') if s]
    analysis = BayesianAnalysis.load(experiment, dataset)
    try:
        by_ad = {r['source_listing_id']: r for r in analysis.rows}
        details = []
        for case in cases:
            selected = case['source_record']; row = by_ad[selected['source_listing_id']]
            if any(row[k] != selected[k] for k in ('audit_id', 'unit_id', 'asking_rent', 'period')):
                raise ValueError('Source scenario identity or price differs')
            detail = analysis.detail(row['audit_id'])
            if not detail['contribution_diagnostics']['acceptable']:
                raise ValueError('Case contribution diagnostics failed')
            if not math.isclose(sum(detail['grouped_contributions'].values()), detail['mean_log_rent'], rel_tol=0, abs_tol=1e-10):
                raise ValueError('Log contributions do not add')
            details.append(detail)
        row = by_ad['3223153']
        if row['bedrooms'] != 1: raise ValueError('Bedroom scenario source changed')
        scenario = analysis.counterfactual(row['audit_id'], {'bedrooms': 0})
        row = by_ad['2675026']
        if row['asking_rent'] != 2878: raise ValueError('Net-price review source changed')
        pricing = next(d for d in details if d['audit_id'] == row['audit_id'])
        # Only the arithmetic shift in the observed quote is calculated. We do
        # not transplant the later gross price into the initial event or refit.
        quote = {'source_listing_id': '2675026', 'modeled_initial_ask': 2878,
            'separately_quoted_gross': 3100, 'log_quote_difference': math.log(3100/2878),
            'quote_percent_difference': 100*(3100/2878-1),
            'interpretation': 'A separately stated gross quote, not a replacement historical target. At fixed fitted price the signed log residual would shift by this amount. The apartment layout and gross terms at the initial event remain separate source questions.'}
        summary = {'version': 'laundry-residual-source-interpretation-scenarios-v1', 'cases': len(details),
            'all_contribution_diagnostics_pass': True, 'bedroom_scenario_status': scenario['status'],
            'main_model_changed': False,
            'interpretation': 'The studio scenario holds the fitted unit/building offsets and all other encoded inputs fixed. Closer agreement with asking rent does not resolve the conflicting bedroom evidence and is not a refit of corrected data.'}
        publish_bundle(output, {'summary.json': canonical(summary)+'\n',
            'details.jsonl': ''.join(canonical(d)+'\n' for d in details),
            'studio-scenario.json': canonical(scenario)+'\n', 'price-basis-scenario.json': canonical(quote)+'\n',
            Path(__file__).name: Path(__file__).read_text()},
            {'version': summary['version'], 'fit_manifest_sha256': digest(experiment/'fit/complete.json'),
             'source_manifest_sha256': digest(dataset/'complete.json'),
             'review_candidates_manifest_sha256': digest(candidates/'complete.json')})
        print(canonical({'summary': summary, 'studio': {k: scenario.get(k) for k in ('status', 'delta_percent', 'before_rent', 'after_rent')},
                         'price_basis': quote}), flush=True)
    finally:
        analysis.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('experiment', 'dataset', 'candidates', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
