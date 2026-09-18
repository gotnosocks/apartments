import json
from types import SimpleNamespace

import pytest

from apartments.research_pipeline import _verified_bundle
from models import bayesian_sampling as m


def test_interrupted_binary_completion_recovers_and_verifies(tmp_path):
    (tmp_path/'posterior.nc').write_bytes(b'\x00\xffbinary posterior\n')
    (tmp_path/'complete.json.tmp').write_text('interrupted previous write')
    manifest = m.publish_fit(tmp_path, version='test', protocol_hash='p1')
    assert set(manifest['files']) == {'posterior.nc'}
    assert not (tmp_path/'complete.json.tmp').exists()
    assert m.publish_fit(tmp_path, version='test', protocol_hash='p1') == manifest
    with pytest.raises(ValueError, match='another protocol'):
        m.publish_fit(tmp_path, version='test', protocol_hash='p2')
    (tmp_path/'posterior.nc').write_bytes(b'changed')
    with pytest.raises(ValueError):
        _verified_bundle(tmp_path)


def test_publication_rejects_symlink_payload(tmp_path):
    (tmp_path/'real').write_text('source')
    (tmp_path/'link').symlink_to(tmp_path/'real')
    with pytest.raises(ValueError, match='regular files'):
        m.publish_fit(tmp_path, version='test', protocol_hash='p1')
    assert not (tmp_path/'complete.json').exists()


def test_progress_atomically_records_chain_state_and_nonfinite_initial_step(tmp_path, capsys):
    path = tmp_path/'progress.json'
    callback = m.SamplingProgress(path)
    chain = SimpleNamespace(finished_draws=12, total_draws=250, divergences=1,
        tuning=True, started=True, latest_num_steps=31, total_num_steps=123,
        step_size=float('nan'), runtime_ms=2500)
    callback([chain])
    first = json.loads(path.read_text())
    assert first['phase'] == 'sampling'
    assert first['chains'][0]['step_size'] is None
    assert first['chains'][0]['runtime_seconds'] == 2.5
    assert first['chains'][0]['finished_draws'] == 12
    assert not (tmp_path/'progress.json.tmp').exists()
    assert json.loads(capsys.readouterr().out) == first
    chain.finished_draws = 13
    callback([chain])
    assert json.loads(path.read_text())['chains'][0]['finished_draws'] == 13
    assert capsys.readouterr().out == ''


def test_sampling_forwards_settings_and_records_terminal_failure(tmp_path, monkeypatch):
    import nutpie
    seen = {}
    model = object(); compiled = object()
    inference = {'posterior': SimpleNamespace(sizes={'chain': 4, 'draw': 100})}
    def compile_model(actual, **kw):
        assert actual is model and kw == {'backend': 'numba'}
        assert json.loads((tmp_path/'progress.json').read_text())['phase'] == 'compiling'
        return compiled
    def draw(actual, **kw):
        assert actual is compiled
        seen.update(kw)
        return inference
    monkeypatch.setattr(nutpie, 'compile_pymc_model', compile_model)
    monkeypatch.setattr(nutpie, 'sample', draw)
    args = dict(draws=100, tune=200, chains=4, seed=42, adaptation='diag',
                target_accept=.94, status_path=tmp_path/'progress.json')
    assert m.sample(model, **args) is inference
    assert {k: seen[k] for k in ('draws', 'tune', 'chains', 'seed', 'adaptation', 'target_accept')} == {
        k: args[k] for k in ('draws', 'tune', 'chains', 'seed', 'adaptation', 'target_accept')}
    assert seen['cores'] == 4 and seen['save_warmup'] is False
    assert isinstance(seen['progress_callback'], m.SamplingProgress)
    assert json.loads((tmp_path/'progress.json').read_text())['phase'] == 'sampled'
    monkeypatch.setattr(nutpie, 'sample', lambda *a, **k: {'posterior': SimpleNamespace(sizes={'chain': 4, 'draw': 99})})
    with pytest.raises(ValueError, match='incomplete chains or draws'):
        m.sample(model, **args)
    assert json.loads((tmp_path/'progress.json').read_text())['phase'] == 'failed'
    def fail(*args, **kwargs):
        raise RuntimeError('failed sampler')
    monkeypatch.setattr(nutpie, 'sample', fail)
    with pytest.raises(RuntimeError, match='failed sampler'):
        m.sample(model, **args)
    assert json.loads((tmp_path/'progress.json').read_text())['phase'] == 'failed'
