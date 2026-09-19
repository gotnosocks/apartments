"""Convert a completed disk-spilled PyMC/NumPyro trace on CPU without sampling."""
import argparse
import json
from pathlib import Path
import time
from types import SimpleNamespace

import h5netcdf
import numpy as np
import xarray as xr

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from models import bayesian_feature_experiment_v3 as runner
from models import bayesian_floor_increment_design as floor

EXTRAS = ('num_steps', 'potential_energy', 'energy', 'adapt_state.step_size', 'accept_prob', 'diverging')


def restore(model, scratch, chains, draws):
    """Reconstruct the exact JAX pytree used by the archived spill implementation."""
    import jax
    initial = model.initial_point()
    if list(initial) != [v.name for v in model.value_vars]:
        raise ValueError('Initial-point and model value-variable order differ')
    template = {'extras': dict.fromkeys(EXTRAS, 0.), 'samples': list(initial.values())}
    leaves, structure = jax.tree_util.tree_flatten_with_path(template)
    paths = sorted(Path(scratch).glob('*.npy'))
    if [p.name for p in paths] != [f'field-{i:03d}.npy' for i in range(len(leaves))]:
        raise ValueError('Spilled leaf inventory differs from PyMC NumPyro contract')
    arrays, schema = [], []
    for path, (key, example) in zip(paths, leaves, strict=True):
        array = np.load(path, mmap_mode='r', allow_pickle=False)
        expected = (chains, draws, *np.shape(example))
        if array.shape != expected or array.dtype.kind not in 'bifu':
            raise ValueError('Spilled leaf shape or dtype differs: '+path.name)
        arrays.append(array)
        schema.append({'file': path.name, 'path': jax.tree_util.keystr(key),
                       'shape': list(array.shape), 'dtype': str(array.dtype)})
    state = jax.tree.unflatten(structure, arrays)
    if (not np.isfinite(state['extras']['num_steps']).all()
            or not (state['extras']['num_steps'] > 0).all()):
        raise ValueError('Missing completed retained sampler statistics')
    return state, schema


def convert(model, state, output, *, batch=64, callback=lambda **kw: None):
    """Apply PyMC's exact constrained-variable graph in bounded CPU batches."""
    import jax
    import pymc.sampling.jax as pm_jax
    if jax.default_backend() != 'cpu' or not jax.config.x64_enabled:
        raise ValueError('Recovery requires default CPU and float64 JAX')
    variables = list(pm_jax.get_default_varnames(model.unobserved_value_vars, include_transformed=False))
    fn = pm_jax.get_jaxified_graph(inputs=model.value_vars, outputs=variables)
    transform = jax.jit(jax.vmap(jax.vmap(fn)))
    potential = jax.jit(pm_jax.get_jaxified_logp(model, negative_logp=False))
    samples = state['samples']
    chains, draws = samples[0].shape[:2]
    # Every chain and the first/middle/final retained positions independently
    # check the recovered variable/statistic ordering against the sampled target.
    density_checks = []
    for chain in range(chains):
        for draw in sorted({0, draws//2, draws-1}):
            calculated = float(potential([np.asarray(a[chain, draw]) for a in samples]))
            saved = float(state['extras']['potential_energy'][chain, draw])
            if not np.isfinite([calculated, saved]).all() or not np.isclose(calculated, saved, rtol=1e-10, atol=1e-7):
                raise ValueError('Recovered variable ordering differs from sampled potential energy')
            density_checks.append({'chain': chain, 'draw': draw, 'absolute_error': abs(calculated-saved)})
    stats = pm_jax._numpyro_stats_to_dict(SimpleNamespace(get_extra_fields=lambda group_by_chain: state['extras']))
    if any(not np.isfinite(v).all() for v in stats.values()):
        raise ValueError('Nonfinite saved sampler statistics')
    output = Path(output)
    if output.exists() or output.with_suffix('.partial').exists():
        raise ValueError('Recovery output must be new')
    temporary = output.with_suffix('.partial')
    xr.Dataset(attrs={'recovery': 'Exact PyMC graph; original retained draws, CPU batches'}).to_netcdf(temporary, engine='h5netcdf')
    stats_ds = xr.Dataset({k: (('chain', 'draw'), v) for k, v in stats.items()},
                          coords={'chain': range(chains), 'draw': range(draws)})
    stats_ds.to_netcdf(temporary, group='sample_stats', mode='a', engine='h5netcdf')
    initialized = False
    maximum = 0
    with h5netcdf.File(temporary, 'a') as target:
        node = target.create_group('posterior')
        for start in range(0, draws, batch):
            end = min(start+batch, draws)
            inputs = [np.asarray(a[:, start:end]) for a in samples]
            if any(not np.isfinite(a).all() for a in inputs):
                raise ValueError('Nonfinite retained unconstrained draw')
            transformed = [np.asarray(a) for a in transform(*inputs)]
            if not initialized:
                node.dimensions['chain'] = chains
                node.dimensions['draw'] = draws
                for name, values in [('chain', np.arange(chains)), ('draw', np.arange(draws))]:
                    node.create_variable(name, (name,), data=values)
                for var, array in zip(variables, transformed, strict=True):
                    dims = tuple(model.named_vars_to_dims.get(var.name, ()))
                    if len(dims) != array.ndim-2:
                        # PyMC/ArviZ's default names for unnamed variable axes.
                        dims = tuple(f'{var.name}_dim_{i}' for i in range(array.ndim-2))
                    for dim, size in zip(dims, array.shape[2:], strict=True):
                        if dim in node.dimensions:
                            if len(node.dimensions[dim]) != size: raise ValueError('Coordinate size differs')
                        else:
                            node.dimensions[dim] = size
                            values = np.asarray(model.coords.get(dim, range(size)))
                            if values.dtype.kind in 'OU':
                                import h5py
                                coord = node.create_variable(dim, (dim,), dtype=h5py.string_dtype())
                                coord[:] = values.astype(object)
                            else:
                                node.create_variable(dim, (dim,), data=values)
                    node.create_variable(var.name, ('chain', 'draw', *dims), dtype=array.dtype,
                        chunks=(1, min(batch, draws), *(min(n, 512) for n in array.shape[2:])),
                        compression='gzip', compression_opts=1)
                initialized = True
            for var, array in zip(variables, transformed, strict=True):
                if not np.isfinite(array).all(): raise ValueError('Nonfinite constrained posterior')
                maximum = max(maximum, array.nbytes)
                node.variables[var.name][:, start:end] = array
                if not np.array_equal(node.variables[var.name][:, start:end], array):
                    raise ValueError('Posterior write does not exactly preserve transformed values')
            callback(completed_draws_per_chain=end, requested_draws_per_chain=draws)
    temporary.replace(output)
    return {'chains': chains, 'draws': draws, 'variables': [v.name for v in variables],
            'maximum_transformed_variable_batch_bytes': maximum, 'density_checks': density_checks,
            'divergences': int(stats['diverging'].sum()), 'mean_n_steps': float(stats['n_steps'].mean()),
            'max_n_steps': int(stats['n_steps'].max()), 'max_tree_depth': int(stats['tree_depth'].max())}


def run(benchmark, dataset, output):
    benchmark, dataset, output = map(Path, (benchmark, dataset, output))
    if output.exists(): raise ValueError('Recovery directory must be new')
    _, files = _verified_bundle(benchmark/'protocol', retain={'settings.json'})
    settings = json.loads(files['settings.json'])
    progress = json.loads((benchmark/'progress.json').read_text())
    if (progress['phase'] != 'postprocessing'
            or progress['retained_batches']*settings['retained_batch_draws'] != settings['draws_per_chain']):
        raise ValueError('Saved progress does not prove completed retained batching')
    paths = [*runner.implementation_paths(), Path(floor.__file__)]
    if any(settings['implementation_sha256'].get(p.name) != digest(p) for p in paths):
        raise ValueError('Sampled model implementation differs')
    data, source = runner.load_data(dataset)
    design = floor.FeatureDesign(data, 'full_half_balance', floor_increment_prior_scale=.15)
    if (digest(dataset/'complete.json') != settings['source_manifest_sha256']
            or source['files']['observations.jsonl'] != settings['source_observations_sha256']
            or design.features != settings['feature_names'] or design.prior_scales.tolist() != settings['feature_prior_scales']):
        raise ValueError('Sampled data or feature design differs')
    model = runner.graph.build_model(data, design, 1., residual_scale='shared',
        building_prior_scale=.35, unit_prior_scale=.25, residual_parameterization='centered')
    if model.graph_configuration != settings['graph_configuration']:
        raise ValueError('Sampled graph configuration differs')
    scratch = benchmark/'unconstrained-trace'
    inventory = {p.name: digest(p) for p in sorted(scratch.glob('*.npy'))}
    state, schema = restore(model, scratch, settings['chains'], settings['draws_per_chain'])
    output.mkdir(parents=True)
    print(canonical({'phase': 'recovering_saved_draws', 'leaves': schema}), flush=True)
    start = time.perf_counter()
    def progress_callback(**kw):
        if kw['completed_draws_per_chain'] % 512 == 0 or kw['completed_draws_per_chain'] == settings['draws_per_chain']:
            print(canonical(kw), flush=True)
    converted = convert(model, state, output/'posterior.nc', callback=progress_callback)
    elapsed = time.perf_counter()-start
    if inventory != {p.name: digest(p) for p in sorted(scratch.glob('*.npy'))}:
        raise ValueError('Raw trace changed during conversion')
    record = {'version': 'numpyro-completed-trace-cpu-recovery-v1',
        'benchmark': str(benchmark.resolve()), 'settings': settings, 'sampling_progress': progress,
        'posterior_sha256': digest(output/'posterior.nc'), 'conversion': converted,
        'recovery_transform_and_write_seconds': elapsed,
        'original_raw_files_unchanged': True, 'new_draws_generated': 0,
        'timing_policy': 'Recovery conversion is separate from retained sampling. The original PyMC call failed after all retained draws; no successful end-to-end PyMC-call timing is available.'}
    publish_bundle(output/'validation', {'recovery.json': canonical(record)+'\n',
        'raw-inventory.json': canonical(inventory)+'\n', 'leaf-schema.json': canonical(schema)+'\n',
        Path(__file__).name: Path(__file__).read_text()}, {'version': record['version']})
    print(canonical(record), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('benchmark', 'dataset', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
