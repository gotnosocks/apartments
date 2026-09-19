"""Explicit protocol and joint contrasts for exact PyMC floor/access experiments."""
import copy
import hashlib
import fcntl
import importlib.metadata
import json
import math
from pathlib import Path

import numpy as np
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_feature_experiment_v4 as previous
from . import bayesian_floor_elevator_design as feature
from . import bayesian_disk_experiment as disk
from . import bayesian_category_contrasts as contrasts

storage, report_cache, disk_protocol = disk.storage, disk.report_cache, disk.disk_protocol

VERSION = 'observable-bayesian-floor-elevator-experiment-v5'
CONTRAST_VERSION = 'joint-lower-floor-elevator-contrasts-v1'
PARITY_VERSION = 'bayesian-floor-elevator-graph-parity-v1'
REQUIRED_FIT = (previous.REQUIRED_FIT-{'floor-contrasts.json'}) | {
    'interaction-design.json', 'floor-elevator-contrasts.json', 'floor-elevator-diagnostics.csv',
    'storage.json', 'trace-manifest.json'}
POLICY = ('Known no/yes elevator weights -0.5/+0.5; unknown zero. Thresholds 2, 3, 4 only; '
          'unknown floor contributes zero before centering. Pooled sum divided by sqrt(3), '
          'matching the separate model full-range interaction-difference prior variance. '
          'Base floor curve is the known-access midpoint; interaction saturates above 5. '
          'Advertised labels, not measured height; source conflicts remain separate.')


def validate_args(args):
    previous.validate_args(args)
    if args.interaction_mode not in feature.MODES:
        raise ValueError('Unsupported interaction representation')
    value = args.interaction_prior_scale
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Positive finite interaction prior scale required')


def implementation_paths():
    return [*disk.implementation_paths(previous), Path(feature.__file__), Path(contrasts.__file__), Path(__file__)]


def make_protocol(args, data, source, code, configuration):
    validate_args(args)
    common = copy.copy(args)
    common.graph_validation = None
    result = previous.make_protocol(common, data, source, code, configuration)
    result.update(version=VERSION, feature_design_version=feature.VERSION,
        base_feature_design_version=feature.floor.VERSION,
        interaction_mode=args.interaction_mode, interaction_prior_scale=args.interaction_prior_scale,
        interaction_thresholds=list(feature.THRESHOLDS), interaction_policy=POLICY,
        graph='Exact repeated-feature compression with explicit lower-floor elevator interactions.',
        execution_version=disk.VERSION, storage_policy=disk.STORAGE_POLICY,
        storage_versions={p: importlib.metadata.version(p) for p in ('zarr', 'obstore', 'xarray', 'h5py')})
    if args.graph_validation is not None and not getattr(args,'floor_block_graph_validation',None):
        manifest, files = _verified_bundle(args.graph_validation, retain={'parity.json'})
        proof = json.loads(files['parity.json'])
        expected = {k: result[k] for k in ('source_manifest_sha256', 'source_observations_sha256',
            'specification', 'floor_increment_prior_scale', 'floor_levels', 'graph_configuration',
            'rows', 'interaction_mode', 'interaction_prior_scale', 'interaction_thresholds')}
        if (manifest.get('version') != PARITY_VERSION or proof.get('version') != PARITY_VERSION
                or proof.get('passed') is not True or any(proof.get(k) != v for k, v in expected.items())):
            raise ValueError('Interaction graph proof differs from source or design settings')
        required = {p.name for p in implementation_paths()}
        validated = proof.get('implementation_sha256', {})
        if not required <= validated.keys() or any(code.get(k) != v for k, v in validated.items()):
            raise ValueError('Interaction graph proof implementation differs')
        result['graph_verification'] = {'manifest_sha256': digest(Path(args.graph_validation)/'complete.json'),
            'version': manifest['version'], 'rows': proof['rows']}
    return disk.execution.update_protocol(result,args,code)


def construct_contrasts(design, data):
    levels = design.floor_levels
    pairs = list(zip(levels[:-1], levels[1:]))
    if len(levels) > 2: pairs.append((levels[0], levels[-1]))
    values = feature.floor.listed_floor_values(data)
    claims = np.asarray([feature.pricing._boolean(feature.floor.reference.amenity.feature_record(r).get('elevator'))
                         for r in data.to_dict('records')], dtype=object)
    def support(level, access):
        rows = data.loc[(values == level) & (claims == int(access))]
        return contrasts.support(rows)
    result = []
    for low, high in pairs:
        for access in (False, True):
            vector = feature.floor_contrast_vector(design, data, low, high, access)
            before, after = support(low, access), support(high, access)
            result.append({'id': f'floor:{low:g}->{high:g}:elevator={int(access)}',
                'kind': 'floor_change_at_known_access', 'lower_floor': low, 'upper_floor': high,
                'elevator': access, 'support_before': before, 'support_after': after,
                'supported_endpoints': bool(before['rows'] and after['rows']), 'design_vector': vector.tolist()})
    for low, high in [(2., 3.), (3., 4.), (4., 5.), (2., 5.)]:
        vector = (feature.floor_contrast_vector(design, data, low, high, True)
                  -feature.floor_contrast_vector(design, data, low, high, False))
        cells = [{'floor': level, 'elevator': access, **support(level, access)}
                 for level in (low, high) for access in (False, True)]
        result.append({'id': f'interaction_difference:{low:g}->{high:g}',
            'kind': 'elevator_minus_no_elevator_floor_change', 'lower_floor': low, 'upper_floor': high,
            'support': cells, 'supported_endpoints': all(c['rows'] > 0 for c in cells), 'design_vector': vector.tolist()})
    return result


def joint_contrasts(inference, design, data, *, prior_multiplier=1.):
    posterior = previous.v2.base.posterior_dataset(inference)
    if posterior.beta.dims != ('chain', 'draw', 'feature') or posterior.feature.values.tolist() != design.features:
        raise ValueError('Interaction posterior coordinates or dimensions differ')
    definitions = construct_contrasts(design, data)
    for item in definitions:
        item['log_contrast_prior_sd'] = float(np.linalg.norm(np.asarray(item['design_vector'])*design.prior_scales)*prior_multiplier)
    rows, table = contrasts.calculate(posterior.beta.values, definitions)
    return {'version': CONTRAST_VERSION, 'interaction_mode': design.mode,
        'contrasts': rows, 'all_contrasts_acceptable': all(r['diagnostics']['acceptable'] for r in rows),
        'chains': posterior.sizes['chain'], 'draws_per_chain': posterior.sizes['draw'],
        'all_joint_beta_draws': True, 'policy': POLICY,
        'interpretation': 'Conditional advertised-floor component contrasts combining main and interaction terms. Unsupported access/floor endpoints are extrapolations, not observed premiums. Joint draws preserve covariance; reporting conventions, group priors and source errors remain separate.'}, table


def completed_fit(target, protocol_hash, configuration):
    manifest, files = _verified_bundle(target, retain={
        'summary.json', 'graph-configuration.json', 'posterior-checkpoint.json', 'floor-elevator-contrasts.json'})
    if (manifest.get('version') != VERSION or manifest.get('protocol_sha256') != protocol_hash
            or not REQUIRED_FIT <= manifest['files'].keys()):
        raise ValueError('Completed interaction fit protocol/version or products differ')
    summary = json.loads(files['summary.json'])
    joint = json.loads(files['floor-elevator-contrasts.json'])
    if (summary.get('protocol_sha256') != protocol_hash
            or json.loads(files['graph-configuration.json']) != configuration
            or joint.get('version') != CONTRAST_VERSION
            or summary.get('floor_elevator_contrasts_acceptable') != joint.get('all_contrasts_acceptable')
            or json.loads(files['posterior-checkpoint.json']) != {
                'protocol_sha256': protocol_hash, 'posterior_sha256': manifest['files']['posterior.nc']}):
        raise ValueError('Completed interaction fit summaries or checkpoint differ')
    return summary


def run(args):
    base = previous
    validate_args(args)
    if args.graph_validation is None and not getattr(args,'floor_block_graph_validation',None):
        raise ValueError('Full-cohort compiled interaction graph parity is required before sampling')
    root = Path(args.output);root.mkdir(exist_ok=True,parents=True)
    with (root/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data,source=base.load_data(args.dataset)
        paths=implementation_paths();code={p.name:digest(p) for p in paths}
        configuration=base.graph.graph_configuration(data,args.prior_multiplier,**base.graph_kwargs(args))
        protocol=make_protocol(args,data,source,code,configuration)
        ph=hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(root/'protocol',{'protocol.json':canonical(protocol)+'\n',**disk.execution.protocol_files(args),
            **{p.name:p.read_text() for p in paths}},{'version':VERSION,'protocol_sha256':ph})
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
            result=completed_fit(target,ph,configuration)
            disk.execution.verify_products(protocol,json.loads((target/'storage.json').read_text()),
                json.loads((target/'trace-manifest.json').read_text()),manifest['files']['posterior.nc'])
            return result
        base.v2.sampler.write_status(root/'progress.json','design',rows=len(data),execution_version=disk.VERSION)
        design=feature.FeatureDesign(data,args.spec,mode=args.interaction_mode,
            interaction_prior_scale=args.interaction_prior_scale,floor_increment_prior_scale=args.floor_increment_prior_scale)
        design.save(target)
        disk.execution.verify_saved_design(args,target)
        (target/'graph-configuration.json').write_text(canonical(configuration)+'\n')
        checkpoint=target/'posterior-checkpoint.json'
        if checkpoint.exists():
            if json.loads(checkpoint.read_text()) != {'protocol_sha256':ph,'posterior_sha256':digest(target/'posterior.nc')}:
                raise ValueError('Invalid posterior checkpoint')
            inference=xr.open_datatree(target/'posterior.nc',engine='h5netcdf',cache=False)
        else:
            graph=disk.execution.graph if 'execution_graph' in protocol else base.graph
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
                adaptation=args.adaptation,target_accept=args.target_accept,status_path=root/'progress.json',**disk.execution.sample_options(protocol))
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
            joint, diagnostic_table=joint_contrasts(inference,design,data,prior_multiplier=args.prior_multiplier)
            (target/'floor-elevator-contrasts.json').write_text(canonical(joint)+'\n')
            diagnostic_table.to_csv(target/'floor-elevator-diagnostics.csv',index_label='contrast')
            result['floor_elevator_contrasts_acceptable']=joint['all_contrasts_acceptable']
            if not joint['all_contrasts_acceptable']:result['status']='diagnostic_only_do_not_interpret_intervals'
            (target/'summary.json').write_text(canonical(result)+'\n')
            (target/'residual-scales.json').write_text(canonical(base.residual_scale_summary(inference,data,configuration))+'\n')
        finally:inference.close()
        if any(digest(p)!=code[p.name] for p in paths):raise ValueError('Implementation changed during disk experiment')
        if not REQUIRED_FIT|{'storage.json','trace-manifest.json','reporting-cache.json',cache_code.name} <= {p.name for p in target.iterdir()}:
            raise ValueError('Required disk inference products missing')
        disk.execution.verify_products(protocol,json.loads((target/'storage.json').read_text()),
            json.loads((target/'trace-manifest.json').read_text()),digest(target/'posterior.nc'))
        base.v2.sampler.publish_fit(target,version=VERSION,protocol_hash=ph)
        base.v2.sampler.write_status(root/'progress.json','complete',status=result['status'])
        base.v2.base.emit('complete',status=result['status'],output=str(target))
        return result


def argument_parser():
    parser = previous.argument_parser()
    parser.description = __doc__
    parser.set_defaults(draws=6000, tune=4000, seed=20260924)
    parser.add_argument('--interaction-mode', choices=feature.MODES, default='pooled')
    parser.add_argument('--interaction-prior-scale', type=float, default=.15)
    disk.execution.add_arguments(parser)
    return parser


if __name__ == '__main__':
    args = argument_parser().parse_args()
    with threadpool_limits(limits=1, user_api='blas'):
        run(args)
