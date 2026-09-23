"""Short JAX NUTS trial of the exact spline model with many vectorized chains.

Records wall time, leapfrog steps per iteration and the repository's standard convergence
diagnostics (R-hat, bulk/tail ESS, divergences, BFMI) for one sampler, chain count and
precision. A short trial measures cost per effective draw; it is not an inference run and
writes no posterior. Compare against nutpie CPU runs at the same retained draw count.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from models import sampler_hardware_probe as probe

MAX_TREE_DEPTH = 10


def run(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    import jax
    from pymc.sampling.jax import sample_jax_nuts  # enables x64; precision is set afterwards
    jax.config.update('jax_enable_x64', args.precision == 64)
    from models.bayesian_rent_model import diagnostics

    record = {'version': 'jax-spline-sampling-trial-v1', 'hardware': probe.hardware(),
              'devices': [str(d) for d in jax.devices()], 'settings': vars(args) | {'output': None}}
    started = time.perf_counter()
    model = probe.build(args.dataset)
    record['build_seconds'] = time.perf_counter() - started
    started = time.perf_counter()
    try:
        if args.sampler.startswith('nutpie'):
            # PyMC developers' June 2026 GPU recommendation; chains run as separate threads.
            import nutpie
            compiled = nutpie.compile_pymc_model(model, backend='jax',
                                                 gradient_backend=args.sampler.split('-')[-1])
            record['compile_seconds'] = time.perf_counter() - started
            inference = nutpie.sample(compiled, draws=args.draws, tune=args.tune, chains=args.chains,
                cores=args.chains, seed=args.seed, target_accept=args.target_accept,
                progress_bar=False, store_unconstrained=False)
            inference.attrs['sampling_time'] = time.perf_counter() - started - record['compile_seconds']
        else:
            inference = sample_jax_nuts(draws=args.draws, tune=args.tune, chains=args.chains,
                target_accept=args.target_accept, random_seed=args.seed, model=model,
                nuts_sampler=args.sampler, progressbar=False, compute_convergence_checks=False,
                chain_method='vectorized', postprocessing_backend='cpu')
    except Exception as error:
        record['error'] = f'{type(error).__name__}: {error}'[:4000]
        (output/'trial.json').write_text(json.dumps(record, indent=2) + '\n')
        raise
    record['pymc_call_seconds'] = time.perf_counter() - started
    record['sampling_seconds'] = float(inference.attrs.get('sampling_time', np.nan))
    stats = inference['sample_stats'].to_dataset()
    steps = stats['n_steps'].values
    record['leapfrog_steps'] = {'mean': float(steps.mean()), 'median': float(np.median(steps)),
                                'max': int(steps.max()), 'per_chain_mean': steps.mean(axis=1).tolist()}
    # Vectorized chains advance in lockstep, so each iteration costs the slowest chain's tree.
    record['lockstep_steps_per_iteration'] = float(steps.max(axis=0).mean())
    if 'maxdepth_reached' not in stats:
        inference['sample_stats']['maxdepth_reached'] = stats['n_steps'] >= 2**MAX_TREE_DEPTH - 1
    started = time.perf_counter()
    record['diagnostics'] = diagnostics(inference)
    record['diagnostics_seconds'] = time.perf_counter() - started
    retained = record['sampling_seconds']*args.draws/(args.draws + args.tune)
    record['min_ess_bulk_per_total_sampling_second'] = record['diagnostics']['min_ess_bulk']/record['sampling_seconds']
    record['note'] = ('sampling_seconds covers warmup, retained draws and JIT; per-second ESS rates use it as '
                      'the denominator. retained_share_seconds is a proportional split, not a measurement.')
    record['retained_share_seconds'] = retained
    (output/'trial.json').write_text(json.dumps(record, indent=2, default=str) + '\n')
    print(json.dumps({k: v for k, v in record.items() if k != 'diagnostics'}
                     | {'diagnostics': {k: v for k, v in record['diagnostics'].items() if k != 'worst_rhat'}},
                     indent=2, default=str))


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--sampler', choices=('numpyro', 'blackjax', 'nutpie-pytensor', 'nutpie-jax'),
                        default='numpyro', help='nutpie-* use the JAX backend with that gradient backend')
    parser.add_argument('--chains', type=int, default=16)
    parser.add_argument('--tune', type=int, default=1000)
    parser.add_argument('--draws', type=int, default=1000)
    parser.add_argument('--target-accept', type=float, default=.93)
    parser.add_argument('--precision', type=int, choices=(32, 64), default=64)
    parser.add_argument('--seed', type=int, default=20260924)
    return parser


if __name__ == '__main__':
    run(argument_parser().parse_args())
