"""Natural-spline floor model plus bedroom-group time-trend deviations.

Identical source loading, feature design, floor spline, disk sampling and
report stages to `bayesian_floor_spline_experiment`; the graph adds
`bayesian_bedroom_time_graph` deviations and every reconstructed location
(residuals, fitted rents) includes them. Research fit: publishing it never
changes the main selection.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from . import bayesian_floor_spline_experiment as previous
from . import bayesian_bedroom_time_graph as graph

VERSION = 'observable-bayesian-bedroom-time-experiment-v1'
BEDROOM_TIME_VERSION = 'bedroom-group-time-deviation-summary-v1'
floor, storage, disk_protocol, execution, report_cache = (previous.floor, previous.storage,
    previous.disk_protocol, previous.execution, previous.report_cache)
v2 = previous.v2
load_data = previous.load_data
residual_scale_summary = previous.residual_scale_summary
floor_contrasts = previous.floor_contrasts
REQUIRED_FIT = previous.REQUIRED_FIT | {'bedroom-time.json'}
VARIABLES = {'walk': ('bedroom_walk_scale', 'bedroom_walk_z', 'bedroom_time'),
             'linear': ('bedroom_slope_raw', 'bedroom_time')}


def validate_args(args):
    previous.validate_args(args)
    if args.residual_scale != 'shared':
        raise ValueError('Bedroom-time graph supports shared residual noise only')
    if args.bedroom_time not in ('walk', 'linear'):
        raise ValueError('bedroom-time must be walk or linear')
    for name in ('bedroom_walk_prior_scale', 'bedroom_linear_prior_scale'):
        value = getattr(args, name)
        if isinstance(value, bool) or not np.isfinite(value) or value <= 0:
            raise ValueError(name+' must be finite and positive')


def graph_kwargs(args):
    return {'mode': args.bedroom_time, 'walk_prior_scale': args.bedroom_walk_prior_scale,
            'linear_prior_scale': args.bedroom_linear_prior_scale,
            'building_prior_scale': args.building_prior_scale, 'unit_prior_scale': args.unit_prior_scale}


def implementation_paths(base=None):
    return [*previous.implementation_paths(), Path(graph.__file__), Path(__file__)]


def make_protocol(args, data, source, code, configuration):
    result = previous.make_protocol(args, data, source, code, configuration)
    result.update(version=VERSION, bedroom_time=args.bedroom_time,
        bedroom_walk_prior_scale=args.bedroom_walk_prior_scale if args.bedroom_time == 'walk' else None,
        bedroom_linear_prior_scale=args.bedroom_linear_prior_scale if args.bedroom_time == 'linear' else None,
        graph='Natural-spline floor design plus zero-sum, group-centered bedroom-group time deviations '
              '(studio, 1, 2, 3+); unique feature rows compressed losslessly.')
    return result


def validate_posterior(inference, args, design, configuration):
    previous.validate_posterior(inference, args, design, configuration)
    posterior = v2.base.posterior_dataset(inference)
    if not set(VARIABLES[args.bedroom_time]) <= set(posterior.data_vars):
        raise ValueError('Posterior is missing bedroom-time variables')
    curve = posterior['bedroom_time']
    if (curve.dims != ('chain', 'draw', 'bedroom_group', 'period')
            or curve.bedroom_group.values.tolist() != list(graph.GROUP_LABELS)
            or curve.period.values.tolist() != [p.strftime('%Y-%m') for p in design.time.periods]):
        raise ValueError('Bedroom-time curve coordinates differ from the design')


def fitted_summary(inference, design, data):
    """`bayesian_feature_experiment.fitted_summary` plus the bedroom-time curve."""
    base = v2.base
    p = base.posterior_dataset(inference)
    samples = {name: base.sample_values(p, name) for name in
               ('alpha', 'beta', 'trend_coefficients', 'annual_drift', 'season_coefficients',
                'building_effect', 'sigma_unit', 'unit_z')}
    curve = p['bedroom_time'].stack(sample=('chain', 'draw')).transpose('sample', 'bedroom_group', 'period').values
    d = design.time; a = d.arrays(data); x = design.matrix(data)
    group = graph.bedroom_groups(data.bedrooms)
    rows = []
    for start in range(0, len(data), 128):
        stop = min(start+128, len(data)); sl = slice(start, stop)
        mu = (samples['alpha'][:, None] + samples['beta'] @ x[sl].T
              + samples['trend_coefficients'] @ (d.time_matrix-d.time_center)[a['period'][sl]].T
              + samples['annual_drift'][:, None]*(d.linear_time-d.linear_center)[a['period'][sl]]
              + samples['season_coefficients'] @ (d.season_matrix-d.season_weights@d.season_matrix)[a['season'][sl]].T
              + samples['building_effect'][:, a['building'][sl]]
              + samples['sigma_unit'][:, None]*samples['unit_z'][:, a['unit'][sl]]
              + curve[:, group[sl], a['period'][sl]])
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


def write_reports(target, inference, design, data, protocol_hash):
    """`bayesian_feature_experiment_v2.write_reports` with bedroom-time locations."""
    reports, base = v2.reports, v2.base
    diag, table = base.diagnostics(inference)
    diag['acceptable'] = bool(diag['acceptable'] and diag['maxdepth_reached'] == 0)
    table.to_csv(target/'parameter-diagnostics.csv', index_label='parameter')
    (target/'diagnostics.json').write_text(canonical(diag)+'\n')
    derived, derived_table = v2.derived_diagnostics(inference, design, data)
    derived_table.to_csv(target/'derived-diagnostics.csv', index_label='parameter')
    (target/'derived-diagnostics.json').write_text(canonical(derived)+'\n')
    acceptable = diag['acceptable'] and derived['acceptable']
    residuals, samples = fitted_summary(inference, design, data)
    contrasts = reports.bathroom_contrasts(design, data, samples['beta'])
    contrasts['half_bath_increments'] = v2.half_bath_contrasts(design, data, samples['beta'])
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
    curves = bedroom_time_summary(inference, design)
    (target/'bedroom-time.json').write_text(canonical(curves)+'\n')
    acceptable = acceptable and curves['diagnostics']['acceptable']
    summary = {'protocol_sha256': protocol_hash, 'design_support': design.support, 'diagnostics': diag,
        'derived_diagnostics': derived, 'bedroom_time_diagnostics': curves['diagnostics'],
        'status': 'exploratory_converged' if acceptable else 'diagnostic_only_do_not_interpret_intervals',
        'median_absolute_log_residual': float(np.median([abs(r['residual_log']) for r in residuals])),
        'latent_intervals': 'Uncertainty in the conditional median asking rent of observed units; not predictive intervals or causal values.',
        'bathroom_balance': contrasts['balance'], 'main_model_changed': False}
    (target/'summary.json').write_text(canonical(summary)+'\n')
    return summary


def bedroom_time_summary(inference, design):
    """January curve values and each group's latest-month-minus-January-2017 shift."""
    posterior = v2.base.posterior_dataset(inference)
    curve = posterior['bedroom_time']
    periods = [p.strftime('%Y-%m') for p in design.time.periods]
    januaries = [p for p in periods if p.endswith('-01')]
    reference = '2017-01' if '2017-01' in periods else januaries[0]
    shift = curve.sel(period=periods[-1])-curve.sel(period=reference)
    diagnostic, _ = v2.base.diagnostics({'posterior': xr.Dataset({'bedroom_time_shift': shift}),
                                        'sample_stats': inference['sample_stats']})
    interval = v2.reports.interval
    return {'version': BEDROOM_TIME_VERSION, 'groups': list(graph.GROUP_LABELS), 'reference_period': reference,
        'latest_period': periods[-1],
        'curves': {g: {p: interval(curve.sel(bedroom_group=g, period=p).values.ravel()) for p in januaries+[periods[-1]]}
                   for g in graph.GROUP_LABELS},
        'latest_minus_reference': {g: interval(shift.sel(bedroom_group=g).values.ravel()) for g in graph.GROUP_LABELS},
        'diagnostics': diagnostic,
        'interpretation': 'Log deviation of each bedroom group from the common Chelsea trend, zero-sum across groups '
                          'and centered over each group\'s own observation months; conditional associations.'}


def completed_fit(target, protocol_hash, configuration):
    manifest, files = previous._verified_bundle(target, retain={'summary.json', 'graph-configuration.json',
        'posterior-checkpoint.json'})
    if (manifest.get('version') != VERSION or manifest.get('protocol_sha256') != protocol_hash
            or not REQUIRED_FIT <= manifest['files'].keys()):
        raise ValueError('Completed bedroom-time fit protocol/version or products differ')
    summary = json.loads(files['summary.json'])
    if (summary.get('protocol_sha256') != protocol_hash
            or json.loads(files['graph-configuration.json']) != configuration
            or json.loads(files['posterior-checkpoint.json']) != {
                'protocol_sha256': protocol_hash, 'posterior_sha256': manifest['files']['posterior.nc']}):
        raise ValueError('Completed bedroom-time fit summaries or checkpoint differ')
    return summary


def run(args):
    """`bayesian_floor_spline_experiment.run` with this module's graph and reports."""
    validate_args(args)
    root = Path(args.output); root.mkdir(exist_ok=True, parents=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data, source = load_data(args.dataset)
        paths = implementation_paths(); code = {p.name: digest(p) for p in paths}
        configuration = graph.graph_configuration(data, args.prior_multiplier, **graph_kwargs(args))
        protocol = make_protocol(args, data, source, code, configuration)
        ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol', {'protocol.json': canonical(protocol)+'\n',
            **{p.name: p.read_text() for p in paths}}, {'version': VERSION, 'protocol_sha256': ph})
        cache_code = Path(report_cache.__file__)
        reporting = {'version': report_cache.VERSION, 'protocol_sha256': ph, 'implementation_sha256': digest(cache_code)}
        publish_bundle(root/'reporting-protocol', {'reporting.json': canonical(reporting)+'\n',
            cache_code.name: cache_code.read_text()}, reporting)
        target = root/'fit'; target.mkdir(exist_ok=True)
        if (target/'complete.json').exists():
            result = completed_fit(target, ph, configuration)
            execution.verify_products(protocol, json.loads((target/'storage.json').read_text()),
                json.loads((target/'trace-manifest.json').read_text()),
                json.loads((target/'complete.json').read_text())['files']['posterior.nc'])
            return result
        v2.sampler.write_status(root/'progress.json', 'design', rows=len(data), execution_version=disk_protocol.VERSION)
        design = floor.FeatureDesign(data, args.spec, floor_prior_scale=args.floor_prior_scale)
        design.save(target)
        (target/'graph-configuration.json').write_text(canonical(configuration)+'\n')
        checkpoint = target/'posterior-checkpoint.json'
        if checkpoint.exists():
            if json.loads(checkpoint.read_text()) != {'protocol_sha256': ph, 'posterior_sha256': digest(target/'posterior.nc')}:
                raise ValueError('Invalid posterior checkpoint')
            inference = xr.open_datatree(target/'posterior.nc', engine='h5netcdf', cache=False)
        else:
            model = graph.build_model(data, design, args.prior_multiplier, **graph_kwargs(args))
            if model.graph_configuration != configuration:
                raise ValueError('Built graph differs from protocol')
            (target/'compression.json').write_text(canonical(model.compression_summary)+'\n')
            names = ['alpha', 'beta', 'sigma', 'sigma_building', 'sigma_unit', 'annual_drift', 'bedroom_time']
            with model:
                prior = v2.pm.sample_prior_predictive(draws=80, random_seed=args.seed+1, var_names=names)
            prior.to_netcdf(target/'prior.nc', engine='h5netcdf')
            inference = storage.sample_to_netcdf(model, output=target/'posterior.nc', trace_root=root/'trace',
                protocol_hash=ph, draws=args.draws, tune=args.tune, chains=args.chains, seed=args.seed,
                adaptation=args.adaptation, target_accept=args.target_accept, status_path=root/'progress.json',
                **execution.sample_options(protocol))
            validate_posterior(inference, args, design, configuration)
            (target/'trace-manifest.json').write_bytes((root/'trace/complete.json').read_bytes())
            storage.atomic_json(checkpoint, {'protocol_sha256': ph, 'posterior_sha256': digest(target/'posterior.nc')})
        try:
            validate_posterior(inference, args, design, configuration)
            v2.sampler.write_status(root/'progress.json', 'diagnostics_and_reports')
            posterior_hash = digest(target/'posterior.nc')
            with report_cache.bounded_unit_samples(v2.base, inference, root/'report-cache', posterior_hash) as cached:
                result = write_reports(target, inference, design, data, ph)
            (target/cache_code.name).write_bytes(cache_code.read_bytes())
            (target/'reporting-cache.json').write_text(canonical({**reporting, 'posterior_sha256': posterior_hash,
                'reporting_manifest_sha256': digest(root/'reporting-protocol/complete.json'),
                'cache_manifest_sha256': digest(root/'report-cache/complete.json'),
                'maximum_source_block_bytes': cached['maximum_source_block_bytes'],
                'chains': args.chains, 'draws': args.draws, 'units': len(design.time.unit_ids),
                'sample_order': 'chain_major_then_draw', 'all_retained_draws': True})+'\n')
            floors = floor_contrasts(inference, design)
            (target/'floor-contrasts.json').write_text(canonical(floors)+'\n')
            result['floor_diagnostics'] = floors['diagnostics']
            if not floors['diagnostics']['acceptable']:
                result['status'] = 'diagnostic_only_do_not_interpret_intervals'
            (target/'summary.json').write_text(canonical(result)+'\n')
            (target/'residual-scales.json').write_text(canonical(residual_scale_summary(inference, data, configuration))+'\n')
        finally:
            inference.close()
        if any(digest(p) != code[p.name] for p in paths):
            raise ValueError('Implementation changed during bedroom-time experiment')
        if not REQUIRED_FIT | {'storage.json', 'trace-manifest.json', 'reporting-cache.json', cache_code.name} <= {
                p.name for p in target.iterdir()}:
            raise ValueError('Required disk inference products missing')
        execution.verify_products(protocol, json.loads((target/'storage.json').read_text()),
            json.loads((target/'trace-manifest.json').read_text()), digest(target/'posterior.nc'))
        v2.sampler.publish_fit(target, version=VERSION, protocol_hash=ph)
        v2.sampler.write_status(root/'progress.json', 'complete', status=result['status'])
        v2.base.emit('complete', status=result['status'], output=str(target))
        return result


def argument_parser():
    parser = previous.argument_parser()
    parser.description = __doc__
    parser.add_argument('--bedroom-time', choices=('walk', 'linear'), default='walk')
    parser.add_argument('--bedroom-walk-prior-scale', type=float, default=.05)
    parser.add_argument('--bedroom-linear-prior-scale', type=float, default=.02)
    return parser


if __name__ == '__main__':
    args = argument_parser().parse_args()
    with threadpool_limits(limits=1, user_api='blas'):
        run(args)
