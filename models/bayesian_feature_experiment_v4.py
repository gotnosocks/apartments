"""Versioned PyMC experiment with observed listed-floor threshold increments.

Uses the existing exact compressed graph and retained joint draws. All other
mean terms are unchanged; this is a new posterior, never a relabeling of v3.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import xarray as xr
from threadpoolctl import threadpool_limits

from . import bayesian_feature_experiment_v3 as previous
from . import bayesian_floor_increment_design as floor
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

VERSION = 'observable-bayesian-floor-experiment-v4'
FLOOR_CONTRAST_VERSION = 'joint-listed-floor-component-contrasts-v1'
v2, graph = previous.v2, previous.graph
REQUIRED_FIT = previous.REQUIRED_FIT | {'floor-contrasts.json'}
load_data = previous.load_data
graph_kwargs = previous.graph_kwargs
validate_posterior = previous.validate_posterior
residual_scale_summary = previous.residual_scale_summary


def validate_args(args):
    previous.validate_args(args)
    value = args.floor_increment_prior_scale
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Floor increment prior scale must be finite and positive')


def implementation_paths():
    return [*previous.implementation_paths(), Path(floor.__file__), Path(__file__)]


def make_protocol(args, data, source, code, configuration):
    common = copy.copy(args)
    common.graph_validation = None
    result = previous.make_protocol(common, data, source, code, configuration)
    observed_floors = floor.listed_floor_values(data)
    levels = np.unique(observed_floors[np.isfinite(observed_floors)]).tolist()
    result.update(version=VERSION, feature_design_version=floor.VERSION,
        floor_increment_prior_scale=args.floor_increment_prior_scale,
        floor_levels=levels, floor_thresholds=levels[:-1],
        floor_policy='Observed-level threshold increments with unconstrained signs; unknown separate; gaps are joint observed-endpoint contrasts, not individually identified missing levels.',
        graph='Exact repeated-feature compression with a versioned floor-increment mean design; other feature families unchanged.')
    if args.graph_validation:
        manifest, files = _verified_bundle(args.graph_validation, retain={'parity.json'})
        proof = json.loads(files['parity.json'])
        if (proof.get('version') != 'bayesian-floor-graph-parity-v1' or proof.get('passed') is not True
                or proof.get('source_manifest_sha256') != result['source_manifest_sha256']
                or proof.get('source_observations_sha256') != result['source_observations_sha256']
                or proof.get('specification') != args.spec
                or proof.get('floor_increment_prior_scale') != args.floor_increment_prior_scale
                or proof.get('floor_levels') != levels
                or proof.get('graph_configuration') != configuration
                or proof.get('rows') != len(data)):
            raise ValueError('Floor graph proof differs from source or design settings')
        required = {p.name for p in previous.implementation_paths()} | {Path(floor.__file__).name}
        validated = proof.get('implementation_sha256', {})
        if not required <= validated.keys() or any(code.get(k) != v for k,v in validated.items()):
            raise ValueError('Floor graph proof implementation differs')
        result['graph_verification'] = {'manifest_sha256': digest(Path(args.graph_validation)/'complete.json'),
                                      'version': manifest['version'], 'rows': proof['rows']}
    return result


def floor_contrasts(inference, design):
    posterior = v2.base.posterior_dataset(inference)
    levels = design.floor_levels
    pairs = list(zip(levels[:-1], levels[1:]))
    if len(levels)>2: pairs.append((levels[0], levels[-1]))
    directions = []
    for low, high in pairs:
        direction = np.zeros(len(design.features))
        for threshold in design.floor_thresholds:
            if low <= threshold < high: direction[design.features.index(floor._name(threshold))] = 1.
        directions.append(direction)
    contrasts = []
    if directions:
        basis = xr.DataArray(np.array(directions), dims=('floor_contrast','feature'),
            coords={'floor_contrast':np.arange(len(pairs)), 'feature':design.features})
        joint = xr.dot(posterior.beta, basis, dim='feature')
        diagnostic, _ = v2.base.diagnostics({'posterior':xr.Dataset({'floor_contrast':joint}),
                                            'sample_stats':inference['sample_stats']})
        counts = {r['level']:r for r in design.floor_support['levels']}
        overlap = {(r['lower_supported_level'],r['upper_supported_level']):r
                   for r in design.floor_support['adjacent_supported_contrasts']}
        for i,(low,high) in enumerate(pairs):
            values = joint.isel(floor_contrast=i).values.ravel()
            log_effect = v2.reports.interval(values)
            percent_effect = {**log_effect, **{bound:100*math.expm1(log_effect[bound])
                               for bound in ('lower_95','median','upper_95')}}
            contrasts.append({'lower_floor':low,'upper_floor':high,
                'kind':'adjacent_observed_levels' if (low,high) in overlap else 'observed_range',
                'support_lower':counts[low], 'support_upper':counts[high],
                'adjacent_overlap':overlap.get((low,high)),
                'log_effect':log_effect, 'percent_effect':percent_effect})
    else:
        diagnostic = {'acceptable':True,'deterministic':True,'reason':'No varying observed floor contrast'}
    return {'version':FLOOR_CONTRAST_VERSION, 'floor_levels':levels,
            'floor_thresholds':design.floor_thresholds, 'contrasts':contrasts,
            'diagnostics':diagnostic, 'draws':posterior.sizes['chain']*posterior.sizes['draw'],
            'interpretation':'Joint floor-feature component contrasts, holding other encoded terms fixed. All retained draws; unconstrained signs. Not causal, not physical-height effects, and sparse overlap remains explicit.'}


def completed_fit(target, protocol_hash, configuration):
    manifest, files = _verified_bundle(target, retain={'summary.json','graph-configuration.json','posterior-checkpoint.json','floor-contrasts.json'})
    if (manifest.get('version') != VERSION or manifest.get('protocol_sha256') != protocol_hash
            or not REQUIRED_FIT <= manifest['files'].keys()):
        raise ValueError('Completed floor fit protocol/version or products differ')
    summary = json.loads(files['summary.json'])
    floors = json.loads(files['floor-contrasts.json'])
    if (summary.get('protocol_sha256') != protocol_hash
            or json.loads(files['graph-configuration.json']) != configuration
            or summary.get('floor_diagnostics') != floors.get('diagnostics')
            or floors.get('version') != FLOOR_CONTRAST_VERSION
            or json.loads(files['posterior-checkpoint.json']) != {
                'protocol_sha256':protocol_hash,'posterior_sha256':manifest['files']['posterior.nc']}):
        raise ValueError('Completed floor fit summaries or checkpoint differ')
    return summary


def run(args):
    validate_args(args)
    root = Path(args.output); root.mkdir(parents=True,exist_ok=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        data,source = load_data(args.dataset)
        paths = implementation_paths()
        code = {p.name:digest(p) for p in paths}
        configuration = graph.graph_configuration(data,args.prior_multiplier,**graph_kwargs(args))
        protocol = make_protocol(args,data,source,code,configuration)
        ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',
            **{p.name:p.read_text() for p in paths}},{'version':VERSION,'protocol_sha256':ph})
        target = root/'fit'
        if (target/'complete.json').exists():
            return completed_fit(target,ph,configuration)
        target.mkdir(exist_ok=True)
        v2.sampler.write_status(root/'progress.json','design',rows=len(data),specification=args.spec,
                                graph_configuration=configuration)
        design = floor.FeatureDesign(data,args.spec, floor_increment_prior_scale=args.floor_increment_prior_scale)
        design.save(target)
        (target/'graph-configuration.json').write_text(canonical(configuration)+'\n')
        v2.base.emit('design_ready',**design.support)
        checkpoint = target/'posterior-checkpoint.json'
        if checkpoint.exists():
            if json.loads(checkpoint.read_text()) != {'protocol_sha256':ph,'posterior_sha256':digest(target/'posterior.nc')}:
                raise ValueError('Invalid posterior checkpoint')
            inference = v2.az.from_netcdf(target/'posterior.nc')
        else:
            model = graph.build_model(data,design,args.prior_multiplier,**graph_kwargs(args))
            if model.graph_configuration != configuration:
                raise ValueError('Built graph settings differ from immutable protocol')
            (target/'compression.json').write_text(canonical(model.compression_summary)+'\n')
            prior_names = ['alpha','beta','sigma','sigma_building','sigma_unit','annual_drift']
            if args.residual_scale == 'bedroom':
                prior_names += ['residual_bedroom_z','residual_bedroom_scale','sigma_by_bedroom']
                if configuration.get('residual_bedroom_parameterization') == 'centered':
                    prior_names.append('residual_bedroom_offset')
            with model:
                prior = v2.pm.sample_prior_predictive(draws=80,random_seed=args.seed+1,var_names=prior_names)
            prior.to_netcdf(target/'prior.nc',engine='h5netcdf')
            inference = v2.sampler.sample(model,draws=args.draws,tune=args.tune,chains=args.chains,
                seed=args.seed,adaptation=args.adaptation,target_accept=args.target_accept,
                status_path=root/'progress.json')
            validate_posterior(inference,args,design,configuration)
            inference.to_netcdf(target/'posterior.nc',engine='h5netcdf')
            checkpoint.write_text(canonical({'protocol_sha256':ph,'posterior_sha256':digest(target/'posterior.nc')})+'\n')
        validate_posterior(inference,args,design,configuration)
        v2.sampler.write_status(root/'progress.json','diagnostics_and_reports')
        result = v2.write_reports(target,inference,design,data,ph)
        floor_summary = floor_contrasts(inference, design)
        (target/'floor-contrasts.json').write_text(canonical(floor_summary)+'\n')
        result['floor_diagnostics'] = floor_summary['diagnostics']
        if not floor_summary['diagnostics']['acceptable']:
            result['status'] = 'diagnostic_only_do_not_interpret_intervals'
        (target/'summary.json').write_text(canonical(result)+'\n')
        (target/'residual-scales.json').write_text(canonical(residual_scale_summary(inference,data,configuration))+'\n')
        if any(digest(p) != code[p.name] for p in paths):
            raise ValueError('Implementation changed during experiment')
        if not REQUIRED_FIT <= {p.name for p in target.iterdir()}:
            raise ValueError('Required inference products missing before completion')
        v2.sampler.publish_fit(target,version=VERSION,protocol_hash=ph)
        v2.sampler.write_status(root/'progress.json','complete',status=result['status'])
        v2.base.emit('complete',status=result['status'],output=str(target))
        return result


def argument_parser():
    parser = previous.argument_parser()
    parser.description = __doc__
    parser.set_defaults(draws=4000, tune=2000)
    parser.add_argument('--floor-increment-prior-scale', type=float, default=.15)
    return parser


if __name__ == '__main__':
    parser = argument_parser(); args = parser.parse_args()
    try: validate_args(args)
    except ValueError as error: parser.error(str(error))
    with threadpool_limits(limits=1, user_api='blas'):
        run(args)
