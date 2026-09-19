"""Tiny traces test recovery correctness only, never sampling performance."""
import numpy as np
import pytest
import xarray as xr

jax = pytest.importorskip('jax')
pytest.importorskip('numpyro')

from models.numpyro_sampling_benchmark import separate_phases
from models.recover_numpyro_trace import convert, restore


def test_recovery_matches_native_pymc_transforms_coordinates_and_every_draw(tmp_path):
    import pymc as pm
    from pymc.sampling.jax import sample_numpyro_nuts
    with pm.Model(coords={'axis': ['a', 'b', 'c']}) as model:
        x = pm.Normal('x', dims='axis')
        sigma = pm.HalfNormal('sigma')
        pm.Deterministic('scaled', x*sigma, dims='axis')
    scratch = tmp_path/'raw'
    with separate_phases({}, lambda *a, **k: None, scratch=scratch, batch_draws=8):
        expected = sample_numpyro_nuts(model=model, draws=21, tune=30, chains=2,
            chain_method='vectorized', random_seed=177, progressbar=False,
            compute_convergence_checks=False, postprocessing_backend='cpu')
    state, schema = restore(model, scratch, 2, 21)
    assert len(schema) == 8
    output = tmp_path/'posterior.nc'
    converted = convert(model, state, output, batch=8)
    assert converted['chains'] == 2 and converted['draws'] == 21
    assert len(converted['density_checks']) == 6
    with xr.open_datatree(output, engine='h5netcdf', cache=False) as actual:
        for group in ('posterior', 'sample_stats'):
            assert set(actual[group].data_vars) == set(expected[group].data_vars)
            for name in expected[group].data_vars:
                assert actual[group][name].dims == expected[group][name].dims
                np.testing.assert_allclose(actual[group][name], expected[group][name], rtol=1e-13, atol=1e-13)
        assert actual['posterior'].axis.values.tolist() == ['a', 'b', 'c']
    expected.close()
    # A preallocated but unwritten tail cannot count as a completed trace.
    index = next(i for i, r in enumerate(schema) if 'num_steps' in r['path'])
    damaged = np.load(scratch/f'field-{index:03d}.npy', mmap_mode='r+')
    damaged[:, -1] = 0
    damaged.flush()
    with pytest.raises(ValueError, match='completed retained'):
        restore(model, scratch, 2, 21)


def test_recovery_rejects_wrong_leaf_count_before_mapping(tmp_path):
    import pymc as pm
    with pm.Model() as model:
        pm.Normal('x')
    with pytest.raises(ValueError, match='inventory'):
        restore(model, tmp_path, 2, 21)
