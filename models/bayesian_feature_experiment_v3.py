"""Frozen feature experiments with explicit noise and building/unit prior settings.

The source cohort, Student-t degrees of freedom and mean design are unchanged.
Residual-scale and group-prior experiments require their own immutable protocol.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

from . import bayesian_feature_experiment_v2 as v2
from . import bayesian_feature_graph_v3 as graph
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from apartments import reviewed_source_lineage

VERSION = 'observable-bayesian-bathroom-experiment-v3'
DATASET_VERSIONS = v2.DATASET_VERSIONS | {'reviewed-scope-composition-projection-v2',
                                       'reviewed-capture-refreshed-analysis-v1'} | reviewed_source_lineage.VERSIONS
REQUIRED_FIT = {'summary.json','diagnostics.json','derived-diagnostics.json',
    'parameter-diagnostics.csv','derived-diagnostics.csv','bathroom-contrasts.json',
    'residuals.jsonl','coefficients.json','group-effects.jsonl','feature-design.json',
    'time-design.json','time-design.npz','posterior.nc','prior.nc',
    'posterior-checkpoint.json','compression.json','graph-configuration.json','residual-scales.json'}


def load_data(dataset):
    """Preserve cohort checks for reviewed scope and reviewed current refreshes."""
    sidecar = reviewed_source_lineage.reviewed_cohort_quarantine.SIDECAR
    elevator_sidecar = reviewed_source_lineage.elevator_corrections.SIDECAR
    floor_label_sidecar = reviewed_source_lineage.floor_label_projection.SIDECAR
    expanded_floor_sidecar = reviewed_source_lineage.expanded_floor_projection.SIDECAR
    direct_floor_sidecar = reviewed_source_lineage.direct_floor_projection.SIDECAR
    residual_scope_sidecar = reviewed_source_lineage.residual_scope_projection.SIDECAR
    manifest,files = _verified_bundle(dataset,retain={'observations.jsonl', sidecar, elevator_sidecar, floor_label_sidecar, expanded_floor_sidecar, residual_scope_sidecar, direct_floor_sidecar})
    if manifest.get('version') not in DATASET_VERSIONS:
        raise ValueError('Verified bathroom or reviewed scope/composition projection required')
    rows = [json.loads(line) for line in files['observations.jsonl'].decode().split('\n') if line.strip()]
    if manifest['version'] in reviewed_source_lineage.VERSIONS:
        reviewed_source_lineage.source_lineage(manifest, rows,
            quarantined=[json.loads(s) for s in files[sidecar].decode().split('\n') if s.strip()]
            if sidecar in files else None,
            elevator_changes=[json.loads(s) for s in files[elevator_sidecar].decode().split('\n') if s.strip()]
            if elevator_sidecar in files else None,
            floor_label_changes=[json.loads(s) for s in files[floor_label_sidecar].decode().split('\n') if s.strip()]
            if floor_label_sidecar in files else None,
            expanded_floor_changes=[json.loads(s) for s in files[expanded_floor_sidecar].decode().split('\n') if s.strip()]
            if expanded_floor_sidecar in files else None,
            residual_scope_changes=[json.loads(s) for s in files[residual_scope_sidecar].decode().split('\n') if s.strip()]
            if residual_scope_sidecar in files else None,
            direct_floor_changes=[json.loads(s) for s in files[direct_floor_sidecar].decode().split('\n') if s.strip()]
            if direct_floor_sidecar in files else None)
    data = v2.pd.DataFrame(rows)
    data.period = v2.pd.to_datetime(data.period)
    data.square_feet = v2.pd.to_numeric(data.square_feet,errors='coerce')
    if (data.audit_id.duplicated().any() or data.duplicated(['unit_id','period']).any()
            or not v2.np.isfinite(data.asking_rent).all() or not data.asking_rent.gt(0).all()):
        raise ValueError('Invalid source cohort')
    return data,manifest


def validate_args(args):
    for name,minimum in [('draws',1),('tune',1),('chains',2),('seed',0)]:
        if type(getattr(args,name)) is not int or getattr(args,name) < minimum:
            raise ValueError(f'{name} must be an integer >= {minimum}')
    for name in ('prior_multiplier','building_prior_scale','unit_prior_scale','target_accept'):
        value = getattr(args,name)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and positive')
    if args.target_accept >= 1:
        raise ValueError('target_accept must be below 1')
    if getattr(args,'residual_parameterization','centered') not in graph.RESIDUAL_PARAMETERIZATIONS:
        raise ValueError('Unknown residual hierarchy parameterization')
    if args.residual_scale not in ('shared','bedroom') or args.adaptation not in ('diag','low_rank'):
        raise ValueError('Unknown residual scale or sampler adaptation')
    if args.spec not in v2.feature.SPECS:
        raise ValueError('Unknown feature specification')


def implementation_paths():
    """Archive local transitive mean-design, graph, sampler and reporting code."""
    modules = (v2,graph,v2.graph,v2.feature,v2.sampler,v2.reports,v2.base,
               v2.feature.amenity,v2.feature.amenity.baseline,v2.feature.pricing,
               v2.corrections,v2.research_pipeline,reviewed_source_lineage,
               reviewed_source_lineage.laundry_floor_split, reviewed_source_lineage.reviewed_cohort_quarantine,
               reviewed_source_lineage.elevator_corrections, reviewed_source_lineage.floor_label_projection,
               reviewed_source_lineage.expanded_floor_projection, reviewed_source_lineage.residual_scope_projection,
               reviewed_source_lineage.direct_floor_projection)
    paths = [Path(m.__file__) for m in modules]+[Path(__file__)]
    if len({p.name for p in paths}) != len(paths):
        raise ValueError('Implementation archive names must be unique')
    return paths


def graph_kwargs(args):
    return {'residual_scale':args.residual_scale,'building_prior_scale':args.building_prior_scale,
            'unit_prior_scale':args.unit_prior_scale,
            'residual_parameterization':getattr(args,'residual_parameterization','centered')}


def graph_verification(path, code):
    if not path:
        return None
    manifest,files = _verified_bundle(path,retain={'parity.json'})
    parity = json.loads(files['parity.json'])
    validated = {Path(name).name:value for name,value in parity['hashes'].items()}
    if (parity.get('passed') is not True or validated.get(Path(graph.__file__).name) != code[Path(graph.__file__).name]
            or any(code[name] != value for name,value in validated.items() if name in code)):
        raise ValueError('Graph verification does not match the v3 implementation')
    return {'manifest_sha256':digest(Path(path)/'complete.json'),'version':manifest['version'],
            'rows':parity['rows'],'source_observations_sha256':parity['source_observations_sha256']}


def make_protocol(args,data,source,code,configuration):
    return {'version':VERSION,'source_manifest_sha256':digest(Path(args.dataset)/'complete.json'),
        'source_observations_sha256':source['files']['observations.jsonl'],
        'source_version':source['version'],'source_directory':str(Path(args.dataset).resolve()),
        'rows':len(data),'units':int(data.unit_id.nunique()),'buildings':int(data.building.nunique()),
        'current_rows':int(data.analysis_price_basis.eq('current_capture_gross_ask').sum()),
        'specification':args.spec,
        **{name:getattr(args,name) for name in ('draws','tune','chains','seed','target_accept',
            'adaptation','prior_multiplier','residual_scale','building_prior_scale','unit_prior_scale')},
        'residual_parameterization':getattr(args,'residual_parameterization','centered'),
        'graph_configuration':configuration,'implementation_sha256':code,
        'graph_verification':graph_verification(getattr(args,'graph_validation',None),code),
        'versions':{p:importlib.metadata.version(p) for p in
                    ('pymc','nutpie','pytensor','numba','arviz','numpy','pandas','scipy','h5netcdf')},
        'purpose':'Current-cohort descriptive coefficients and residuals, including all accepted current captures.',
        'likelihood':'Student-t(log gross asking rent), fixed nu=5; residual scale and group priors recorded explicitly.',
        'graph':'Lossless repeated-feature compression; unchanged mean design; one likelihood term per observation.',
        'bathroom_policy':'Explicit complete integer counts, at least one full bath, agreeing scalar, no unresolved review flags; preserve unknown rows with a reporting indicator.',
        'uncertainty':'Conditional on source measurements, cohort, likelihood and priors; not causal or protection against omitted features.'}


def validate_posterior(inference,args,design,configuration):
    posterior = v2.base.posterior_dataset(inference)
    if posterior.sizes.get('chain') != args.chains or posterior.sizes.get('draw') != args.draws:
        raise ValueError('Incomplete posterior checkpoint')
    required = {'alpha','beta','trend_coefficients','annual_drift','season_coefficients',
                'building_effect','sigma_building','sigma_unit','unit_z','sigma','trend_scale','season_scale'}
    if args.residual_scale == 'bedroom':
        required |= {'residual_bedroom_z','residual_bedroom_scale','sigma_by_bedroom'}
        if configuration.get('residual_bedroom_parameterization') == 'centered':
            required.add('residual_bedroom_offset')
        elif 'residual_bedroom_offset' in posterior:
            raise ValueError('Noncentered checkpoint contains a centered offset variable')
    elif {'residual_bedroom_z','residual_bedroom_scale','sigma_by_bedroom','residual_bedroom_offset'} & set(posterior.data_vars):
        raise ValueError('Shared-noise checkpoint contains bedroom-noise variables')
    if not required <= set(posterior.data_vars):
        raise ValueError('Posterior is missing required graph variables')
    dimensions = {name:('chain','draw') for name in required}
    dimensions.update(beta=('chain','draw','feature'),building_effect=('chain','draw','building'),
                      unit_z=('chain','draw','unit'),trend_coefficients=('chain','draw','trend_basis'),
                      season_coefficients=('chain','draw','season_basis'))
    if args.residual_scale == 'bedroom':
        dimensions.update(residual_bedroom_z=('chain','draw','residual_bedroom'),
                          sigma_by_bedroom=('chain','draw','residual_bedroom'))
        if configuration.get('residual_bedroom_parameterization') == 'centered':
            dimensions['residual_bedroom_offset']=('chain','draw','residual_bedroom')
    if any(posterior[name].dims != dims for name,dims in dimensions.items()):
        raise ValueError('Posterior graph-variable dimensions differ from the protocol')
    # Reconstruction uses posterior columns positionally against these saved
    # bases, so matching dimension names alone does not preserve their meaning.
    coordinates = {'feature':design.features,'building':design.time.buildings,'unit':design.time.unit_ids,
                   'trend_basis':range(design.time.time_matrix.shape[1]),'season_basis':range(11)}
    if args.residual_scale == 'bedroom':
        coordinates['residual_bedroom'] = configuration['residual_bedroom_levels']
    for name,expected in coordinates.items():
        if name not in posterior.coords or posterior.coords[name].values.tolist() != list(expected):
            raise ValueError(f'Posterior coordinate mismatch: {name}')


def completed_fit(target,protocol_hash,configuration):
    manifest,files = _verified_bundle(target,retain={'summary.json','graph-configuration.json','posterior-checkpoint.json'})
    if (manifest.get('version') != VERSION or manifest.get('protocol_sha256') != protocol_hash
            or not REQUIRED_FIT <= manifest['files'].keys()):
        raise ValueError('Completed fit protocol/version or required products mismatch')
    summary = json.loads(files['summary.json'])
    if (summary.get('protocol_sha256') != protocol_hash
            or json.loads(files['graph-configuration.json']) != configuration
            or json.loads(files['posterior-checkpoint.json']) != {
                'protocol_sha256':protocol_hash,'posterior_sha256':manifest['files']['posterior.nc']}):
        raise ValueError('Completed fit graph or checkpoint identity mismatch')
    return summary


def residual_scale_summary(inference,data,configuration):
    posterior = v2.base.posterior_dataset(inference)
    by_bedroom = []
    if configuration['residual_scale'] == 'bedroom':
        for level,expected_count in zip(configuration['residual_bedroom_levels'],
                                         configuration['residual_bedroom_counts'],strict=True):
            rows = data.loc[data.bedrooms.eq(level)]
            if len(rows) != expected_count:
                raise ValueError('Residual bedroom support differs from graph configuration')
            scale = posterior['sigma_by_bedroom'].sel(residual_bedroom=level)
            by_bedroom.append({'bedrooms':level,'sigma':v2.reports.interval(scale.values.ravel()),
                'support':{'rows':len(rows),'units':int(rows.unit_id.nunique()),'buildings':int(rows.building.nunique())}})
    return {'version':'bayesian-residual-scale-summary-v1','graph_configuration':configuration,
            'student_t_nu':5.,'scale_units':'Log advertised asking rent; Student-t scale, not its standard deviation.',
            'global_sigma':v2.reports.interval(posterior['sigma'].values.ravel()),
            'global_sigma_role':'Shared observation scale' if not by_bedroom else 'Geometric mean of bedroom-level scales (equal level weights)',
            'by_bedroom':by_bedroom,
            'interpretation':'Separate conditional 95% posterior intervals. Residual variation is not latent conditional-median uncertainty. Student-t standard deviation equals scale * sqrt(5/3); no mean or feature contribution changed by this summary.'}


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
        design = v2.feature.FeatureDesign(data,args.spec)
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--spec',choices=v2.feature.SPECS,default='full_half_balance')
    parser.add_argument('--draws',type=int,default=1000)
    parser.add_argument('--tune',type=int,default=1000)
    parser.add_argument('--chains',type=int,default=4)
    parser.add_argument('--seed',type=int,default=20260918)
    parser.add_argument('--target-accept',type=float,default=.93)
    parser.add_argument('--adaptation',choices=('diag','low_rank'),default='diag')
    parser.add_argument('--prior-multiplier',type=float,default=1.)
    parser.add_argument('--residual-scale',choices=('shared','bedroom'),default='shared')
    parser.add_argument('--building-prior-scale',type=float,default=.35)
    parser.add_argument('--unit-prior-scale',type=float,default=.25)
    parser.add_argument('--residual-parameterization',choices=graph.RESIDUAL_PARAMETERIZATIONS,default='centered')
    parser.add_argument('--graph-validation',type=Path)
    return parser


if __name__ == '__main__':
    parser = argument_parser()
    args = parser.parse_args()
    try:
        validate_args(args)
    except ValueError as error:
        parser.error(str(error))
    run(args)
