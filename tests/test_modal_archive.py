import importlib.util
from pathlib import Path
import sqlite3
import pytest


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location('modal_archive', Path(__file__).parents[1]/'models/modal_archive.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_streaming_digest_and_invalid_snapshot(module, tmp_path):
    import hashlib
    path = tmp_path/'file'; path.write_bytes(b'abc'*1000)
    assert module.digest(path) == hashlib.sha256(path.read_bytes()).hexdigest()
    for value in ['../archive','x/y','', 'a b']:
        with pytest.raises(ValueError): module.safe_id(value)


def test_resumable_allowlisted_upload(module, tmp_path, monkeypatch):
    archive = tmp_path/'archive'; (archive/'bodies/aa').mkdir(parents=True)
    body = archive/'bodies/aa/hash.gz'; body.write_bytes(b'body')
    (archive/'.env').write_text('do-not-upload')
    db = sqlite3.connect(archive/'archive.sqlite3')
    db.execute('create table observations(id integer)'); db.commit(); db.close()
    paths = []
    class Batch:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def put_file(self, path, remote):
            assert Path(path).exists()
            paths.append(remote)
    class Volume:
        def batch_upload(self, **kwargs): return Batch()
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr(module,'volume',Volume())
    module.upload_files('test', archive, None)
    first = list(paths)
    module.upload_files('test', archive, None)
    assert paths[len(first):] == ['/snapshots/test/complete.json']
    assert first == ['/snapshots/test/archive.sqlite3','/bodies/aa/hash.gz','/snapshots/test/complete.json']
    assert (archive/'archive.sqlite3').exists()
    assert not (tmp_path/'data/modal-upload/test/archive.sqlite3').exists()
