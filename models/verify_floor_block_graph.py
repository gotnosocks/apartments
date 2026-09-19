"""Full-cohort log-density/gradient parity, with compilation and warm timing separated."""
import hashlib
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import time
import tempfile
import ctypes
import nutpie

import numpy as np
from models import bayesian_feature_model as reference, bayesian_floor_block_graph as compressed, bayesian_floor_increment_design as feature
from models import bayesian_feature_experiment_v3 as runner
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dataset', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--design', type=Path, required=True, help='Frozen fit directory containing saved design')
parser.add_argument('--interaction', action='store_true')
args = parser.parse_args()
source = args.dataset
data, source_manifest = runner.load_data(source)
protocol = {'source_manifest_sha256':digest(source/'complete.json'),
            'source_observations_sha256':source_manifest['files']['observations.jsonl'],
            'specification':'full_half_balance','prior_multiplier':1.}
paths = [p for p in runner.implementation_paths()
         if 'experiment' not in p.name and p.name != 'bayesian_sampling.py'] + [Path(feature.__file__)]
if args.interaction:
    from models import bayesian_floor_elevator_design as interaction
    design = interaction.FeatureDesign.load(args.design)
    paths.append(Path(interaction.__file__))
else:
    design = feature.FeatureDesign.load(args.design)
paths.extend([Path(compressed.__file__), Path(__file__)])
hashes = {str(p): digest(p) for p in paths}
design_hashes = {p.name:digest(p) for p in args.design.glob('*design.json')}
base_design = design.base if args.interaction else design
# A proof for stale saved centering/support is not a proof for the runner's design.
fresh = (interaction.FeatureDesign(data, design.spec, mode=design.mode,
         interaction_prior_scale=design.interaction_prior_scale,
         floor_increment_prior_scale=base_design.floor_increment_prior_scale)
         if args.interaction else feature.FeatureDesign(data, design.spec,
         floor_increment_prior_scale=base_design.floor_increment_prior_scale))
with tempfile.TemporaryDirectory(prefix='floor-block-design-') as temporary:
    fresh.save(Path(temporary))
    for name in design_hashes:
        assert json.loads((Path(temporary)/name).read_text()) == json.loads((args.design/name).read_text()), name
np.testing.assert_array_equal(fresh.matrix(data), design.matrix(data))
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
# Exercise the exact C callback supplied to nutpie's sampler, including its
# gradient output copy and finite checks. This is not a NUTS throughput benchmark.
from models import bayesian_feature_graph_v3 as current_graph
joint_models = {'current': current_graph.build_model(data, design), 'blocks': new}
compiled = {}
joint_timings = {}
for name, model in joint_models.items():
    print(canonical({'phase':'compiling_nutpie_joint','graph':name}), flush=True)
    started = time.perf_counter()
    compiled[name] = nutpie.compile_pymc_model(model, backend='numba')
    joint_timings[name] = {'compile_seconds':time.perf_counter()-started}
# PyMC's value-variable order is unchanged; its initial point keys have that order.
flat_points = [np.ascontiguousarray(np.concatenate([np.asarray(p[v.name]).reshape(-1)
               for v in old.value_vars]), dtype=np.float64) for p in points]
buffers = {name:(np.empty(model.n_dim), np.empty(1)) for name,model in compiled.items()}
def invoke(name, point):
    model = compiled[name]
    gradient, logp = buffers[name]
    pointer = ctypes.POINTER(ctypes.c_double)
    code = model.compiled_logp_func.ctypes(model.n_dim, point.ctypes.data_as(pointer),
        gradient.ctypes.data_as(pointer), logp.ctypes.data_as(pointer),
        ctypes.c_void_p(model.user_data.ctypes.data))
    if code != 0:
        raise ValueError(f'Nutpie joint callback failed: {code}')
    return float(logp[0]), gradient.copy()
for point in flat_points:
    left, right = invoke('current', point), invoke('blocks', point)
    np.testing.assert_allclose(left[0],right[0],rtol=1e-11,atol=1e-6)
    np.testing.assert_allclose(left[1],right[1],rtol=1e-10,atol=1e-7)
# Alternate graph order over 12 batches at each of 3 points; each batch has 100
# calls. Warmups excluded. Timings include the same small Python invocation cost.
joint_batches = {name:[] for name in compiled}
for point in flat_points:
    for _ in range(10):
        for name in compiled: invoke(name, point)
    for repeat in range(12):
        for name in (('current','blocks') if repeat%2 == 0 else ('blocks','current')):
            started = time.perf_counter()
            for _ in range(100): invoke(name, point)
            joint_batches[name].append((time.perf_counter()-started)/100)
for name, values in joint_batches.items():
    joint_timings[name].update(warm_median_seconds=float(np.median(values)),
        warm_batch_mean_seconds=values, measured_calls=3600, warmup_calls=30)
joint_timings['current_over_blocks_median_ratio'] = (joint_timings['current']['warm_median_seconds']
                                                      /joint_timings['blocks']['warm_median_seconds'])

assert all(digest(p)==hashes[str(p)] for p in paths)
assert all(digest(args.design/name)==sha for name,sha in design_hashes.items())
assert digest(source/'complete.json') == protocol['source_manifest_sha256']
result={'version':'bayesian-floor-block-graph-parity-v1','rows':len(data),
 'buildings':int(data.building.nunique()),'units':int(data.unit_id.nunique()),'specification':design.spec,
 'nutpie_joint_callback':joint_timings,'graph_configuration':new.graph_configuration,'feature_columns':len(design.features),'points':results,'timings':timings,'compression':new.compression_summary,
 'criterion':{'logp_rtol':1e-11,'logp_atol':1e-6,'gradient_rtol':1e-10,'gradient_atol':1e-7},
 'passed':True,'mode':'NUMBA','seed':20260918,
 'timing_notes':'Compilation setup and first invocation (including possible JIT) recorded separately; steady-state medians use nine evaluations per target/graph across three identical points. One BLAS thread. Other live workload may affect wall times. No sampling performed.',
 'environment':{k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','PYTENSOR_FLAGS')},
 'versions':{p:importlib.metadata.version(p) for p in ('pymc','pytensor','numba','numpy','scipy')},
 'hashes':hashes,'source_manifest_sha256':protocol['source_manifest_sha256'],
 'source_observations_sha256':protocol['source_observations_sha256'],'floor_increment_prior_scale':base_design.floor_increment_prior_scale,'floor_levels':base_design.floor_levels,'design_sha256':design_hashes,'implementation_sha256':{p.name:digest(p) for p in paths}}
if args.interaction:
    result.update(interaction_mode=design.mode, interaction_prior_scale=design.interaction_prior_scale,
                  interaction_thresholds=list(interaction.THRESHOLDS))
result['fresh_design_matches_saved'] = True
lines=['# Full-cohort Bayesian graph parity','',
 f"Verified {len(data):,} rows, {data.unit_id.nunique():,} units and {data.building.nunique():,} buildings using the supplied frozen saved training design.",'',
 f"Exact independent block compression: {new.compression_summary['blocks']}. No observations, targets or priors changed.",'',
 '| Point | Absolute log-density difference | Maximum absolute gradient difference |', '| --- | ---: | ---: |']
for r in results:lines.append(f"| {r['point']} | {r['absolute_log_density_difference']:.10g} | {r['maximum_absolute_gradient_difference']:.10g} |")
lines+=['','| Graph | Logp warm median (ms) | Gradient warm median (ms) |','| --- | ---: | ---: |']
for name,t in timings.items():lines.append(f"| {name} | {1000*t['logp_warm_median_seconds']:.4f} | {1000*t['dlogp_warm_median_seconds']:.4f} |")
lines+=['', 'Nutpie joint callback timing (C callback; not sampling):', canonical(joint_timings), '',result['timing_notes'],'','Full timings, criterion, parameter-point hashes, source/design/code hashes and dependency versions are in `parity.json`. These checks establish numerical equivalence at tested points, not sampler convergence or coefficient validity.','']
output=args.output
publish_bundle(output,{'parity.json':canonical(result)+'\n','report.md':'\n'.join(lines),
 'verify_floor_block_graph.py':Path(__file__).read_text(),
 'bayesian_floor_block_graph.py':Path(compressed.__file__).read_text()},
 {'version':result['version'],'source_manifest_sha256':protocol['source_manifest_sha256'],
 'source_observations_sha256':protocol['source_observations_sha256'],'design_and_code_hashes':hashes,
 'implementation_sha256':digest(__file__)})
print(canonical({'phase':'complete','output':str(output),'points':results,'timings':timings}),flush=True)
