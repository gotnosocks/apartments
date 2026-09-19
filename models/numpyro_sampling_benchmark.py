"""Production-length PyMC/NumPyro benchmark with separate warmup and sampling.

Uses PyMC's JAX sampler and the exact reviewed floor model, never a surrogate.
Compilation within each MCMC loop is included in that phase and reported as
such; a short smoke run is not used to rank sampling performance.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models import bayesian_feature_experiment_v3 as runner
from models import bayesian_floor_increment_design as floor


def phase(output, name, **values):
    record = {'phase': name, 'updated_at': datetime.now(timezone.utc).isoformat(), **values}
    path = Path(output)/'progress.json'
    temporary = path.with_suffix('.tmp'); temporary.write_text(canonical(record)+'\n'); temporary.replace(path)
    print(canonical(record), flush=True)


@contextmanager
def separate_phases(timings, callback, *, scratch=None, batch_draws=500):
    """Use NumPyro's public warmup/post_warmup_state lifecycle inside PyMC."""
    import jax
    import numpyro.infer
    original = numpyro.infer.MCMC
    if scratch is not None:
        scratch = Path(scratch)
        scratch.mkdir(parents=True, exist_ok=False)
    if batch_draws < 1:
        raise ValueError('Positive retained batch size required')

    class PhasedMCMC(original):
        def run(self, rng_key, *args, extra_fields=(), init_params=None, **kwargs):
            if getattr(self, '_benchmark_warmup', False):
                return super().run(rng_key, *args, extra_fields=extra_fields,
                                   init_params=init_params, **kwargs)
            callback('warmup_including_initialization_and_jit')
            start = time.perf_counter(); self._benchmark_warmup = True
            requested_draws = self.num_samples
            # NumPyro 0.22 warmup allocates num_samples slots even when
            # collect_warmup=False. A single unused slot avoids a full trace.
            self.num_samples = 1
            try:
                super().warmup(rng_key, *args, extra_fields=extra_fields,
                               init_params=init_params, collect_warmup=False, **kwargs)
                jax.block_until_ready(self.last_state)
            finally:
                self._benchmark_warmup = False
                self.num_samples = requested_draws
            timings['warmup_including_initialization_and_jit_seconds'] = time.perf_counter()-start
            callback('retained_sampling', **timings)
            sampling_seconds = spill_seconds = 0.
            retained = None
            memory_chunks = []
            for offset in range(0, requested_draws, batch_draws):
                count = min(batch_draws, requested_draws-offset)
                self.num_samples = count
                start = time.perf_counter()
                # Continue each chain's exact adapted state and RNG. No new
                # warmup, thinning, discarded draws, or approximate posterior.
                super().run(self.post_warmup_state.rng_key, *args,
                            extra_fields=extra_fields, init_params=None, **kwargs)
                samples = super().get_samples(group_by_chain=True)
                extra = super().get_extra_fields(group_by_chain=True)
                state = {'samples': samples, 'extras': extra}
                jax.block_until_ready(state)
                sampling_seconds += time.perf_counter()-start
                self.post_warmup_state = self.last_state
                start = time.perf_counter()
                leaves, structure = jax.tree.flatten(state)
                if scratch is None:
                    memory_chunks.append(jax.device_get(state))
                else:
                    if retained is None:
                        retained = [np.lib.format.open_memmap(scratch/f'field-{i:03d}.npy',
                            mode='w+', dtype=v.dtype,
                            shape=(self.num_chains, requested_draws, *v.shape[2:]))
                            for i, v in enumerate(leaves)]
                    for target, value in zip(retained, leaves, strict=True):
                        target[:, offset:offset+count] = np.asarray(value)
                        target.flush()
                spill_seconds += time.perf_counter()-start
                callback('retained_sampling', completed_draws_per_chain=offset+count,
                    requested_draws_per_chain=requested_draws,
                    retained_sampling_including_loop_jit_seconds=sampling_seconds,
                    retained_transfer_and_storage_seconds=spill_seconds)
            self.num_samples = requested_draws
            if retained is None:
                self._benchmark_retained = jax.tree.map(
                    lambda *arrays: np.concatenate(arrays, axis=1), *memory_chunks)
            else:
                self._benchmark_retained = jax.tree.unflatten(structure, retained)
            timings['retained_sampling_including_loop_jit_seconds'] = sampling_seconds
            timings['retained_transfer_and_storage_seconds'] = spill_seconds
            timings['retained_batches'] = (requested_draws+batch_draws-1)//batch_draws
            callback('postprocessing', **timings)

        def get_samples(self, group_by_chain=False):
            if not hasattr(self, '_benchmark_retained'):
                return super().get_samples(group_by_chain=group_by_chain)
            values = self._benchmark_retained['samples']
            return values if group_by_chain else jax.tree.map(
                lambda v: v.reshape((-1, *v.shape[2:])), values)

        def get_extra_fields(self, group_by_chain=False):
            if not hasattr(self, '_benchmark_retained'):
                return super().get_extra_fields(group_by_chain=group_by_chain)
            values = self._benchmark_retained['extras']
            return values if group_by_chain else jax.tree.map(
                lambda v: v.reshape((-1, *v.shape[2:])), values)

    numpyro.infer.MCMC = PhasedMCMC
    try:
        yield
    finally:
        numpyro.infer.MCMC = original


def run(dataset, output, *, device='gpu', draws=6000, tune=4000, chains=4, seed=20260924):
    import jax
    import pymc.sampling.jax as pm_jax

    output = Path(output)
    if output.exists(): raise ValueError('Benchmark output must be new')
    if draws < 2000 or tune < 2000 or chains != 4:
        raise ValueError('Sampling-speed comparison requires four production-length chains')
    if not jax.config.x64_enabled: raise ValueError('Float64 required')
    devices = jax.devices(device)
    if device == 'cpu' and len(devices) < chains:
        raise ValueError('CPU comparison requires four declared JAX CPU devices')
    output.mkdir(parents=True)
    phase(output, 'building_model')
    data, source = runner.load_data(dataset)
    design = floor.FeatureDesign(data, 'full_half_balance', floor_increment_prior_scale=.15)
    model = runner.graph.build_model(data, design, 1., residual_scale='shared',
        building_prior_scale=.35, unit_prior_scale=.25, residual_parameterization='centered')
    paths = [*runner.implementation_paths(), Path(floor.__file__), Path(__file__)]
    code = {p.name: digest(p) for p in paths}
    settings = {'version': 'pymc-numpyro-production-benchmark-v2',
        'source_manifest_sha256': digest(Path(dataset)/'complete.json'),
        'source_observations_sha256': source['files']['observations.jsonl'],
        'rows': len(data), 'units': int(data.unit_id.nunique()), 'buildings': int(data.building.nunique()),
        'draws_per_chain': draws, 'warmup_per_chain': tune, 'chains': chains, 'seed': seed,
        'target_accept': .93, 'max_tree_depth': 10, 'dense_mass': False,
        'device': device, 'devices': [str(d) for d in devices], 'device_kind': devices[0].device_kind,
        'chain_method': 'vectorized' if device == 'gpu' else 'parallel',
        'postprocessing_backend': 'cpu', 'float64': True, 'retained_batch_draws': 500,
        'trace_storage': 'All unconstrained draws and statistics spilled to host disk; exact adapted state and RNG continued between batches.',
        'graph_configuration': model.graph_configuration,
        'feature_names': design.features, 'feature_prior_scales': design.prior_scales.tolist(),
        'implementation_sha256': code,
        'versions': {p: importlib.metadata.version(p) for p in
            ('pymc', 'pytensor', 'numpy', 'jax', 'jaxlib', 'numpyro', 'arviz', 'xarray')},
        'timing_policy': 'Warmup includes initialization and its JIT. Retained sampling excludes warmup and postprocessing but includes initial compilation of its own loop. No claim that either phase excludes all compilation. Production-length draws and ESS/sec, not short total runtime, determine the sampling comparison.'}
    publish_bundle(output/'protocol', {'settings.json': canonical(settings)+'\n',
        **{p.name: p.read_text() for p in paths}}, {'version': settings['version']})
    timings = {}; start = time.perf_counter()
    with separate_phases(timings, lambda name, **values: phase(output, name, **values),
                         scratch=output/'unconstrained-trace', batch_draws=500):
        trace = pm_jax.sample_numpyro_nuts(model=model, draws=draws, tune=tune, chains=chains,
            random_seed=seed, target_accept=.93, chain_method=settings['chain_method'],
            postprocessing_backend='cpu', postprocessing_vectorize='scan',
            nuts_kwargs={'dense_mass': False, 'max_tree_depth': 10},
            compute_convergence_checks=False, progressbar=True)
    timings['pymc_call_including_postprocessing_seconds'] = time.perf_counter()-start
    if trace['posterior'].sizes['chain'] != chains or trace['posterior'].sizes['draw'] != draws:
        raise ValueError('Incomplete benchmark posterior')
    phase(output, 'saving_posterior', **timings)
    start = time.perf_counter()
    trace.to_netcdf(output/'posterior.nc', engine='h5netcdf')
    timings['posterior_write_seconds'] = time.perf_counter()-start
    stats = trace['sample_stats'].to_dataset()
    stats_summary = {'divergences': int(stats.diverging.sum().item()),
        'mean_n_steps': float(stats.n_steps.mean().item()), 'max_n_steps': int(stats.n_steps.max().item()),
        'max_tree_depth': int(stats.tree_depth.max().item())}
    trace.close()
    assert all(digest(p) == code[p.name] for p in paths)
    result = {'settings': settings, 'timings': timings, 'sample_statistics': stats_summary,
        'posterior_sha256': digest(output/'posterior.nc'),
        'status': 'sampled_diagnostics_and_ess_comparison_pending'}
    (output/'sampled.json').write_text(canonical(result)+'\n')
    phase(output, result['status'], **timings)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'gpu'), default='gpu')
    run(**vars(parser.parse_args()))
