"""Verify comparison inputs while the corrected model is still sampling."""
import json
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import elevator_fit_comparison as comparison


def run():
    prefix = Path('data/model')
    experiments = [prefix/name for name in (
        'chelsea-bayesian-reviewed-price-basis-complete-disk-20260919',
        'chelsea-bayesian-reviewed-elevator-disk-20260919')]
    datasets = [prefix/name for name in (
        'chelsea-reviewed-price-basis-complete-analysis-20260919',
        'chelsea-reviewed-elevator-analysis-20260919')]
    before, after, changes = comparison.verify_revision(*datasets)
    fits, bindings = [], []
    for root, dataset, rows in zip(experiments, datasets, (before, after), strict=True):
        _, files = _verified_bundle(root/'protocol', retain={'protocol.json'})
        protocol = json.loads(files['protocol.json'])
        source = json.loads((dataset/'complete.json').read_text())
        if (protocol['source_manifest_sha256'] != digest(dataset/'complete.json')
                or protocol['source_observations_sha256'] != source['files']['observations.jsonl']):
            raise ValueError('Protocol is not bound to the exact revised source')
        frame = pd.DataFrame(rows)
        frame.period = pd.to_datetime(frame.period)
        frame.square_feet = pd.to_numeric(frame.square_feet, errors='coerce')
        design = comparison.q.load_design(root/'fit', frame, protocol)
        fits.append({'protocol': protocol, 'design': design, 'data': frame})
        bindings.append({'protocol_manifest_sha256': digest(root/'protocol/complete.json'),
            'source_manifest_sha256': digest(dataset/'complete.json'),
            'saved_design_sha256': {name: digest(root/'fit'/name) for name in
                ('feature-design.json', 'time-design.json', 'time-design.npz')}})
    changed_code = comparison.check_protocols(*(fit['protocol'] for fit in fits))
    comparison.check_designs(*fits)
    result = {'version': 'elevator-comparison-input-check-v1', 'changed_rows': len(changes),
        'rows': len(after), 'unchanged_membership_prices_and_unrelated_columns': True,
        'changed_source_readers': changed_code,
        'elevator_normalization': [fit['design'].numeric['elevator'] for fit in fits],
        'contrasts': [comparison.elevator_vectors(fit['design'], fit['data']) for fit in fits],
        'fits': bindings,
        'scope': 'Exact source inverse and protocol/saved-design check only. No posterior comparison or model selection. Completed comparison will independently reconstruct both designs and verify posterior diagnostics.'}
    files = {'inputs.json': canonical(result)+'\n', Path(__file__).name: Path(__file__).read_text(),
             Path(comparison.__file__).name: Path(comparison.__file__).read_text()}
    publish_bundle(prefix/'chelsea-elevator-comparison-inputs-20260919', files,
                   {'version': result['version'], 'fits': bindings})
    print(canonical({'changed_rows': len(changes), 'rows': len(after),
                     'raw_elevator_prior_sd': [r[0]['raw_contrast_prior_sd'] for r in result['contrasts']]}), flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1, user_api='blas'):
        run()
