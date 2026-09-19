import json

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models.install_numpyro_recovery import install


def prepared(tmp_path):
    benchmark, recovery = tmp_path/'benchmark', tmp_path/'recovery'
    settings = {'chains': 4, 'draws_per_chain': 6000}
    publish_bundle(benchmark/'protocol', {'settings.json': canonical(settings)+'\n'}, {})
    scratch = benchmark/'unconstrained-trace'
    scratch.mkdir()
    (scratch/'field-000.npy').write_bytes(b'original raw bytes')
    progress = {'phase': 'postprocessing', 'retained_batches': 12,
                'warmup_including_initialization_and_jit_seconds': 100,
                'retained_sampling_including_loop_jit_seconds': 200,
                'retained_transfer_and_storage_seconds': 2}
    (benchmark/'progress.json').write_text(canonical(progress)+'\n')
    recovery.mkdir()
    (recovery/'posterior.nc').write_bytes(b'verified converted posterior bytes')
    record = {'benchmark': str(benchmark.resolve()), 'settings': settings,
              'new_draws_generated': 0, 'original_raw_files_unchanged': True,
              'conversion': {'chains': 4, 'draws': 6000, 'divergences': 0,
                             'mean_n_steps': 63, 'max_n_steps': 63, 'max_tree_depth': 6},
              'sampling_progress': progress, 'posterior_sha256': digest(recovery/'posterior.nc'),
              'recovery_transform_and_write_seconds': 10}
    publish_bundle(recovery/'validation', {'recovery.json': canonical(record)+'\n',
        'raw-inventory.json': canonical({'field-000.npy': digest(scratch/'field-000.npy')})+'\n'}, {})
    return benchmark, recovery


def test_install_preserves_sampling_times_without_inventing_successful_pymc_call(tmp_path):
    benchmark, recovery = prepared(tmp_path)
    install(benchmark, recovery)
    result = json.loads((benchmark/'sampled.json').read_text())
    assert result['pymc_call_completed'] is False
    assert result['timings']['retained_sampling_including_loop_jit_seconds'] == 200
    assert 'pymc_call_including_postprocessing_seconds' not in result['timings']
    assert (benchmark/'posterior.nc').read_bytes() == (recovery/'posterior.nc').read_bytes()
    with pytest.raises(ValueError, match='overwritten'):
        install(benchmark, recovery)


@pytest.mark.parametrize('fault', ['raw', 'posterior', 'progress'])
def test_install_rejects_changed_recovery_or_original_evidence(tmp_path, fault):
    benchmark, recovery = prepared(tmp_path)
    path = {'raw': benchmark/'unconstrained-trace/field-000.npy',
            'posterior': recovery/'posterior.nc', 'progress': benchmark/'progress.json'}[fault]
    path.write_text('{}\n')
    with pytest.raises(ValueError): install(benchmark, recovery)
    assert not (benchmark/'sampled.json').exists()
