"""Publish callback-bounded CPU ESS rates for the completed Chelsea benchmark."""
import io
import json
from pathlib import Path

import pandas as pd

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import sampler_efficiency as metrics


def main():
    root = Path(__file__).resolve().parents[3]
    experiment = root/'data/model/chelsea-bayesian-current-floor-disk-20260918'
    progress = root/'data/model/chelsea-nutpie-steady-throughput-20260918'
    recovery = root/'data/model/chelsea-current-floor-trace-recovery-20260918/validation'
    output = root/'data/model/chelsea-nutpie-wall-efficiency-20260919'
    protocol_manifest, protocol_files = _verified_bundle(experiment/'protocol', retain={'protocol.json'})
    protocol = json.loads(protocol_files['protocol.json'])
    fit_manifest, fit = _verified_bundle(experiment/'fit', retain={
        'parameter-diagnostics.csv', 'derived-diagnostics.csv', 'summary.json'})
    _, recovered = _verified_bundle(recovery, retain={'sampler-progress.json', 'recovery.json'})
    _, captured = _verified_bundle(progress, retain={'sampling-progress.jsonl'})
    recovered_metadata = json.loads(recovered['recovery.json'])
    if (recovered_metadata['protocol_sha256'] != protocol_manifest['protocol_sha256']
            or fit_manifest['protocol_sha256'] != protocol_manifest['protocol_sha256']
            or recovered_metadata['posterior_sha256'] != fit_manifest['files']['posterior.nc']):
        raise ValueError('Timing recovery and completed fit must refer to the same draw archive')
    events = [json.loads(line) for line in captured['sampling-progress.jsonl'].splitlines()]
    events.append(json.loads(recovered['sampler-progress.json']))
    bounds = metrics.retained_wall_bounds(events, protocol['tune'], protocol['draws'], protocol['chains'])
    denominators = {'retained_wall_lower_rate': bounds['retained_wall_seconds_upper'],
                    'retained_wall_upper_rate': bounds['retained_wall_seconds_lower']}
    summary = json.loads(fit['summary.json'])
    families = {name: summary[key] for name, key in (
        ('parameters', 'diagnostics'), ('derived', 'derived_diagnostics'), ('floor', 'floor_diagnostics'))}
    if not all(d['acceptable'] and d['maxdepth_reached'] == 0 for d in families.values()):
        raise ValueError('Completed fit must pass all diagnostic families')
    rates = {name: {kind: [d['min_ess_'+kind]/bounds['retained_wall_seconds_upper'],
                          d['min_ess_'+kind]/bounds['retained_wall_seconds_lower']]
                    for kind in ('bulk', 'tail')} for name, d in families.items()}
    result = {'version': 'cpu-callback-wall-efficiency-v1', 'timing': bounds,
              'minimum_ess_per_second_intervals': rates,
              'acceptable': True, 'backend_ranking_established': False,
              'diagnostics': families,
              'policy': 'Same complete four-chain, 6000-draw pooled ESS as the selected fit. Rate bounds invert the wall-duration bounds. No short-run startup subtraction or division by summed chain times.'}
    files = {'summary.json': canonical(result)+'\n',
             'sampling-progress.jsonl': ''.join(canonical(r)+'\n' for r in events),
             Path(__file__).name: Path(__file__).read_text(),
             'sampler_efficiency.py': Path(metrics.__file__).read_text()}
    for name in ('parameter', 'derived'):
        table = pd.read_csv(io.BytesIO(fit[name+'-diagnostics.csv']), index_col=0)
        files[name+'-efficiency.csv'] = metrics.efficiency(table, denominators).to_csv(index_label='parameter')
    publish_bundle(output, files, {'version': result['version'],
        'fit_manifest_sha256': digest(experiment/'fit/complete.json'),
        'protocol_manifest_sha256': digest(experiment/'protocol/complete.json'),
        'recovery_manifest_sha256': digest(recovery/'complete.json'),
        'progress_manifest_sha256': digest(progress/'complete.json')})
    print(canonical({'output': str(output), 'timing': bounds, 'rates': rates}), flush=True)


if __name__ == '__main__':
    main()
