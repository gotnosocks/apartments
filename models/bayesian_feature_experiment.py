"""Reproducible, current-cohort Bayesian feature and bathroom research runner."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

from . import bayesian_feature_model as feature
from . import bayesian_rent_model as base
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
import numpy as np
import pandas as pd
import pymc as pm
import arviz as az

VERSION = 'bayesian-bathroom-experiment-v1'


def load_data(dataset):
    manifest, files = _verified_bundle(dataset, retain={'observations.jsonl'})
    if manifest.get('version') != 'reported-bathroom-counts-projection-v1':
        raise ValueError('Source-verified bathroom projection required')
    data = pd.DataFrame([json.loads(s) for s in files['observations.jsonl'].decode().split('\n') if s.strip()])
    data.period = pd.to_datetime(data.period)
    data.square_feet = pd.to_numeric(data.square_feet, errors='coerce')
    if (data.audit_id.duplicated().any() or data.duplicated(['unit_id', 'period']).any()
            or not np.isfinite(data.asking_rent).all() or not data.asking_rent.gt(0).all()):
        raise ValueError('Invalid source cohort')
    return data, manifest


def interval(values):
    values = np.asarray(values)
    return {'median': float(np.median(values)), 'lower_95': float(np.quantile(values, .025)),
            'upper_95': float(np.quantile(values, .975)), 'probability_positive': float(np.mean(values > 0))}


def bathroom_contrasts(design, data, beta):
    full, half, known = feature.bathroom_values(data)
    result = []
    def state(beds, baths, halves):
        row = data.iloc[[0]].copy()
        row['bedrooms'] = beds; row['reported_full_bathrooms'] = baths
        row['reported_half_bathrooms'] = halves; row['bathrooms'] = baths+.5*halves
        row['bathroom_count_evidence'] = [{'flags': []}]
        mask = known & data.bedrooms.eq(beds).to_numpy() & (full == baths) & (half == halves)
        return row, {'rows': int(mask.sum()), 'units': int(data.loc[mask, 'unit_id'].nunique()),
                     'buildings': int(data.loc[mask, 'building'].nunique())}
    def contrast(beds, before, after):
        a, sa = state(beds, *before); b, sb = state(beds, *after)
        delta = (design.matrix(b)-design.matrix(a))[0]
        draws = beta @ delta
        result.append({'bedrooms': beds, 'before_full_half': before, 'after_full_half': after,
            'log_effect': interval(draws), 'percent_effect': interval(100*np.expm1(draws)),
            'support_before': sa, 'support_after': sb,
            'supported_endpoints': bool(sa['rows'] and sb['rows']),
            'held_fixed': 'building, unit, date, square footage and other observed features; descriptive association'})
        return draws
    balance = []
    for beds in range(1, 5):
        for baths in range(1, 5):
            contrast(beds, (baths, 0), (baths+1, 0))
        contrast(beds, (max(1, beds), 0), (max(1, beds), 1))
        if beds >= 2:
            first = contrast(beds, (beds-1, 0), (beds, 0))
            second = contrast(beds, (beds, 0), (beds+1, 0))
            balance.append({'bedrooms': beds, 'definition': 'log increment net -1 to 0 minus net 0 to +1 (full baths minus bedrooms)',
                'difference': interval(first-second),
                'probability_first_increment_larger': float(np.mean(first > second)),
                'support': [state(beds, baths, 0)[1] for baths in (beds-1, beds, beds+1)]})
    return {'increments': result, 'balance': balance,
            'interpretation': 'Conditional posterior associations, not effects of a renovation. Unknown and flagged bathroom composition excluded from bathroom-value coding, not from the cohort.'}


def fitted_summary(inference, design, data):
    p = base.posterior_dataset(inference)
    samples = {name: base.sample_values(p, name) for name in
               ('alpha', 'beta', 'trend_coefficients', 'annual_drift', 'season_coefficients',
                'building_effect', 'sigma_unit', 'unit_z')}
    d = design.time; a = d.arrays(data); x = design.matrix(data)
    # Block observations to keep posterior reconstruction within memory bounds.
    rows = []
    for start in range(0, len(data), 128):
        stop = min(start+128, len(data)); sl = slice(start, stop)
        mu = (samples['alpha'][:, None] + samples['beta'] @ x[sl].T
              + samples['trend_coefficients'] @ (d.time_matrix-d.time_center)[a['period'][sl]].T
              + samples['annual_drift'][:, None]*(d.linear_time-d.linear_center)[a['period'][sl]]
              + samples['season_coefficients'] @ (d.season_matrix-d.season_weights@d.season_matrix)[a['season'][sl]].T
              + samples['building_effect'][:, a['building'][sl]]
              + samples['sigma_unit'][:, None]*samples['unit_z'][:, a['unit'][sl]])
        quantiles = np.exp(np.quantile(mu, [.025, .5, .975], axis=0))
        for j, row in enumerate(data.iloc[sl].itertuples()):
            estimate = float(quantiles[1, j])
            rows.append({'audit_id': row.audit_id, 'source_listing_id': str(row.source_listing_id),
                'unit_id': row.unit_id, 'building': row.building, 'period': row.period.strftime('%Y-%m-%d'),
                'asking_rent': float(row.asking_rent), 'fitted_rent': estimate,
                'latent_rent_lower_95': float(quantiles[0, j]), 'latent_rent_upper_95': float(quantiles[2, j]),
                'residual_dollars': float(row.asking_rent-estimate),
                'residual_log': float(np.log(row.asking_rent/estimate))})
    return rows, samples


def publish_fit(directory, protocol_hash):
    """Publish binary and text outputs only after all checks and writes finish."""
    files = {p.name: digest(p) for p in directory.iterdir() if p.is_file() and p.name != 'complete.json'}
    manifest = {'version': VERSION, 'protocol_sha256': protocol_hash, 'files': files}
    temporary = directory/'complete.json.tmp'
    temporary.write_text(canonical(manifest)+'\n')
    temporary.replace(directory/'complete.json')
    _verified_bundle(directory)


def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data, source = load_data(args.dataset)
        paths = [Path(m.__file__) for m in (feature, base, feature.amenity, feature.amenity.baseline,
                 feature.pricing)] + [Path(__file__)]
        code = {p.name: digest(p) for p in paths}
        protocol = {'version': VERSION, 'source_manifest_sha256': digest(Path(args.dataset)/'complete.json'),
            'source_observations_sha256': source['files']['observations.jsonl'],
            'source_directory': str(Path(args.dataset).resolve()), 'rows': len(data),
            'units': int(data.unit_id.nunique()), 'buildings': int(data.building.nunique()),
            'current_rows': int(data.analysis_price_basis.eq('current_capture_gross_ask').sum()),
            'specification': args.spec, 'draws': args.draws, 'tune': args.tune, 'chains': args.chains,
            'seed': args.seed, 'target_accept': args.target_accept, 'adaptation': args.adaptation,
            'prior_multiplier': args.prior_multiplier, 'implementation_sha256': code,
            'versions': {p: importlib.metadata.version(p) for p in ('pymc', 'nutpie', 'arviz', 'numpy', 'pandas', 'scipy')},
            'purpose': 'Current-cohort descriptive coefficients and residuals; all captured current observations included. No unseen-building objective.',
            'likelihood': 'Student-t(log advertised gross rent), fixed nu=5; inferred residual, unit, building, trend and season scales',
            'bathroom_policy': 'Use explicit full/half source counts only if complete, integer, at least one full bath, and no source-review flags; retain all other rows with an unknown indicator.',
            'uncertainty': 'Posterior conditional on source measurements, cohort, likelihood and priors; not causal or protection against source errors.'}
        ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol', {'protocol.json': canonical(protocol)+'\n',
            **{p.name: p.read_text() for p in paths}}, {'version': VERSION, 'protocol_sha256': ph})
        target = root/'fit'
        if (target/'complete.json').exists():
            manifest, files = _verified_bundle(target, retain={'summary.json'})
            if manifest.get('protocol_sha256') != ph:
                raise ValueError('Protocol mismatch')
            return json.loads(files['summary.json'])
        target.mkdir(exist_ok=True)
        base.emit('design', rows=len(data), specification=args.spec)
        design = feature.FeatureDesign(data, args.spec)
        design.save(target)
        base.emit('design_ready', **design.support)
        checkpoint = target/'posterior-checkpoint.json'
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_text())
            if saved != {'protocol_sha256': ph, 'posterior_sha256': digest(target/'posterior.nc')}:
                raise ValueError('Invalid posterior checkpoint')
            inference = az.from_netcdf(target/'posterior.nc')
        else:
            model = feature.build_model(data, design, args.prior_multiplier)
            base.emit('sampling', chains=args.chains, tune=args.tune, draws=args.draws)
            started = time.time()
            with model:
                prior = pm.sample_prior_predictive(draws=80, random_seed=args.seed+1,
                    var_names=['alpha', 'beta', 'sigma', 'sigma_building', 'sigma_unit', 'annual_drift'])
                prior.to_netcdf(target/'prior.nc', engine='h5netcdf')
                inference = pm.sample(draws=args.draws, tune=args.tune, chains=args.chains,
                    cores=min(args.chains, 4), random_seed=args.seed, nuts_sampler='nutpie',
                    backend='numba', nuts={'adaptation': args.adaptation},
                    target_accept=args.target_accept, progressbar=False,
                    idata_kwargs={'log_likelihood': False}, compute_convergence_checks=False)
            inference.to_netcdf(target/'posterior.nc', engine='h5netcdf')
            checkpoint.write_text(canonical({'protocol_sha256': ph, 'posterior_sha256': digest(target/'posterior.nc')})+'\n')
            base.emit('sampling_complete', seconds=time.time()-started)
        diag, table = base.diagnostics(inference)
        diag['acceptable'] = bool(diag['acceptable'] and diag['maxdepth_reached'] == 0)
        table.to_csv(target/'parameter-diagnostics.csv', index_label='parameter')
        (target/'diagnostics.json').write_text(canonical(diag)+'\n')
        base.emit('diagnostics', **{k: v for k, v in diag.items() if k != 'worst_rhat'})
        residuals, samples = fitted_summary(inference, design, data)
        contrasts = bathroom_contrasts(design, data, samples['beta'])
        (target/'bathroom-contrasts.json').write_text(canonical(contrasts)+'\n')
        (target/'residuals.jsonl').write_text(''.join(canonical(r)+'\n' for r in residuals))
        coefficients = [{'feature': name, **interval(samples['beta'][:, i])} for i, name in enumerate(design.features)]
        (target/'coefficients.json').write_text(canonical(coefficients)+'\n')
        group_rows = []
        for kind, ids, draws in [('building', design.time.buildings, samples['building_effect']),
                                 ('unit', design.time.unit_ids, samples['sigma_unit'][:, None]*samples['unit_z'])]:
            for i, identity in enumerate(ids):
                group_rows.append({'kind': kind, 'id': identity, 'log_effect': interval(draws[:, i]),
                    'percent_effect': interval(100*np.expm1(draws[:, i]))})
        (target/'group-effects.jsonl').write_text(''.join(canonical(r)+'\n' for r in group_rows))
        summary = {'protocol_sha256': ph, 'design_support': design.support, 'diagnostics': diag,
            'status': 'exploratory_converged' if diag['acceptable'] else 'diagnostic_only_do_not_interpret_intervals',
            'median_absolute_log_residual': float(np.median([abs(r['residual_log']) for r in residuals])),
            'latent_intervals': 'Uncertainty about the conditional median asking rent for these observed units, not posterior predictive intervals or causal values.',
            'bathroom_balance': contrasts['balance'], 'main_model_changed': False}
        (target/'summary.json').write_text(canonical(summary)+'\n')
        if any(digest(p) != code[p.name] for p in paths):
            raise ValueError('Implementation changed during experiment')
        publish_fit(target, ph)
        base.emit('complete', status=summary['status'], output=str(target))
        return summary


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
    args = parser.parse_args()
    if min(args.draws, args.tune) < 1 or args.chains < 2 or args.prior_multiplier <= 0:
        parser.error('Positive draws/tune/prior scale and at least two chains required')
    run(args)
