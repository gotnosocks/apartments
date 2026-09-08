"""Small SQLite fixtures for cloud checkpoint publication and backup guards."""
import json
import sqlite3
from streeteasy_archive.cloud_state import publish_browser_checkpoint


def test_checkpoint_is_standalone_and_replaced(tmp_path):
    source=tmp_path/'crawls/test'; source.mkdir(parents=True)
    db=sqlite3.connect(source/'archive.sqlite3')
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE evidence(value)')
        db.execute('INSERT INTO evidence VALUES(1)'); db.commit()
        first=publish_browser_checkpoint(source,tmp_path)
        checkpoint=tmp_path/'browser/archive.sqlite3'
        with sqlite3.connect(checkpoint) as reader:
            assert reader.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert reader.execute('PRAGMA journal_mode').fetchone()[0]=='delete'
            assert reader.execute('SELECT value FROM evidence').fetchone()[0]==1
        inode=checkpoint.stat().st_ino
        db.execute('UPDATE evidence SET value=2'); db.commit()
        second=publish_browser_checkpoint(source,tmp_path)
        assert checkpoint.stat().st_ino!=inode
        with sqlite3.connect(checkpoint) as reader:
            assert reader.execute('SELECT value FROM evidence').fetchone()[0]==2
            assert reader.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert second['committed_at']>=first['committed_at']
        assert json.loads((tmp_path/'browser/checkpoint.json').read_text())['archive_path']=='crawls/test'
        assert (tmp_path/'browser/bodies').is_symlink()
        assert not (tmp_path/'browser/archive.partial.sqlite3').exists()
    finally:
        db.close()


def test_local_backup_writer_rejected_without_mutation(tmp_path,capsys):
    from streeteasy_archive.cli import acquire_lock
    marker=tmp_path/'CLOUD_AUTHORITATIVE.json'; marker.write_text('{}')
    assert acquire_lock(tmp_path) is None
    assert 'local archive is a backup' in capsys.readouterr().err
    assert not (tmp_path/'crawler.lock').exists()
    assert not (tmp_path/'archive.sqlite3').exists()


def test_bulk_copy_rejects_uncheckpointed_wal(tmp_path):
    import pytest
    from streeteasy_archive.cloud_state import copy_closed_database,checkpoint_database
    source=tmp_path/'source.sqlite3'; target=tmp_path/'target.sqlite3'
    db=sqlite3.connect(source)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE evidence(value)')
        db.execute('INSERT INTO evidence VALUES(9)'); db.commit()
        with pytest.raises(RuntimeError,match='nonempty WAL'):
            copy_closed_database(source,target)
        assert not target.exists()
        checkpoint_database(source)
        copy_closed_database(source,target)
        with sqlite3.connect(target) as reader:
            assert reader.execute('SELECT value FROM evidence').fetchone()[0]==9
        with pytest.raises(ValueError,match='already exists'):
            copy_closed_database(source,target)
    finally:
        db.close()
