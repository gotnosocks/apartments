"""Verify JAX GPU and Numba CPU evaluate the same full PyMC posterior.

Kernel timings are compatibility evidence, not a sampling-speed benchmark.
"""
import argparse
import importlib.metadata
import os
from pathlib import Path
import time

import numpy as np

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import bayesian_feature_experiment_v3 as runner
from models import bayesian_floor_increment_design as floor


def run(dataset, output):
    import jax
    from pymc.sampling.jax import get_jaxified_logp

    if not jax.config.x64_enabled:
        raise ValueError('Float64 is required')
    device = jax.devices('gpu')[0]
    data, source = runner.load_data(dataset)
    design = floor.FeatureDesign(data, 'full_half_balance', floor_increment_prior_scale=.15)
    model = runner.graph.build_model(data, design, 1., residual_scale='shared',
        building_prior_scale=.35, unit_prior_scale=.25, residual_parameterization='centered')
    paths = [*runner.implementation_paths(), Path(floor.__file__), Path(__file__)]
    code = {p.name: digest(p) for p in paths}
    initial = model.initial_point()
    order = [v.name for v in model.value_vars]
    assert set(order) == set(initial)
    rng = np.random.default_rng(20260925)
    points = [initial, *[{k: np.asarray(v)+rng.normal(0, scale, np.shape(v))
                         for k, v in initial.items()} for scale in (.025, .1)]]
    print('Compiling CPU reference log density and gradient', flush=True)
    start = time.perf_counter()
    logp = model.compile_logp(mode='NUMBA'); gradient = model.compile_dlogp(mode='NUMBA')
    logp(initial); gradient(initial)
    cpu_compile = time.perf_counter()-start
    print('Compiling GPU JAX log density and autodiff gradient', flush=True)
    start = time.perf_counter()
    with jax.default_device(device):
        function = jax.jit(jax.value_and_grad(get_jaxified_logp(model, negative_logp=True)))
        gpu_points = [[jax.device_put(p[k], device) for k in order] for p in points]
        jax.block_until_ready(function(gpu_points[0]))
    gpu_compile = time.perf_counter()-start
    results, timings = [], {'cpu': [], 'gpu': []}
    for index, (point, gpu_point) in enumerate(zip(points, gpu_points)):
        cpu_value, cpu_gradient = logp(point), gradient(point)
        value, grads = jax.block_until_ready(function(gpu_point))
        gpu_gradient = np.concatenate([np.asarray(g).ravel() for g in grads])
        assert value.dtype == np.float64 and gpu_gradient.dtype == np.float64
        assert np.isfinite(cpu_value) and np.isfinite(value) and np.isfinite(gpu_gradient).all()
        np.testing.assert_allclose(cpu_value, value, rtol=1e-11, atol=1e-6)
        np.testing.assert_allclose(cpu_gradient, gpu_gradient, rtol=1e-9, atol=1e-7)
        results.append({'point': index, 'log_density_absolute_difference': float(abs(cpu_value-value)),
            'gradient_maximum_absolute_difference': float(np.max(np.abs(cpu_gradient-gpu_gradient))),
            'gradient_parameters': int(gpu_gradient.size)})
        for repeat in range(10):
            for backend in (('cpu', 'gpu') if repeat % 2 else ('gpu', 'cpu')):
                start = time.perf_counter()
                if backend == 'cpu': logp(point); gradient(point)
                else: jax.block_until_ready(function(gpu_point))
                timings[backend].append(time.perf_counter()-start)
    assert all(digest(p) == code[p.name] for p in paths)
    result = {'version': 'full-model-sampler-backend-preflight-v1', 'passed': True,
        'rows': len(data), 'units': int(data.unit_id.nunique()), 'buildings': int(data.building.nunique()),
        'source_manifest_sha256': digest(Path(dataset)/'complete.json'),
        'source_observations_sha256': source['files']['observations.jsonl'],
        'graph_configuration': model.graph_configuration, 'feature_names': design.features,
        'feature_prior_scales': design.prior_scales.tolist(), 'value_variable_order': order,
        'device': str(device), 'device_kind': device.device_kind, 'float64': True,
        'checks': results, 'compile_and_first_call_seconds': {'cpu': cpu_compile, 'gpu': gpu_compile},
        'kernel_wall_seconds': timings,
        'kernel_median_seconds': {k: float(np.median(v)) for k, v in timings.items()},
        'timing_scope': 'CPU separately evaluates log density and gradient; JAX evaluates fused value-and-gradient with device-resident inputs and explicit synchronization. These are kernel diagnostics, not matched sampling speed, ESS/sec, or evidence of a fastest sampler.',
        'versions': {p: importlib.metadata.version(p) for p in
            ('pymc', 'nutpie', 'pytensor', 'numpy', 'jax', 'jaxlib', 'numpyro', 'blackjax')},
        'environment': {k: os.environ.get(k) for k in
            ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'JAX_ENABLE_X64', 'JAX_PLATFORMS', 'PYTENSOR_FLAGS')},
        'implementation_sha256': code}
    publish_bundle(output, {'preflight.json': canonical(result)+'\n',
        **{p.name: p.read_text() for p in paths}}, {'version': result['version'], 'passed': True})
    print(canonical(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    run(**vars(parser.parse_args()))
