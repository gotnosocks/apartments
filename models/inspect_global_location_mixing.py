"""Diagnose global intercept/building-offset mixing on a complete draw checkpoint.

This may inspect a diagnostic-only fit; it never certifies the fit or relaxes its
convergence gate. Every retained draw is used for numerical diagnostics.
"""
import argparse
from collections import Counter
import io
import json
from pathlib import Path

import arviz as az
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run(experiment, output):
    root = Path(experiment)
    pm, pf = _verified_bundle(root/'protocol', retain={'protocol.json'})
    protocol = json.loads(pf['protocol.json'])
    checkpoint = json.loads((root/'fit/posterior-checkpoint.json').read_text())
    posterior = root/'fit/posterior.nc'
    if (checkpoint.get('protocol_sha256') != pm['protocol_sha256']
            or checkpoint.get('posterior_sha256') != digest(posterior)):
        raise ValueError('Posterior checkpoint binding differs')
    source = Path(protocol['source_directory'])
    sm, sf = _verified_bundle(source, retain={'observations.jsonl'})
    if (digest(source/'complete.json') != protocol['source_manifest_sha256']
            or sm['files']['observations.jsonl'] != protocol['source_observations_sha256']):
        raise ValueError('Diagnostic source weights differ')
    building_counts, unit_counts = Counter(), Counter()
    for line in sf['observations.jsonl'].decode().split('\n'):
        if line:
            row = json.loads(line); building_counts[row['building']] += 1; unit_counts[row['unit_id']] += 1
    with xr.open_dataset(posterior, group='posterior', engine='h5netcdf') as p:
        if p.sizes['chain'] != protocol['chains'] or p.sizes['draw'] != protocol['draws']:
            raise ValueError('Checkpoint draw dimensions differ')
        alpha = p.alpha.transpose('chain', 'draw').values
        buildings = p.building_effect.transpose('chain', 'draw', 'building').values
        labels = p.building.values.tolist()
        units = p.unit.values.tolist()
        if sum(unit_counts.values()) != protocol['rows'] or set(units) != unit_counts.keys():
            raise ValueError('Unit weights or identities differ')
        mean_unit_z, weighted_unit_z = np.zeros_like(alpha), np.zeros_like(alpha)
        for start in range(0, len(units), 512):
            block = p.unit_z.isel(unit=slice(start, start+512)).transpose('chain', 'draw', 'unit').values
            weights = np.array([unit_counts[u]/protocol['rows'] for u in units[start:start+512]])
            mean_unit_z += block.sum(axis=-1)/len(units)
            weighted_unit_z += np.einsum('cdu,u->cd', block, weights)
        sigma_unit = p.sigma_unit.transpose('chain', 'draw').values
    mean = buildings.mean(axis=-1)
    weighted_building = np.einsum('cdb,b->cd', buildings, [building_counts[b]/protocol['rows'] for b in labels])
    weighted_groups = weighted_building+sigma_unit*weighted_unit_z
    values = {'alpha': alpha, 'observation_weighted_group_offset': weighted_groups,
              'alpha_plus_weighted_groups': alpha+weighted_groups,
              'observation_weighted_building_offset': weighted_building,
              'mean_unit_effect': sigma_unit*mean_unit_z,
              'observation_weighted_unit_effect': sigma_unit*weighted_unit_z}
    for label in ('the-thomas-eddy', '101-west-23-street-new_york'):
        values['alpha_plus_'+label] = alpha+buildings[:, :, labels.index(label)]
    if any(not np.isfinite(v).all() for v in values.values()): raise ValueError('Nonfinite location draws')
    ds = xr.Dataset({k: (('chain', 'draw'), v) for k, v in values.items()})
    diagnostics = az.summary(ds, kind='diagnostics', round_to='none')
    result = {'version': 'global-location-mixing-diagnostic-v2', 'chains': protocol['chains'],
        'draws_per_chain': protocol['draws'], 'posterior_sha256': checkpoint['posterior_sha256'],
        'protocol_sha256': checkpoint['protocol_sha256'],
        'diagnostics': json.loads(diagnostics.to_json(orient='index')),
        'maximum_absolute_unweighted_building_mean': float(np.abs(mean).max()),
        'within_chain_alpha_correlations': {key: [float(np.corrcoef(a, b)[0, 1]) for a, b in zip(alpha, value)]
                                            for key, value in values.items() if key != 'alpha'},
        'chain_means': {k: v.mean(axis=1).tolist() for k, v in values.items()},
        'chain_standard_deviations': {k: v.std(axis=1, ddof=1).tolist() for k, v in values.items()},
        'interpretation': 'Building effects already obey an unweighted zero-sum constraint; their arithmetic mean is roundoff, not a drifting parameter. Examine observation-weighted building/unit offsets and their sum with alpha instead. Better mixing of any sum does not waive the failed alpha gate. All numerical diagnostics retain every draw; no price-effect interpretation is made.',
        'fit_accepted': False, 'main_selection_changed': False}
    with plt.rc_context({'svg.hashsalt': 'apartments-global-location-diagnostic', 'font.size': 10}):
        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True, layout='constrained')
        width = 100
        if protocol['draws'] % width: raise ValueError('Plot requires complete 100-draw blocks')
        x = np.arange(protocol['draws']//width)*width+width/2
        for ax, (key, data) in zip(axes, list(values.items())[:3]):
            for chain, trace in enumerate(data):
                ax.plot(x, trace.reshape(-1, width).mean(axis=1)-data.mean(), label=f'Chain {chain+1}', linewidth=1)
            ax.axhline(0, color='black', linewidth=.5)
            ax.set_ylabel('Log-price deviation')
            ax.set_title(key.replace('_', ' '))
        axes[0].legend(ncol=4, frameon=False)
        axes[-1].set_xlabel('Retained draw index (100-draw block means; numerical diagnostics use every draw)')
        fig.suptitle('Global location mixing — diagnostic only')
        image = io.StringIO(); fig.savefig(image, format='svg', metadata={'Date': None}); plt.close(fig)
    if digest(posterior) != checkpoint['posterior_sha256']: raise ValueError('Checkpoint changed during inspection')
    publish_bundle(output, {'diagnostic.json': canonical(result)+'\n', 'diagnostics.csv': diagnostics.to_csv(),
        'location-traces.svg': image.getvalue(), Path(__file__).name: Path(__file__).read_text()},
        {'version': result['version'], 'protocol_manifest_sha256': digest(root/'protocol/complete.json'),
         'posterior_checkpoint_sha256': digest(root/'fit/posterior-checkpoint.json')})
    print(canonical(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('experiment', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
