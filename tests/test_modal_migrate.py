"""Export plans preserve durable SQLite data and omit regenerable coordination files."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def module():
    spec = importlib.util.spec_from_file_location('migration_test_module', Path(__file__).parents[1] / 'models/modal_migrate.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_plan_excludes_sqlite_shared_memory_but_keeps_wal(tmp_path, monkeypatch):
    m = module()
    db = tmp_path / 'crawls/test/archive.sqlite3'
    db.parent.mkdir(parents=True)
    db.write_bytes(b'database')
    Path(str(db) + '-wal').write_bytes(b'committed transaction data')
    Path(str(db) + '-shm').write_bytes(b'transient coordination index')
    monkeypatch.setattr(m, 'BASE', tmp_path)
    monkeypatch.setattr(m, 'EXPORT', tmp_path / 'migrations/test')
    monkeypatch.setattr(m, 'volume', SimpleNamespace(reload=lambda: None, commit=lambda: None))
    plan = m.plan.local()
    assert plan['total_files'] == 2
    assert plan['total_bytes'] == len(b'databasecommitted transaction data')
    assert Path(str(db) + '-shm').exists()  # Source is never deleted.


def test_controller_retains_successful_work_after_one_pack_fails(tmp_path, monkeypatch):
    m = module()
    processed = []
    def mapped(ids, **kwargs):
        assert kwargs['return_exceptions'] is True
        for ident in ids:
            processed.append(ident)
            yield RuntimeError('source changed') if ident == 0 else {'id': ident}
    monkeypatch.setattr(m, 'plan', SimpleNamespace(remote=lambda: {'groups': [{'id': 0}, {'id': 1}]}))
    monkeypatch.setattr(m, 'pack', SimpleNamespace(map=mapped))
    monkeypatch.setattr(m, 'EXPORT', tmp_path)
    with pytest.raises(RuntimeError, match='successful bundles retained'):
        m.run.local()
    assert processed == [0, 1]
    assert not (tmp_path / 'complete.json').exists()
