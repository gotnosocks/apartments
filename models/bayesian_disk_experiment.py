"""Run the frozen v3/v4 PyMC specifications with durable disk-backed sampling.

Model-family versions remain explicit; execution_version separately identifies
trace storage. No mean, prior, likelihood or convergence rule is changed.
"""
from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import json
from pathlib import Path

import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from . import bayesian_feature_experiment_v3 as linear
from . import bayesian_feature_experiment_v4 as increments
from . import bayesian_disk_sampling as storage
from . import bayesian_report_cache as report_cache

from . import bayesian_disk_protocol as disk_protocol

VERSION = disk_protocol.VERSION
STORAGE_POLICY = disk_protocol.POLICY


def implementation_paths(base):
    return [*base.implementation_paths(),Path(storage.__file__),Path(disk_protocol.__file__),Path(__file__)]


def make_protocol(args,data,source,code,configuration):
    base = increments if args.floor_increments else linear
    protocol = base.make_protocol(args,data,source,code,configuration)
    protocol.update(execution_version=VERSION,storage_policy=STORAGE_POLICY,
        storage_versions={p:importlib.metadata.version(p) for p in ('zarr','obstore','xarray','h5py')})
    return protocol


def run(args):
    base = increments if args.floor_increments else linear
    base.validate_args(args)
    root = Path(args.output);root.mkdir(exist_ok=True,parents=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data,source=base.load_data(args.dataset)
        paths=implementation_paths(base);code={p.name:digest(p) for p in paths}
        configuration=base.graph.graph_configuration(data,args.prior_multiplier,**base.graph_kwargs(args))
        protocol=make_protocol(args,data,source,code,configuration)
        ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',
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
            disk_protocol.verify_products(protocol,json.loads((target/'storage.json').read_text()),
                json.loads((target/'trace-manifest.json').read_text()),manifest['files']['posterior.nc'])
            return result
        base.v2.sampler.write_status(root/'progress.json','design',rows=len(data),execution_version=VERSION)
        design=(increments.floor.FeatureDesign(data,args.spec,floor_increment_prior_scale=args.floor_increment_prior_scale)
                if args.floor_increments else linear.v2.feature.FeatureDesign(data,args.spec))
        design.save(target)
        (target/'graph-configuration.json').write_text(canonical(configuration)+'\n')
        checkpoint=target/'posterior-checkpoint.json'
        if checkpoint.exists():
            if json.loads(checkpoint.read_text()) != {'protocol_sha256':ph,'posterior_sha256':digest(target/'posterior.nc')}:
                raise ValueError('Invalid posterior checkpoint')
            inference=xr.open_datatree(target/'posterior.nc',engine='h5netcdf',cache=False)
        else:
            model=base.graph.build_model(data,design,args.prior_multiplier,**base.graph_kwargs(args))
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
                adaptation=args.adaptation,target_accept=args.target_accept,status_path=root/'progress.json')
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
            if args.floor_increments:
                floors=increments.floor_contrasts(inference,design)
                (target/'floor-contrasts.json').write_text(canonical(floors)+'\n')
                result['floor_diagnostics']=floors['diagnostics']
                if not floors['diagnostics']['acceptable']:result['status']='diagnostic_only_do_not_interpret_intervals'
                (target/'summary.json').write_text(canonical(result)+'\n')
            (target/'residual-scales.json').write_text(canonical(base.residual_scale_summary(inference,data,configuration))+'\n')
        finally:inference.close()
        if any(digest(p)!=code[p.name] for p in paths):raise ValueError('Implementation changed during disk experiment')
        if not base.REQUIRED_FIT|{'storage.json','trace-manifest.json','reporting-cache.json',cache_code.name} <= {p.name for p in target.iterdir()}:
            raise ValueError('Required disk inference products missing')
        disk_protocol.verify_products(protocol,json.loads((target/'storage.json').read_text()),
            json.loads((target/'trace-manifest.json').read_text()),digest(target/'posterior.nc'))
        base.v2.sampler.publish_fit(target,version=base.VERSION,protocol_hash=ph)
        base.v2.sampler.write_status(root/'progress.json','complete',status=result['status'])
        base.v2.base.emit('complete',status=result['status'],output=str(target))
        return result


def argument_parser():
    parser=increments.argument_parser();parser.description=__doc__
    parser.add_argument('--floor-increments',action='store_true',help='Use v4 floor thresholds; otherwise preserve v3 mean design')
    return parser


if __name__=='__main__':
    args=argument_parser().parse_args()
    with threadpool_limits(limits=1,user_api='blas'):run(args)
