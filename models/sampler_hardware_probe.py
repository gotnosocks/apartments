"""Measure the current spline model's log-density gradient cost across hardware choices.

For one model built exactly as ``bayesian_floor_spline_experiment`` builds it, record:
Numba CPU seconds per logp+gradient with 1..N concurrent chain processes (memory and
core contention), and JAX seconds per vectorized batch of K chains on the available
device in float64 and float32, plus float32 error against float64 at fixed points.

Kernel costs predict sampler wall time only through leapfrog steps per iteration, which
this probe does not measure; it is hardware-selection evidence, not an ESS benchmark.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from models import bayesian_floor_spline_experiment as spline
from models import bayesian_floor_spline_design as floor

SEED = 20260923


def build(dataset):
    args = spline.argument_parser().parse_args(['--dataset', str(dataset), '--output', '/dev/null'])
    data, _ = spline.load_data(dataset)
    design = floor.FeatureDesign(data, args.spec, floor_prior_scale=args.floor_prior_scale)
    return spline.graph.build_model(data, design, args.prior_multiplier, **spline.graph_kwargs(args))


def points(model, count=3):
    from pymc.blocking import DictToArrayBijection
    initial = model.initial_point()
    names = [v.name for v in model.value_vars]
    rng = np.random.default_rng(SEED)
    result = []
    for scale in (0, .025, .1)[:count]:
        point = {k: np.asarray(initial[k]) + rng.normal(0, scale, np.shape(initial[k])) for k in names}
        result.append(DictToArrayBijection.map(point).data)
    return np.asarray(result)


def timed(call, minimum_seconds):
    call()
    calls, started = 0, time.perf_counter()
    while (elapsed := time.perf_counter() - started) < minimum_seconds:
        call()
        calls += 1
    return elapsed/calls


def numba_worker(function, x, seconds, queue):
    count, started = 0, time.perf_counter()
    while time.perf_counter() - started < seconds:
        function(x)
        count += 1
    queue.put(count)


def numba_probe(model, x, processes, seconds):
    started = time.perf_counter()
    function = model.logp_dlogp_function(ravel_inputs=True, mode='NUMBA')
    function.set_extra_values({})
    function(x[0])
    compile_seconds = time.perf_counter() - started
    single = timed(lambda: function(x[0]), seconds)
    reference = [function(point) for point in x]
    context = multiprocessing.get_context('fork')
    scaling = []
    for count in processes:
        queue = context.Queue()
        workers = [context.Process(target=numba_worker, args=(function, x[0], seconds, queue)) for _ in range(count)]
        for worker in workers:
            worker.start()
        totals = [queue.get() for _ in workers]
        for worker in workers:
            worker.join()
        per_chain = seconds/np.mean(totals)
        scaling.append({'processes': count, 'seconds_per_gradient_per_chain': per_chain,
                        'aggregate_gradients_per_second': sum(totals)/seconds,
                        'slowdown_vs_single': per_chain/single})
        print(json.dumps(scaling[-1]), flush=True)
    return {'compile_seconds': compile_seconds, 'seconds_per_gradient': single, 'scaling': scaling}, reference


def jax_probe(dataset, batches, seconds, output):
    """Runs in a subprocess so JAX_ENABLE_X64 fixes the precision for the whole graph."""
    import jax
    import jax.numpy as jnp
    from jax.flatten_util import ravel_pytree
    from pymc.sampling.jax import get_jaxified_logp
    # Importing PyMC's JAX module enables x64; restore the precision this child was asked for.
    jax.config.update('jax_enable_x64', os.environ.get('JAX_ENABLE_X64') == '1')
    model = build(dataset)
    x = points(model)
    initial = model.initial_point()
    template = [np.asarray(initial[v.name]) for v in model.value_vars]
    _, unravel = ravel_pytree([jnp.asarray(t) for t in template])
    logp = get_jaxified_logp(model)  # PyMC's flag is inverted: the default returns +logp
    dtype = jnp.float64 if jax.config.x64_enabled else jnp.float32
    value_grad = jax.value_and_grad(lambda flat: logp(unravel(flat)))
    started = time.perf_counter()
    single = jax.jit(value_grad)
    values = [single(jnp.asarray(point, dtype)) for point in x]
    jax.block_until_ready(values)
    compile_seconds = time.perf_counter() - started
    results = []
    batched = jax.jit(jax.vmap(value_grad))
    for size in batches:
        state = jnp.asarray(np.resize(x, (size, x.shape[1])), dtype)
        try:
            call = lambda: jax.block_until_ready(batched(state))
            per_call = timed(call, seconds)
        except Exception as error:  # device memory exhaustion ends the sweep
            results.append({'chains': size, 'error': type(error).__name__})
            print(json.dumps(results[-1]), flush=True)
            break
        results.append({'chains': size, 'seconds_per_batch': per_call,
                        'seconds_per_gradient_per_chain': per_call/size})
        print(json.dumps(results[-1]), flush=True)
    np.savez(output, logp=np.asarray([v[0] for v in values], np.float64),
             grad=np.asarray([v[1] for v in values], np.float64))
    return {'x64': bool(jax.config.x64_enabled), 'devices': [str(d) for d in jax.devices()],
            'logp_at_points': [float(v[0]) for v in values],
            'backend': jax.default_backend(), 'compile_seconds': compile_seconds, 'batches': results}


def errors(reference_logp, reference_grad, path):
    other = np.load(path)
    grad_scale = np.maximum(np.abs(reference_grad), 1.)
    return {'max_abs_logp_error': float(np.max(np.abs(other['logp'] - reference_logp))),
            'max_relative_logp_error': float(np.max(np.abs(other['logp'] - reference_logp)/np.abs(reference_logp))),
            'max_scaled_gradient_error': float(np.max(np.abs(other['grad'] - reference_grad)/grad_scale))}


def hardware():
    info = {'cpu_count': os.cpu_count(), 'platform': platform.platform(), 'cpu': platform.processor()}
    try:
        info['cpu'] = next(line.split(':', 1)[1].strip() for line in open('/proc/cpuinfo') if line.startswith('model name'))
    except (OSError, StopIteration):
        pass
    try:
        info['gpu'] = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
                                     capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        info['gpu'] = None
    return info


def run(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    result = {'version': 'spline-gradient-hardware-probe-v1', 'hardware': hardware(),
              'dataset': str(Path(args.dataset).resolve())}
    model = build(args.dataset)
    x = points(model)
    result['parameters'] = int(x.shape[1])
    reference = None
    if args.processes:
        result['numba'], values = numba_probe(model, x, args.processes, args.seconds)
        reference = (np.asarray([v[0] for v in values]), np.asarray([v[1] for v in values]))
        result['numba']['logp_at_points'] = reference[0].tolist()
    del model
    for precision in args.jax_precisions:
        path = output/f'jax{precision}.npz'
        env = {**os.environ, 'JAX_ENABLE_X64': '1' if precision == 64 else '0'}
        command = [sys.executable, '-m', 'models.sampler_hardware_probe', '--jax-child', str(path),
                   '--dataset', args.dataset, '--output', str(output), '--seconds', str(args.seconds),
                   '--batches', *map(str, args.batches)]
        completed = subprocess.run(command, env=env, capture_output=True, text=True)
        sys.stdout.write(completed.stdout)
        if completed.returncode:
            result[f'jax{precision}'] = {'error': completed.stderr[-4000:]}
            continue
        result[f'jax{precision}'] = json.loads(completed.stdout.strip().splitlines()[-1])
        if reference is not None:
            result[f'jax{precision}']['vs_numba64'] = errors(*reference, path)
    if (output/'jax64.npz').exists() and (output/'jax32.npz').exists():
        wide = np.load(output/'jax64.npz')
        result['jax32_vs_jax64'] = errors(wide['logp'], wide['grad'], output/'jax32.npz')
    (output/'probe.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--processes', type=int, nargs='*', default=[1, 2, 4],
                        help='Concurrent Numba chain processes to time; empty skips Numba')
    parser.add_argument('--jax-precisions', type=int, nargs='*', default=[], choices=(32, 64))
    parser.add_argument('--batches', type=int, nargs='*', default=[1, 4, 16, 64, 256])
    parser.add_argument('--seconds', type=float, default=15.)
    parser.add_argument('--jax-child', help=argparse.SUPPRESS)
    return parser


if __name__ == '__main__':
    arguments = argument_parser().parse_args()
    if arguments.jax_child:
        summary = jax_probe(arguments.dataset, arguments.batches, arguments.seconds, arguments.jax_child)
        print(json.dumps(summary))
    else:
        run(arguments)
