"""Versioned PyMC natural-spline floor specification with durable posterior draws."""
from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import json
import math
import sys
from pathlib import Path

import numpy as np
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_experiment_v3 as previous
from . import bayesian_floor_spline_design as floor
from . import bayesian_disk_sampling as storage
from . import bayesian_disk_protocol as disk_protocol
from . import bayesian_disk_experiment as disk
from . import bayesian_floor_execution as execution
from . import bayesian_report_cache as report_cache

VERSION = 'observable-bayesian-floor-spline-experiment-v5'
FLOOR_CONTRAST_VERSION = 'joint-listed-floor-spline-component-contrasts-v1'
FLOOR_INTERPRETATION = 'Joint regularized natural-spline floor-component contrasts, holding other encoded terms fixed. Conditional associations, not causal or physical-height effects; shared smoothness and source support remain explicit.'
STORAGE_POLICY = disk_protocol.POLICY
v2, graph = previous.v2, previous.graph
load_data = previous.load_data
graph_kwargs = previous.graph_kwargs
validate_posterior = previous.validate_posterior
residual_scale_summary = previous.residual_scale_summary
REQUIRED_FIT = previous.REQUIRED_FIT | {'floor-contrasts.json'}


def validate_args(args):
    previous.validate_args(args)
    value = args.floor_prior_scale
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Floor prior scale must be finite and positive')
    if getattr(args, 'floor_block_graph_validation', None) or getattr(args, 'graph_validation', None):
        raise ValueError('Existing linear/increment parity proofs cannot validate a spline design')


def implementation_paths(base=None):
    return [*previous.implementation_paths(), Path(floor.__file__), Path(__file__).with_name('bayesian_floor_increment_design.py'),
            Path(storage.__file__), Path(disk_protocol.__file__), Path(disk.__file__),
            *execution.implementation_paths(), Path(__file__)]


def make_protocol(args, data, source, code, configuration):
    result = previous.make_protocol(args, data, source, code, configuration)
    values = floor.listed_floor_values(data)
    levels = np.unique(values[np.isfinite(values)]).tolist()
    knots, anchor = floor.knot_specification(levels)
    result.update(version=VERSION, feature_design_version=floor.VERSION,
        floor_prior_scale=args.floor_prior_scale, floor_levels=levels,
        floor_knots=knots, floor_reference=anchor, floor_policy=floor.policy(),
        execution_version=disk_protocol.VERSION, storage_policy=STORAGE_POLICY,
        storage_versions={p: importlib.metadata.version(p) for p in ('zarr','obstore','xarray','h5py')},
        graph='Lossless repeated-feature compression of the natural-spline floor design; nonfloor terms unchanged.')
    return execution.update_protocol(result, args, code)


def floor_contrasts(inference, design):
    posterior = v2.base.posterior_dataset(inference)
    if posterior.beta.dims != ('chain', 'draw', 'feature') or posterior.beta.feature.values.tolist() != design.features:
        raise ValueError('Posterior feature coordinates differ from spline design')
    levels = design.floor_levels
    pairs = list(zip(levels[:-1], levels[1:]))
    if len(levels) > 2:
        pairs.append((levels[0], levels[-1]))
    directions = [design.contrast_vector(low, high) for low, high in pairs]
    basis = xr.DataArray(np.asarray(directions), dims=('contrast','feature'),
        coords={'contrast': np.arange(len(pairs)), 'feature': design.features})
    joint = xr.dot(posterior.beta, basis, dim='feature')
    diagnostic, _ = v2.base.diagnostics({'posterior': xr.Dataset({'floor_contrast': joint}),
                                       'sample_stats': inference['sample_stats']})
    counts = {r['level']: r for r in design.floor_support['levels']}
    overlap = {(r['lower_supported_level'],r['upper_supported_level']): r
               for r in design.floor_support['adjacent_supported_contrasts']}
    contrasts = []
    for index, (low, high) in enumerate(pairs):
        effect = v2.reports.interval(joint.isel(contrast=index).values.ravel())
        percent = {**effect, **{k: 100*math.expm1(effect[k]) for k in ('lower_95','median','upper_95')}}
        contrasts.append({'lower_floor': low, 'upper_floor': high,
            'kind': 'adjacent_observed_levels' if (low, high) in overlap else 'observed_range',
            'support_lower': counts[low], 'support_upper': counts[high],
            'adjacent_overlap': overlap.get((low, high)), 'log_effect': effect, 'percent_effect': percent})
    return {'version': FLOOR_CONTRAST_VERSION, 'floor_levels': levels,
        'floor_knots': design.floor_knots, 'floor_reference': design.floor_reference,
        'floor_prior_scale': design.floor_prior_scale, 'floor_policy': design.floor_policy,
        'contrasts': contrasts, 'diagnostics': diagnostic,
        'draws': posterior.sizes['chain']*posterior.sizes['draw'], 'interpretation': FLOOR_INTERPRETATION}


def completed_fit(target, protocol_hash, configuration):
    manifest, files = _verified_bundle(target, retain={'summary.json','graph-configuration.json',
        'posterior-checkpoint.json','floor-contrasts.json'})
    if (manifest.get('version') != VERSION or manifest.get('protocol_sha256') != protocol_hash
            or not REQUIRED_FIT <= manifest['files'].keys()):
        raise ValueError('Completed spline fit protocol/version or products differ')
    summary, floors = json.loads(files['summary.json']), json.loads(files['floor-contrasts.json'])
    if (summary.get('protocol_sha256') != protocol_hash
            or json.loads(files['graph-configuration.json']) != configuration
            or json.loads(files['posterior-checkpoint.json']) != {
                'protocol_sha256': protocol_hash, 'posterior_sha256': manifest['files']['posterior.nc']}
            or floors.get('version') != FLOOR_CONTRAST_VERSION
            or summary.get('floor_diagnostics') != floors.get('diagnostics')):
        raise ValueError('Completed spline fit summaries or checkpoint differ')
    return summary

def run(args):
    base = sys.modules[__name__]
    base.validate_args(args)
    root = Path(args.output);root.mkdir(exist_ok=True,parents=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data,source=base.load_data(args.dataset)
        paths=implementation_paths(base);code={p.name:digest(p) for p in paths}
        configuration=base.graph.graph_configuration(data,args.prior_multiplier,**base.graph_kwargs(args))
        protocol=make_protocol(args,data,source,code,configuration)
        ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**execution.protocol_files(args),
            **{p.name:p.read_text() for p in paths}},{'version':base.VERSION,'protocol_sha256':ph})
        # Report execution is a separate immutable stage; its cache changes
        # neither the sampler protocol's mathematical model nor retained draws.
        cache_code = Path(report_cache.__file__)
        reporting = {'version': report_cache.VERSION, 'protocol_sha256': ph,
                     'implementation_sha256': digest(cache_code)}
        publish_bundle(root/'reporting-protocol', {'reporting.json': canonical(reporting)+'\n',
            cache_code.name: cache_code.read_text()}, reporting)
        target=root/'fit';target.mkdir(exist_ok=True)
        if (target/'complete.json').exists():
            manifest=json.loads((target/'complete.json').read_text())
            if not {'storage.json','trace-manifest.json'}<=manifest['files'].keys():
                raise ValueError('Disk fit is missing storage evidence')
            result=base.completed_fit(target,ph,configuration)
            execution.verify_products(protocol,json.loads((target/'storage.json').read_text()),
                json.loads((target/'trace-manifest.json').read_text()),manifest['files']['posterior.nc'])
            return result
        base.v2.sampler.write_status(root/'progress.json','design',rows=len(data),execution_version=disk_protocol.VERSION)
        design=floor.FeatureDesign(data,args.spec,floor_prior_scale=args.floor_prior_scale)
        design.save(target)
        execution.verify_saved_design(args,target)
        (target/'graph-configuration.json').write_text(canonical(configuration)+'\n')
        checkpoint=target/'posterior-checkpoint.json'
        if checkpoint.exists():
            if json.loads(checkpoint.read_text()) != {'protocol_sha256':ph,'posterior_sha256':digest(target/'posterior.nc')}:
                raise ValueError('Invalid posterior checkpoint')
            inference=xr.open_datatree(target/'posterior.nc',engine='h5netcdf',cache=False)
        else:
            graph=execution.graph if 'execution_graph' in protocol else base.graph
            model=graph.build_model(data,design,args.prior_multiplier,**base.graph_kwargs(args))
            if model.graph_configuration != configuration:raise ValueError('Built graph differs from protocol')
            (target/'compression.json').write_text(canonical(model.compression_summary)+'\n')
            names=['alpha','beta','sigma','sigma_building','sigma_unit','annual_drift']
            if args.residual_scale=='bedroom':
                names+=['residual_bedroom_z','residual_bedroom_scale','sigma_by_bedroom']
                if configuration.get('residual_bedroom_parameterization')=='centered':names+=['residual_bedroom_offset']
            with model:prior=base.v2.pm.sample_prior_predictive(draws=80,random_seed=args.seed+1,var_names=names)
            prior.to_netcdf(target/'prior.nc',engine='h5netcdf')
            inference=storage.sample_to_netcdf(model,output=target/'posterior.nc',trace_root=root/'trace',
                protocol_hash=ph,draws=args.draws,tune=args.tune,chains=args.chains,seed=args.seed,
                adaptation=args.adaptation,target_accept=args.target_accept,status_path=root/'progress.json',**execution.sample_options(protocol))
            base.validate_posterior(inference,args,design,configuration)
            (target/'trace-manifest.json').write_bytes((root/'trace/complete.json').read_bytes())
            storage.atomic_json(checkpoint,{'protocol_sha256':ph,'posterior_sha256':digest(target/'posterior.nc')})
        try:
            base.validate_posterior(inference,args,design,configuration)
            base.v2.sampler.write_status(root/'progress.json','diagnostics_and_reports')
            posterior_hash = digest(target/'posterior.nc')
            with report_cache.bounded_unit_samples(base.v2.base,inference,root/'report-cache',posterior_hash) as cached:
                result=base.v2.write_reports(target,inference,design,data,ph)
            if digest(cache_code) != reporting['implementation_sha256']:
                raise ValueError('Report cache implementation changed')
            (target/cache_code.name).write_bytes(cache_code.read_bytes())
            (target/'reporting-cache.json').write_text(canonical({**reporting,
                'posterior_sha256': posterior_hash,
                'reporting_manifest_sha256': digest(root/'reporting-protocol/complete.json'),
                'cache_manifest_sha256': digest(root/'report-cache/complete.json'),
                'maximum_source_block_bytes': cached['maximum_source_block_bytes'],
                'chains': args.chains, 'draws': args.draws, 'units': len(design.time.unit_ids),
                'sample_order': 'chain_major_then_draw', 'all_retained_draws': True})+'\n')
            floors=floor_contrasts(inference,design)
            (target/'floor-contrasts.json').write_text(canonical(floors)+'\n')
            result['floor_diagnostics']=floors['diagnostics']
            if not floors['diagnostics']['acceptable']:result['status']='diagnostic_only_do_not_interpret_intervals'
            (target/'summary.json').write_text(canonical(result)+'\n')
            (target/'residual-scales.json').write_text(canonical(base.residual_scale_summary(inference,data,configuration))+'\n')
        finally:inference.close()
        if any(digest(p)!=code[p.name] for p in paths):raise ValueError('Implementation changed during disk experiment')
        if not base.REQUIRED_FIT|{'storage.json','trace-manifest.json','reporting-cache.json',cache_code.name} <= {p.name for p in target.iterdir()}:
            raise ValueError('Required disk inference products missing')
        execution.verify_products(protocol,json.loads((target/'storage.json').read_text()),
            json.loads((target/'trace-manifest.json').read_text()),digest(target/'posterior.nc'))
        base.v2.sampler.publish_fit(target,version=base.VERSION,protocol_hash=ph)
        base.v2.sampler.write_status(root/'progress.json','complete',status=result['status'])
        base.v2.base.emit('complete',status=result['status'],output=str(target))
        return result


def argument_parser():
    parser = previous.argument_parser()
    parser.description = __doc__
    parser.set_defaults(draws=6000, tune=4000, target_accept=.93)
    parser.add_argument('--floor-prior-scale', type=float, default=.10)
    execution.add_arguments(parser)
    parser.set_defaults(maxdepth=10)
    return parser


if __name__ == '__main__':
    args = argument_parser().parse_args()
    with threadpool_limits(limits=1, user_api='blas'):
        run(args)
