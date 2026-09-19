import copy
import fcntl
import hashlib

import numpy as np
import pytest
import xarray as xr

from apartments.corrections import canonical
from models import bayesian_disk_sampling as storage
from models import recover_completed_disk_trace as recovery


@pytest.fixture
def finished():
    protocol = dict(chains=2, draws=7, tune=9, seed=11, adaptation='diag', target_accept=.93)
    identity = {**protocol, 'protocol_sha256': hashlib.sha256(canonical(protocol).encode()).hexdigest(),
        'contract': {'chains': 2, 'draws': 7, 'variables': {'a': []}, 'coordinates': {}}}
    progress = {'chains': [dict(chain=i, finished_draws=16, total_draws=16, tuning=False)
                           for i in range(2)]}
    stats = {k: (('chain', 'draw'), np.ones((2, 7))) for k in storage.STATISTICS}
    stats['tuning'] = (('chain', 'draw'), np.zeros((2, 7), dtype=bool))
    trace = xr.DataTree.from_dict({
        '/': xr.Dataset(attrs={'adaptation_kind': 'diagonal', 'sampler_settings': {
            'num_chains': 2, 'num_draws': 7, 'num_tune': 9, 'seed': 11,
            'adapt_options': {'step_size_settings': {'target_accept': .93}}}}),
        'posterior': xr.Dataset({'a': (('chain', 'draw'), np.ones((2, 7)))}),
        'sample_stats': xr.Dataset(stats)})
    return identity, protocol, progress, trace


def test_finished_identity_and_all_draws_validate(finished):
    assert recovery.validate_finished(*finished) == finished[0]['protocol_sha256']


@pytest.mark.parametrize('damage', ['short', 'tuning', 'chain_duplicate', 'seed', 'raw_seed', 'empty_steps'])
def test_no_completion_from_partial_or_mismatched_evidence(finished, damage):
    identity, protocol, progress, trace = copy.deepcopy(finished)
    if damage == 'short': progress['chains'][0]['finished_draws'] -= 1
    if damage == 'tuning': progress['chains'][0]['tuning'] = True
    if damage == 'chain_duplicate': progress['chains'][0]['chain'] = 1
    if damage == 'seed': identity['seed'] += 1
    if damage == 'raw_seed': trace.attrs['sampler_settings']['seed'] += 1
    if damage == 'empty_steps': trace['sample_stats'].n_steps.values[0, 0] = 0
    with pytest.raises(ValueError):
        recovery.validate_finished(identity, protocol, progress, trace)


def test_install_refuses_to_touch_a_live_experiment(tmp_path):
    experiment = tmp_path/'experiment'; experiment.mkdir()
    with (experiment/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            recovery.install(experiment, tmp_path/'absent-recovery')
    assert not (experiment/'fit').exists()
