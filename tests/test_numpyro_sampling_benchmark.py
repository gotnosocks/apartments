"""Lifecycle checks only: small chains are never sampling-speed evidence."""
import numpy as np
import pytest

jax = pytest.importorskip('jax')
numpyro = pytest.importorskip('numpyro')

from models.numpyro_sampling_benchmark import separate_phases


def sample(batch, scratch=None):
    import pymc as pm
    from pymc.sampling.jax import sample_numpyro_nuts
    timings, events = {}, []
    with pm.Model() as model:
        pm.Normal('x', shape=3)
    original = numpyro.infer.MCMC
    with separate_phases(timings, lambda name, **kw: events.append((name, kw)),
                         batch_draws=batch, scratch=scratch):
        result = sample_numpyro_nuts(model=model, draws=21, tune=30, chains=2,
            chain_method='vectorized', random_seed=123, progressbar=False,
            compute_convergence_checks=False, postprocessing_backend='cpu')
    assert numpyro.infer.MCMC is original
    assert result['posterior'].sizes['chain'] == 2
    assert result['posterior'].sizes['draw'] == 21
    assert timings['retained_sampling_including_loop_jit_seconds'] > 0
    assert events[0][0] == 'warmup_including_initialization_and_jit'
    assert events[-1][0] == 'postprocessing'
    return result, events


def test_batches_preserve_every_draw_and_statistic(tmp_path):
    whole, _ = sample(21)
    batched, events = sample(8, tmp_path/'trace')
    for group in ('posterior', 'sample_stats'):
        for name in whole[group].data_vars:
            np.testing.assert_allclose(whole[group][name].values,
                                       batched[group][name].values, rtol=1e-10, atol=1e-10)
    counts = [v['completed_draws_per_chain'] for _, v in events
              if 'completed_draws_per_chain' in v]
    assert counts == [8, 16, 21]
    assert list((tmp_path/'trace').glob('*.npy'))


def test_callback_failure_restores_library_class():
    original = numpyro.infer.MCMC
    def fail(*args, **kwargs):
        raise RuntimeError('test interruption')
    with pytest.raises(RuntimeError, match='test interruption'):
        with separate_phases({}, fail):
            sampler = numpyro.infer.MCMC(numpyro.infer.NUTS(
                potential_fn=lambda x: (x*x).sum()/2), num_warmup=3, num_samples=3)
            sampler.run(jax.random.PRNGKey(1), init_params=np.zeros(2))
    assert numpyro.infer.MCMC is original
