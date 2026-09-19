"""Full-cohort compiled parity for the exact lower-floor/elevator PyMC model."""
import hashlib
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import time

import numpy as np
from models import bayesian_feature_model as reference, bayesian_feature_graph_v3 as compressed
from models import bayesian_floor_elevator_experiment as experiment
feature, runner = experiment.feature, experiment.previous
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

parser = experiment.argument_parser()
parser.description = __doc__
args = parser.parse_args()
experiment.validate_args(args)
if args.graph_validation is not None:
    parser.error('This command creates a new parity proof; omit --graph-validation')
if args.residual_scale != 'shared' or args.building_prior_scale != .35 or args.unit_prior_scale != .25:
    parser.error('The independent reference graph currently supports shared noise and .35/.25 group priors only')
source = args.dataset
data, source_manifest = runner.load_data(source)
protocol = {'source_manifest_sha256':digest(source/'complete.json'),
            'source_observations_sha256':source_manifest['files']['observations.jsonl'],
            'specification':args.spec,'prior_multiplier':args.prior_multiplier}
paths = experiment.implementation_paths()
hashes = {str(p): digest(p) for p in paths}
design = feature.FeatureDesign(data, args.spec, floor_increment_prior_scale=args.floor_increment_prior_scale,
    mode=args.interaction_mode, interaction_prior_scale=args.interaction_prior_scale)
assert design.support['rows'] == len(data)
functions, models, timings = {}, {}, {}
for name, module in [('reference', reference), ('compressed', compressed)]:
    started = time.perf_counter()
    models[name] = module.build_model(data, design, protocol['prior_multiplier'])
    timings[name] = {'model_build_seconds': time.perf_counter()-started}
    functions[name] = {}
    for target in ('logp', 'dlogp'):
        print(canonical({'phase':'compiling','graph':name,'target':target}), flush=True)
        started = time.perf_counter()
        functions[name][target] = getattr(models[name], 'compile_'+target)(mode='NUMBA')
        timings[name][target+'_compile_setup_seconds'] = time.perf_counter()-started
old, new = models['reference'], models['compressed']
assert old.coords == new.coords
assert old.named_vars_to_dims == new.named_vars_to_dims
assert [rv.name for rv in old.free_RVs] == [rv.name for rv in new.free_RVs]
assert [str(rv.owner.op) for rv in old.free_RVs] == [str(rv.owner.op) for rv in new.free_RVs]
initial = old.initial_point()
assert list(initial) == list(new.initial_point())
for name, value in initial.items():
    np.testing.assert_array_equal(value, new.initial_point()[name])
rng = np.random.default_rng(20260918)
points = [initial, *[{key: np.asarray(value)+rng.normal(0, scale, np.shape(value))
                    for key,value in initial.items()} for scale in (.025,.1)]]
point_hashes = [hashlib.sha256(canonical({k:np.asarray(v).tolist() for k,v in p.items()}).encode()).hexdigest() for p in points]
# First invocation can trigger Numba JIT; it is explicitly not a steady-state evaluation timing.
for name in functions:
    for target, fn in functions[name].items():
        print(canonical({'phase':'first_invocation','graph':name,'target':target}), flush=True)
        started = time.perf_counter()
        value = fn(points[0])
        timings[name][target+'_first_invocation_seconds'] = time.perf_counter()-started
        assert np.isfinite(value).all()
results = []
warm = {name:{target:[] for target in ('logp','dlogp')} for name in functions}
for i,point in enumerate(points):
    values = {}
    for name in functions:
        values[name] = {}
        for target,fn in functions[name].items():
            value = fn(point)
            assert np.isfinite(value).all()
            values[name][target] = value
    a,b = values['reference'],values['compressed']
    np.testing.assert_allclose(a['logp'], b['logp'], rtol=1e-11, atol=1e-6)
    np.testing.assert_allclose(a['dlogp'], b['dlogp'], rtol=1e-10, atol=1e-7)
    absolute = np.abs(a['dlogp']-b['dlogp'])
    results.append({'point':i,'point_sha256':point_hashes[i],
        'reference_log_density':float(a['logp']),'compressed_log_density':float(b['logp']),
        'absolute_log_density_difference':float(abs(a['logp']-b['logp'])),
        'gradient_parameters':int(a['dlogp'].size),'maximum_absolute_gradient_difference':float(absolute.max()),
        'maximum_scaled_gradient_difference':float(np.max(absolute/np.maximum(1.,np.abs(a['dlogp'])))),
        'all_finite':True})
    # Alternate order across repeats to reduce systematic timing-order bias.
    for repeat in range(3):
        for name in (('reference','compressed') if repeat % 2 == 0 else ('compressed','reference')):
            for target,fn in functions[name].items():
                started = time.perf_counter(); value=fn(point); elapsed=time.perf_counter()-started
                assert np.isfinite(value).all()
                warm[name][target].append(elapsed)
for name in warm:
    for target, times in warm[name].items():
        timings[name][target+'_warm_median_seconds'] = float(np.median(times))
        timings[name][target+'_warm_all_seconds'] = times
assert all(digest(p)==hashes[str(p)] for p in paths)
assert digest(source/'complete.json') == protocol['source_manifest_sha256']
result={'version':experiment.PARITY_VERSION,'rows':len(data),
 'buildings':int(data.building.nunique()),'units':int(data.unit_id.nunique()),'specification':design.spec,
 'graph_configuration':new.graph_configuration,'feature_columns':len(design.features),'points':results,'timings':timings,'compression':new.compression_summary,
 'criterion':{'logp_rtol':1e-11,'logp_atol':1e-6,'gradient_rtol':1e-10,'gradient_atol':1e-7},
 'passed':True,'mode':'NUMBA','seed':20260918,
 'timing_notes':'Compilation setup and first invocation (including possible JIT) recorded separately; steady-state medians use nine evaluations per target/graph across three identical points. One BLAS thread. Other live workload may affect wall times. No sampling performed.',
 'environment':{k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','PYTENSOR_FLAGS')},
 'versions':{p:importlib.metadata.version(p) for p in ('pymc','pytensor','numba','numpy','scipy')},
 'hashes':hashes,'source_manifest_sha256':protocol['source_manifest_sha256'],
 'source_observations_sha256':protocol['source_observations_sha256'],'floor_increment_prior_scale':args.floor_increment_prior_scale,
 'interaction_mode':args.interaction_mode,'interaction_prior_scale':args.interaction_prior_scale,
 'interaction_thresholds':list(feature.THRESHOLDS),'floor_levels':design.floor_levels,'implementation_sha256':{p.name:digest(p) for p in paths}}
lines=['# Full-cohort floor/elevator graph parity','',
 f"Verified {len(data):,} rows, {data.unit_id.nunique():,} units and {data.building.nunique():,} buildings using a freshly reconstructed training design.",'',
 f"Exact feature compression: {new.compression_summary['unique_feature_rows']:,} unique feature rows. No observations, targets or priors changed.",'',
 '| Point | Absolute log-density difference | Maximum absolute gradient difference |', '| --- | ---: | ---: |']
for r in results:lines.append(f"| {r['point']} | {r['absolute_log_density_difference']:.10g} | {r['maximum_absolute_gradient_difference']:.10g} |")
lines+=['','| Graph | Logp warm median (ms) | Gradient warm median (ms) |','| --- | ---: | ---: |']
for name,t in timings.items():lines.append(f"| {name} | {1000*t['logp_warm_median_seconds']:.4f} | {1000*t['dlogp_warm_median_seconds']:.4f} |")
lines+=['',result['timing_notes'],'','Full timings, criterion, parameter-point hashes, source/design/code hashes and dependency versions are in `parity.json`. These checks establish numerical equivalence at tested points, not sampler convergence or coefficient validity.','']
output=args.output
publish_bundle(output,{'parity.json':canonical(result)+'\n','report.md':'\n'.join(lines),
 Path(__file__).name:Path(__file__).read_text()},
 {'version':result['version'],'source_manifest_sha256':protocol['source_manifest_sha256'],
 'source_observations_sha256':protocol['source_observations_sha256'],'design_and_code_hashes':hashes,
 'implementation_sha256':digest(__file__)})
print(canonical({'phase':'complete','output':str(output),'points':results,'timings':timings}),flush=True)
