"""Observable, equivalent-graph Bayesian fits of original or reviewed bathroom data."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path

from . import bayesian_feature_model as feature
from . import bayesian_feature_graph as graph
from . import bayesian_sampling as sampler
from . import bayesian_feature_experiment as reports
from . import bayesian_rent_model as base
from apartments import corrections, research_pipeline
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
import numpy as np
import pandas as pd
import pymc as pm
import arviz as az
import xarray as xr

VERSION = 'observable-bayesian-bathroom-experiment-v2'
DATASET_VERSIONS = {'reported-bathroom-counts-projection-v1', 'reviewed-bathroom-counts-projection-v1'}


def load_data(dataset):
    manifest, files = _verified_bundle(dataset, retain={'observations.jsonl'})
    if manifest.get('version') not in DATASET_VERSIONS:
        raise ValueError('Verified original or reviewed bathroom projection required')
    data = pd.DataFrame([json.loads(s) for s in files['observations.jsonl'].decode().split('\n') if s.strip()])
    data.period = pd.to_datetime(data.period)
    data.square_feet = pd.to_numeric(data.square_feet, errors='coerce')
    if (data.audit_id.duplicated().any() or data.duplicated(['unit_id', 'period']).any()
            or not np.isfinite(data.asking_rent).all() or not data.asking_rent.gt(0).all()):
        raise ValueError('Invalid source cohort')
    return data, manifest


def contrast_directions(design, data):
    """Supported physical-state contrasts, including covariance-sensitive balance."""
    full, half, known = feature.bathroom_values(data)
    directions = {}
    def state(beds, baths, halves):
        mask = known & data.bedrooms.eq(beds).to_numpy() & (full == baths) & (half == halves)
        if not mask.any():
            return None
        row = data.iloc[[0]].copy()
        row['bedrooms'] = beds; row['reported_full_bathrooms'] = baths
        row['reported_half_bathrooms'] = halves; row['bathrooms'] = baths+.5*halves
        row['bathroom_count_evidence'] = [{'flags': []}]
        return design.matrix(row)[0]
    def add(name, before, after):
        if before is not None and after is not None:
            delta = after-before
            if np.max(np.abs(delta)) > 1e-12:
                directions[name] = delta
    for beds in range(1, 5):
        for baths in range(1, 5):
            add(f'bed{beds}:full{baths}_to_{baths+1}', state(beds, baths, 0), state(beds, baths+1, 0))
            for halves in range(2):
                add(f'bed{beds}:full{baths}:half{halves}_to_{halves+1}', state(beds, baths, halves), state(beds, baths, halves+1))
        if beds >= 2:
            states = [state(beds, baths, 0) for baths in (beds-1, beds, beds+1)]
            if all(s is not None for s in states):
                delta = 2*states[1]-states[0]-states[2]
                if np.max(np.abs(delta)) > 1e-12:
                    directions[f'bed{beds}:net_minus1_to0_minus_0to1'] = delta
    return directions


def half_bath_contrasts(design, data, beta):
    full, half, known = feature.bathroom_values(data)
    result = []
    for beds in range(1, 5):
        for baths in range(1, 5):
            for before in range(2):
                supports = []; states = []
                for halves in (before, before+1):
                    mask = known & data.bedrooms.eq(beds).to_numpy() & (full == baths) & (half == halves)
                    supports.append({'rows': int(mask.sum()), 'units': int(data.loc[mask, 'unit_id'].nunique()),
                                     'buildings': int(data.loc[mask, 'building'].nunique())})
                    row = data.iloc[[0]].copy()
                    row['bedrooms'] = beds; row['reported_full_bathrooms'] = baths
                    row['reported_half_bathrooms'] = halves; row['bathrooms'] = baths+.5*halves
                    row['bathroom_count_evidence'] = [{'flags': []}]
                    states.append(design.matrix(row)[0])
                delta = states[1]-states[0]
                identified = bool(np.max(np.abs(delta)) > 1e-12)
                draws = beta @ delta
                result.append({'bedrooms': beds, 'full_bathrooms': baths, 'before_half': before,
                    'after_half': before+1, 'support_before': supports[0], 'support_after': supports[1],
                    'supported_endpoints': bool(supports[0]['rows'] and supports[1]['rows']),
                    'encoded_contrast': identified,
                    'log_effect': reports.interval(draws) if identified else None,
                    'percent_effect': reports.interval(100*np.expm1(draws)) if identified else None})
    return result


def derived_diagnostics(inference, design, data):
    posterior = base.posterior_dataset(inference)
    variables = {'unit_effect': posterior['sigma_unit']*posterior['unit_z']}
    directions = contrast_directions(design, data)
    if directions:
        delta = xr.DataArray(np.array(list(directions.values())), dims=('contrast', 'feature'),
            coords={'contrast': list(directions), 'feature': design.features})
        variables['bathroom_contrast'] = xr.dot(posterior.beta, delta, dim='feature')
    return base.diagnostics({'posterior': xr.Dataset(variables), 'sample_stats': inference['sample_stats']})


def write_reports(target, inference, design, data, protocol_hash):
    diag, table = base.diagnostics(inference)
    diag['acceptable'] = bool(diag['acceptable'] and diag['maxdepth_reached'] == 0)
    table.to_csv(target/'parameter-diagnostics.csv', index_label='parameter')
    (target/'diagnostics.json').write_text(canonical(diag)+'\n')
    base.emit('diagnostics', **{k: v for k, v in diag.items() if k != 'worst_rhat'})
    derived, derived_table = derived_diagnostics(inference, design, data)
    derived_table.to_csv(target/'derived-diagnostics.csv', index_label='parameter')
    (target/'derived-diagnostics.json').write_text(canonical(derived)+'\n')
    acceptable = diag['acceptable'] and derived['acceptable']
    residuals, samples = reports.fitted_summary(inference, design, data)
    contrasts = reports.bathroom_contrasts(design, data, samples['beta'])
    contrasts['half_bath_increments'] = half_bath_contrasts(design, data, samples['beta'])
    (target/'bathroom-contrasts.json').write_text(canonical(contrasts)+'\n')
    (target/'residuals.jsonl').write_text(''.join(canonical(r)+'\n' for r in residuals))
    coefficients = [{'feature': name, **reports.interval(samples['beta'][:, i])} for i, name in enumerate(design.features)]
    (target/'coefficients.json').write_text(canonical(coefficients)+'\n')
    with (target/'group-effects.jsonl').open('w') as stream:
        for kind, ids, draws in [('building', design.time.buildings, samples['building_effect']),
                                ('unit', design.time.unit_ids, samples['sigma_unit'][:, None]*samples['unit_z'])]:
            for i, identity in enumerate(ids):
                stream.write(canonical({'kind': kind, 'id': identity, 'log_effect': reports.interval(draws[:, i]),
                    'percent_effect': reports.interval(100*np.expm1(draws[:, i]))})+'\n')
    summary = {'protocol_sha256': protocol_hash, 'design_support': design.support, 'diagnostics': diag,
        'derived_diagnostics': derived,
        'status': 'exploratory_converged' if acceptable else 'diagnostic_only_do_not_interpret_intervals',
        'median_absolute_log_residual': float(np.median([abs(r['residual_log']) for r in residuals])),
        'latent_intervals': 'Uncertainty in the conditional median asking rent of observed units; not predictive intervals or causal values.',
        'bathroom_balance': contrasts['balance'], 'main_model_changed': False}
    (target/'summary.json').write_text(canonical(summary)+'\n')
    return summary


def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data, source = load_data(args.dataset)
        paths = [Path(m.__file__) for m in (feature, graph, sampler, reports, base,
            feature.amenity, feature.amenity.baseline, feature.pricing, corrections, research_pipeline)] + [Path(__file__)]
        code = {p.name: digest(p) for p in paths}
        verification = None
        if getattr(args, 'graph_validation', None):
            vm, vf = _verified_bundle(args.graph_validation, retain={'parity.json'})
            parity = json.loads(vf['parity.json'])
            validated = {Path(name).name: value for name, value in parity['hashes'].items()}
            if (parity.get('passed') is not True or validated.get(Path(graph.__file__).name) != code[Path(graph.__file__).name]
                    or any(code[name] != value for name, value in validated.items() if name in code)):
                raise ValueError('Graph parity evidence does not match current implementation')
            verification = {'manifest_sha256': digest(Path(args.graph_validation)/'complete.json'),
                'version': vm['version'], 'rows': parity['rows'],
                'source_observations_sha256': parity['source_observations_sha256']}
        protocol = {'version': VERSION, 'source_manifest_sha256': digest(Path(args.dataset)/'complete.json'),
            'source_observations_sha256': source['files']['observations.jsonl'],
            'source_version': source['version'], 'source_directory': str(Path(args.dataset).resolve()),
            'rows': len(data), 'units': int(data.unit_id.nunique()), 'buildings': int(data.building.nunique()),
            'current_rows': int(data.analysis_price_basis.eq('current_capture_gross_ask').sum()),
            'specification': args.spec, 'draws': args.draws, 'tune': args.tune, 'chains': args.chains,
            'seed': args.seed, 'target_accept': args.target_accept, 'adaptation': args.adaptation,
            'prior_multiplier': args.prior_multiplier, 'implementation_sha256': code,
            'graph_verification': verification,
            'versions': {p: importlib.metadata.version(p) for p in ('pymc', 'nutpie', 'pytensor', 'numba', 'arviz', 'numpy', 'pandas', 'scipy', 'h5netcdf')},
            'purpose': 'Current-cohort descriptive coefficients and residuals, including all accepted current captures.',
            'likelihood': 'Student-t(log gross asking rent), fixed nu=5; all priors identical to bayesian-feature-bathroom-v1',
            'graph': 'Exact sharing of repeated covariate rows and calendar-level products; every observation remains distinct.',
            'bathroom_policy': 'Explicit complete integer counts, at least one full bath, agreeing scalar, no unresolved review flags; preserve unknown rows with a reporting indicator.',
            'uncertainty': 'Conditional on source measurements, cohort, likelihood and priors; not causal or protection against omitted features.'}
        ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol', {'protocol.json': canonical(protocol)+'\n',
            **{p.name: p.read_text() for p in paths}}, {'version': VERSION, 'protocol_sha256': ph})
        target = root/'fit'
        if (target/'complete.json').exists():
            manifest, files = _verified_bundle(target, retain={'summary.json'})
            if manifest.get('protocol_sha256') != ph:
                raise ValueError('Fit protocol mismatch')
            return json.loads(files['summary.json'])
        target.mkdir(exist_ok=True)
        sampler.write_status(root/'progress.json', 'design', rows=len(data), specification=args.spec)
        design = feature.FeatureDesign(data, args.spec)
        design.save(target)
        base.emit('design_ready', **design.support)
        checkpoint = target/'posterior-checkpoint.json'
        if checkpoint.exists():
            if json.loads(checkpoint.read_text()) != {'protocol_sha256': ph, 'posterior_sha256': digest(target/'posterior.nc')}:
                raise ValueError('Invalid posterior checkpoint')
            inference = az.from_netcdf(target/'posterior.nc')
        else:
            model = graph.build_model(data, design, args.prior_multiplier)
            (target/'compression.json').write_text(canonical(model.compression_summary)+'\n')
            with model:
                prior = pm.sample_prior_predictive(draws=80, random_seed=args.seed+1,
                    var_names=['alpha', 'beta', 'sigma', 'sigma_building', 'sigma_unit', 'annual_drift'])
            prior.to_netcdf(target/'prior.nc', engine='h5netcdf')
            inference = sampler.sample(model, draws=args.draws, tune=args.tune, chains=args.chains,
                seed=args.seed, adaptation=args.adaptation, target_accept=args.target_accept,
                status_path=root/'progress.json')
            inference.to_netcdf(target/'posterior.nc', engine='h5netcdf')
            checkpoint.write_text(canonical({'protocol_sha256': ph, 'posterior_sha256': digest(target/'posterior.nc')})+'\n')
        # A resumed file must satisfy the same completeness contract as a fresh sample.
        if (inference['posterior'].sizes.get('chain') != args.chains
                or inference['posterior'].sizes.get('draw') != args.draws):
            raise ValueError('Incomplete posterior checkpoint')
        sampler.write_status(root/'progress.json', 'diagnostics_and_reports')
        result = write_reports(target, inference, design, data, ph)
        if any(digest(p) != code[p.name] for p in paths):
            raise ValueError('Implementation changed during experiment')
        sampler.publish_fit(target, version=VERSION, protocol_hash=ph)
        sampler.write_status(root/'progress.json', 'complete', status=result['status'])
        base.emit('complete', status=result['status'], output=str(target))
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--spec', choices=feature.SPECS, default='full_half_balance')
    parser.add_argument('--draws', type=int, default=1000)
    parser.add_argument('--tune', type=int, default=1000)
    parser.add_argument('--chains', type=int, default=4)
    parser.add_argument('--seed', type=int, default=20260918)
    parser.add_argument('--target-accept', type=float, default=.93)
    parser.add_argument('--adaptation', choices=('diag', 'low_rank'), default='diag')
    parser.add_argument('--prior-multiplier', type=float, default=1.)
    parser.add_argument('--graph-validation', type=Path)
    args = parser.parse_args()
    if (min(args.draws, args.tune) < 1 or args.chains < 2 or args.prior_multiplier <= 0
            or not 0 < args.target_accept < 1):
        parser.error('Positive draws/tune/prior scale, at least two chains, and target acceptance in (0,1) required')
    run(args)
