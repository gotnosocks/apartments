"""Bounded, conditional in-sample posterior predictive checks for accepted fits."""
from __future__ import annotations

import argparse
import json
import importlib.metadata
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_report as report
from . import bayesian_feature_design_v2 as ordered_design

VERSION = 'bayesian-feature-posterior-checks-v2'
VARIABLE_DIMS = {
    'alpha': (), 'beta': ('feature',), 'trend_coefficients': ('trend_basis',),
    'annual_drift': (), 'season_coefficients': ('season_basis',),
    'building_effect': ('building',), 'sigma_unit': (), 'unit_z': ('unit',), 'sigma': (),
}
THRESHOLDS = {'10pct': float(np.log(1.1)), '25pct': float(np.log(1.25))}
MIN_SUPPORT = {'rows': 10, 'units': 5, 'buildings': 2}
LIMITATIONS = [
    'Conditional in-sample posterior predictive checks: the same observations informed the posterior. These are likelihood and residual diagnostics, not held-out prediction or causal estimates.',
    'Building and unit effects remain fixed at each joint posterior draw; only Student-t observation noise is replicated (nu=5). Checks do not test the distribution of newly sampled buildings or units.',
    'Discrepancy tail probabilities are descriptive posterior predictive comparisons, not calibrated frequentist p-values. Slices overlap; no automatic feature addition, data correction or model promotion follows.',
    'Current and historical asks have different sampling rules. Small supported slices have limited power; unsupported slices are listed explicitly.',
    'At most 200 joint draws are used, balanced across chains. Tail-probability resolution and Monte Carlo variation are limited by this subset; intervals summarize discrepancies, not apartment-price uncertainty.',
    'Positive residual means asking rent exceeds the conditional log-rent location. Negative thresholds use reciprocal rent ratios: below 1/1.1 or 1/1.25, rather than minus 10% or 25%.',
]


def select_draws(chains, draws, per_chain=50):
    if (any(not isinstance(v, int) or isinstance(v, bool) for v in (chains, draws, per_chain))
            or chains < 2 or draws < 1 or per_chain < 1 or chains*per_chain > 200):
        raise ValueError('Require at least two chains and 1–200 total requested draws')
    count = min(draws, per_chain)
    # Midpoints of equal draw-index bins cover each chain without selecting warmup.
    indices = ((np.arange(count)+.5)*draws/count).astype(int)
    return [(chain, int(draw)) for chain in range(chains) for draw in indices]


def verify_implementation(protocol):
    root = Path(__file__).resolve().parents[1]
    hashes = protocol['implementation_sha256']
    required = {'bayesian_feature_model.py', 'bayesian_rent_model.py', 'bayesian_feature_experiment.py',
                'amenity_rent_model.py', 'minimal_rent_model.py', 'pricing.py', 'corrections.py', 'research_pipeline.py'}
    # Use the exact protocol inventory, including transitive design dependencies.
    if not required <= hashes.keys():
        raise ValueError('Missing frozen reconstruction dependencies')
    paths = []
    for name, expected in hashes.items():
        if Path(name).name != name:
            raise ValueError('Invalid frozen implementation filename')
        candidates = [p for p in (root/'models'/name, root/'src'/'apartments'/name) if p.is_file()]
        if len(candidates) != 1 or digest(candidates[0]) != expected:
            raise ValueError('Current reconstruction implementation differs from frozen protocol: '+name)
        paths.append(candidates[0])
    return paths


def load_draws(path, protocol, design, per_chain=50):
    with xr.open_dataset(path, group='posterior', engine='h5netcdf') as posterior:
        if (posterior.sizes.get('chain') != protocol['chains']
                or posterior.sizes.get('draw') != protocol['draws']):
            raise ValueError('Posterior chain/draw dimensions differ from protocol')
        expected = {'feature': design.features, 'building': design.time.buildings,
                    'unit': design.time.unit_ids, 'trend_basis': list(range(design.time.time_matrix.shape[1])),
                    'season_basis': list(range(design.time.season_matrix.shape[1]))}
        for dimension, values in expected.items():
            if dimension not in posterior.coords or posterior[dimension].values.tolist() != list(values):
                raise ValueError('Posterior coordinate order differs from saved design: '+dimension)
        for name, dimensions in VARIABLE_DIMS.items():
            if name not in posterior or set(posterior[name].dims) != {'chain', 'draw', *dimensions}:
                raise ValueError('Unexpected posterior dimensions: '+name)
        chosen = select_draws(protocol['chains'], protocol['draws'], per_chain)
        samples = {name: [] for name in VARIABLE_DIMS}
        selection = []
        for chain in range(protocol['chains']):
            positions = [draw for selected_chain, draw in chosen if selected_chain == chain]
            # Select before load; batch a bounded chain subset to avoid repeatedly
            # decompressing the same on-disk chunks for individual draw reads.
            part = posterior[list(VARIABLE_DIMS)].isel(chain=chain, draw=positions).load()
            for draw in positions:
                selection.append({'chain_index': chain, 'draw_index': draw,
                                  'chain_coordinate': posterior.chain.values[chain].item(),
                                  'draw_coordinate': posterior.draw.values[draw].item()})
            for name, dimensions in VARIABLE_DIMS.items():
                samples[name].extend(np.asarray(part[name].transpose('draw', *dimensions).values).copy())
    samples = {name: np.stack(values) for name, values in samples.items()}
    if (any(not np.isfinite(value).all() for value in samples.values())
            or np.any(samples['sigma'] <= 0) or np.any(samples['sigma_unit'] < 0)):
        raise ValueError('Nonfinite draws or invalid residual/unit scales')
    return samples, selection


def reconstruct_mu(samples, design, data):
    """Reconstruct selected joint draws, preserving every coefficient covariance."""
    d = design.time
    a = d.arrays(data)
    if np.any(a['unit'] < 0) or np.any(a['building'] < 0):
        raise ValueError('Observed group absent from fitted design')
    mu = (samples['alpha'][:, None] + samples['beta'] @ design.matrix(data).T
          + samples['trend_coefficients'] @ (d.time_matrix-d.time_center)[a['period']].T
          + samples['annual_drift'][:, None]*(d.linear_time-d.linear_center)[a['period']]
          + samples['season_coefficients'] @ (d.season_matrix-d.season_weights@d.season_matrix)[a['season']].T
          + samples['building_effect'][:, a['building']]
          + samples['sigma_unit'][:, None]*samples['unit_z'][:, a['unit']])
    if not np.isfinite(mu).all():
        raise ValueError('Nonfinite reconstructed location')
    return mu


def slices(data):
    current = data.analysis_price_basis.eq('current_capture_gross_ask').to_numpy()
    proposals = [('overall', np.ones(len(data), dtype=bool)), ('current', current), ('history', ~current)]
    for beds in sorted(data.bedrooms.unique()):
        mask = data.bedrooms.eq(beds).to_numpy()
        name = f'bedrooms={float(beds):g}'
        proposals.extend([(name, mask), (name+'/current', mask & current), (name+'/history', mask & ~current)])
    accepted, omitted = [], []
    for name, mask in proposals:
        subset = data.loc[mask]
        support = {'rows': len(subset), 'units': int(subset.unit_id.nunique()),
                   'buildings': int(subset.building.nunique())}
        item = {'slice': name, 'support': support}
        if all(support[k] >= value for k, value in MIN_SUPPORT.items()):
            accepted.append((item, mask))
        else:
            omitted.append(item)
    return accepted, omitted


def discrepancies(residuals):
    result = {'median_signed_log_residual': np.median(residuals, axis=1),
              'mean_absolute_log_residual': np.mean(np.abs(residuals), axis=1)}
    for name, threshold in THRESHOLDS.items():
        positive = np.mean(residuals > threshold, axis=1)
        negative = np.mean(residuals < -threshold, axis=1)
        result.update({f'positive_tail_{name}': positive, f'negative_tail_{name}': negative,
                       f'signed_tail_balance_{name}': positive-negative})
    return result


def interval(values):
    low, median, high = np.quantile(values, [.025, .5, .975])
    return {'median': float(median), 'lower_95': float(low), 'upper_95': float(high)}


def compare_residuals(observed, replicated):
    if observed.shape != replicated.shape or observed.ndim != 2 or not np.isfinite(observed).all() or not np.isfinite(replicated).all():
        raise ValueError('Finite paired draw-by-observation residual arrays required')
    obs, rep = discrepancies(observed), discrepancies(replicated)
    return {key: {'observed': interval(obs[key]), 'replicated': interval(rep[key]),
                  'observed_minus_replicated': interval(obs[key]-rep[key]),
                  'probability_replicated_greater_or_equal': float(np.mean(rep[key] >= obs[key])),
                  'observed_by_draw': obs[key].tolist(), 'replicated_by_draw': rep[key].tolist()}
            for key in obs}


def markdown(result):
    text = ['# Conditional in-sample posterior predictive checks', '', *[p+'\n' for p in LIMITATIONS],
            f"Selected {len(result['selected_draws'])} joint draws; seed {result['seed']}. Thresholds and minimum support are fixed in the saved protocol.", '',
            '| Slice | Rows / units / buildings | Discrepancy | Observed median | Replicated median | P(rep ≥ obs) |',
            '|---|---|---|---:|---:|---:|']
    for item in result['slices']:
        support = ' / '.join(str(item['support'][k]) for k in ('rows', 'units', 'buildings'))
        for key, value in item['discrepancies'].items():
            text.append(f"| {item['slice']} | {support} | {key} | {value['observed']['median']:.5f} | {value['replicated']['median']:.5f} | {value['probability_replicated_greater_or_equal']:.3f} |")
    text.extend(['', f"{len(result['omitted_slices'])} unsupported slices are enumerated in checks.json. Full 95% discrepancy intervals and paired draw statistics are retained there.", ''])
    return '\n'.join(text)


def run(experiment, dataset, output, *, per_chain=50, seed=20260919):
    experiment, dataset, output = map(Path, (experiment, dataset, output))
    verified, manifests = report.build_report(experiment, dataset, top=1)
    protocol = json.loads((experiment/'protocol'/'protocol.json').read_text())
    paths = verify_implementation(protocol)
    _, source = _verified_bundle(dataset, retain={'observations.jsonl'})
    data = pd.DataFrame(report.jsonl(source['observations.jsonl']))
    data['period'] = pd.to_datetime(data.period)
    data['square_feet'] = pd.to_numeric(data.square_feet, errors='coerce')
    design = ordered_design.load_design(experiment/'fit', data)
    samples, selected = load_draws(experiment/'fit'/'posterior.nc', protocol, design, per_chain)
    mu = reconstruct_mu(samples, design, data)
    observed = np.log(data.asking_rent.to_numpy(dtype=float))[None, :]-mu
    # One replication for each selected joint draw, in documented chain-major order.
    replicated = np.random.default_rng(seed).standard_t(5., size=mu.shape)*samples['sigma'][:, None]
    accepted, omitted = slices(data)
    result = {'version': VERSION, 'purpose': 'conditional_in_sample_posterior_predictive_checks',
              'protocol_sha256': verified['protocol_sha256'], 'seed': seed, 'rng': 'numpy.default_rng/PCG64',
              'design_loader': ordered_design.VERSION,
              'design_loader_sha256': digest(Path(ordered_design.__file__)),
              'requested_draws_per_chain': per_chain, 'selected_draws': selected,
              'selection': 'Equal draw-index-bin midpoints per chain; chain-major order; posterior group only.',
              'thresholds_log_ratio': THRESHOLDS, 'minimum_slice_support': MIN_SUPPORT,
              'cohort': verified['cohort'], 'source_observations_sha256': verified['source_observations_sha256'],
              'bindings': {kind: digest(path/'complete.json') for kind, path in
                           [('fit', experiment/'fit'), ('protocol', experiment/'protocol'), ('source', dataset)]},
              'posterior_sha256': manifests['fit_manifest']['files']['posterior.nc'],
              'reconstruction_implementation_sha256': protocol['implementation_sha256'],
              'versions': {name: importlib.metadata.version(name) for name in
                           ('numpy', 'pandas', 'xarray', 'h5netcdf', 'scipy')},
              'slices': [{**item, 'discrepancies': compare_residuals(observed[:, mask], replicated[:, mask])}
                         for item, mask in accepted], 'omitted_slices': omitted, 'limitations': LIMITATIONS,
              'main_model_changed': False}
    if any(digest(p) != protocol['implementation_sha256'][p.name] for p in paths):
        raise ValueError('Reconstruction implementation changed during checks')
    publish_bundle(output, {'checks.json': canonical(result)+'\n', 'checks.md': markdown(result),
                           Path(__file__).name: Path(__file__).read_text(),
                           Path(report.__file__).name: Path(report.__file__).read_text(),
                           Path(ordered_design.__file__).name: Path(ordered_design.__file__).read_text()},
                   {'version': VERSION, 'protocol_sha256': verified['protocol_sha256']})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--draws-per-chain', type=int, default=50)
    parser.add_argument('--seed', type=int, default=20260919)
    args = parser.parse_args()
    result = run(args.experiment, args.dataset, args.output, per_chain=args.draws_per_chain, seed=args.seed)
    print(canonical({'slices': len(result['slices']), 'draws': len(result['selected_draws']), 'output': str(args.output)}))
