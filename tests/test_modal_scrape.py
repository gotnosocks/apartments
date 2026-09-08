"""Remote crawl guards with fixtures only; no provider or Modal calls."""
import importlib.util
from pathlib import Path
import pytest
pytest.importorskip('modal')
spec = importlib.util.spec_from_file_location('modal_scrape', Path(__file__).parents[1]/'models/modal_scrape.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

@pytest.mark.parametrize('budget', [0,-1,10001])
def test_unbounded_or_invalid_budget_rejected(budget):
    with pytest.raises(ValueError): m.validate_budget(budget,5,1)


def test_resume_is_scoped_and_bounded():
    args=m.command(Path('/archive/crawls/test'),100,5,1)
    assert args[args.index('--neighborhood')+1]=='chelsea'
    assert '--include-unavailable' in args and 'resume' in args
    assert args[args.index('--max-requests')+1]=='100'


def test_secret_allowlist():
    assert m.credentials({'OXYLABS_USER':'u','OXYLABS_PASSWORD':'p','OTHER_SECRET':'private'}) == {
        'OXYLABS_USERNAME':'u','OXYLABS_PASSWORD':'p'}


def test_clone_preserves_source(tmp_path):
    import sqlite3,json
    base=tmp_path/'source'; base.mkdir()
    (base/'complete.json').write_text('{}')
    with sqlite3.connect(base/'archive.sqlite3') as db:
        db.execute('CREATE TABLE evidence(value)'); db.execute('INSERT INTO evidence VALUES(7)')
    target=tmp_path/'clone'
    m.clone_snapshot(base,target,'test')
    with sqlite3.connect(target/'archive.sqlite3') as db: db.execute('UPDATE evidence SET value=8')
    with sqlite3.connect(base/'archive.sqlite3') as db: assert db.execute('SELECT value FROM evidence').fetchone()[0]==7
    m.clone_snapshot(base,target,'test')
    assert json.loads((target/'origin.json').read_text())['snapshot']=='test'
    with pytest.raises(ValueError): m.clone_snapshot(base,target,'different')


def test_publish_new_snapshot_and_readiness(tmp_path):
    import sqlite3,json
    snapshots=tmp_path/'snapshots'; snapshots.mkdir()
    workspace=tmp_path/'workspace'; workspace.mkdir()
    (workspace/'origin.json').write_text(json.dumps({'snapshot':'original'}))
    (workspace/'last-run.json').write_text(json.dumps({'exit_code':0,'queue':{'pending':12}}))
    with sqlite3.connect(workspace/'archive.sqlite3') as db:
        db.execute('CREATE TABLE evidence(value)'); db.execute('INSERT INTO evidence VALUES(8)')
    destination=snapshots/'next'
    result=m.publish_workspace(workspace,destination,snapshots,'next')
    assert (destination/'complete.json').exists()
    assert result['source_run']['queue']['pending']==12
    assert not (destination/'apartments.duckdb').exists()
    with sqlite3.connect(destination/'archive.sqlite3') as db:
        assert db.execute('SELECT value FROM evidence').fetchone()[0]==8
    with pytest.raises(ValueError,match='never overwrite'):
        m.publish_workspace(workspace,destination,snapshots,'next')


def test_publish_invalid_seed_leaves_no_readiness_marker(tmp_path):
    import json
    workspace=tmp_path/'workspace'; workspace.mkdir()
    (workspace/'origin.json').write_text(json.dumps({'snapshot':'original'}))
    (workspace/'last-run.json').write_text('{}')
    destination=tmp_path/'new'
    with pytest.raises(ValueError,match='completed preparation'):
        m.publish_workspace(workspace,destination,tmp_path,'new',True)
    assert not (destination/'complete.json').exists()
