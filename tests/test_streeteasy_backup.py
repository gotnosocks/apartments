"""ops/streeteasy-backup against a small archive in a temporary folder."""

import os
from pathlib import Path
import sqlite3
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "streeteasy-backup"


def archive(root):
    """An archive with a WAL database still holding rows, a body, a lock and a partial body."""
    root.mkdir()
    db = sqlite3.connect(root / "archive.sqlite3")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("CREATE TABLE ads(id INTEGER)")
    db.executemany("INSERT INTO ads VALUES(?)", [(i,) for i in range(100)])
    db.commit()
    (root / "bodies" / "ab").mkdir(parents=True)
    (root / "bodies" / "ab" / "abcd.json.gz").write_bytes(b"body")
    (root / "bodies" / "ab" / "abce.json.tmp").write_bytes(b"part")
    (root / "graphql-search").mkdir()
    (root / "graphql-search" / "run-1.json").write_text("{}")
    (root / "collector.lock").write_text("")
    return db


def run(source, target, keep=2):
    env = {
        **os.environ,
        "STREETEASY_ARCHIVE": str(source),
        "STREETEASY_BACKUP": str(target),
        "STREETEASY_BACKUP_KEEP": str(keep),
    }
    return subprocess.run(
        [str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


def test_backup_copies_the_open_database_and_the_files(tmp_path):
    source, target = tmp_path / "api", tmp_path / "backup" / "streeteasy-api"
    target.parent.mkdir()
    db = archive(source)
    assert (source / "archive.sqlite3-wal").stat().st_size > 0

    # Older copies beyond the newest two go.
    (target / "db").mkdir(parents=True)
    for day in ("20261001", "20261002", "20261003"):
        (target / "db" / f"archive-{day}T130000Z.sqlite3").write_bytes(b"old")
    # A copy saved by hand stays out of the count.
    (target / "db" / "archive-pre-restore.sqlite3").write_bytes(b"mine")
    db.execute("INSERT INTO ads VALUES(100)")
    db.commit()
    result = run(source, target)
    assert result.returncode == 0, result.stderr
    older, newest, mine = sorted(os.listdir(target / "db"))
    assert older == "archive-20261003T130000Z.sqlite3"
    assert mine == "archive-pre-restore.sqlite3"
    copy = sqlite3.connect(target / "db" / newest)
    assert copy.execute("SELECT count(*) FROM ads").fetchone() == (101,)
    assert copy.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    copy.close()

    files = target / "files"
    assert (files / "bodies" / "ab" / "abcd.json.gz").read_bytes() == b"body"
    assert (files / "graphql-search" / "run-1.json").exists()
    assert not (files / "bodies" / "ab" / "abce.json.tmp").exists()
    assert not list(files.glob("archive.sqlite3*"))
    assert not (files / "collector.lock").exists()
    assert "ok: archive-" in (target / "backup.log").read_text()

    # A body gone from the archive stays in the backup.
    (source / "bodies" / "ab" / "abcd.json.gz").unlink()
    assert run(source, target).returncode == 0
    assert (files / "bodies" / "ab" / "abcd.json.gz").exists()
    db.close()


@pytest.mark.parametrize("missing", ["archive", "disk"])
def test_backup_stops_without_an_archive_or_a_backup_disk(tmp_path, missing):
    source, target = tmp_path / "api", tmp_path / "backup" / "streeteasy-api"
    if missing != "archive":
        archive(source).close()
    if missing != "disk":
        target.parent.mkdir()
    result = run(source, target)
    assert result.returncode == 1
    assert ("no database" if missing == "archive" else "mounted") in result.stderr
    assert not target.exists()


def test_backup_refuses_to_keep_no_copies(tmp_path):
    source, target = tmp_path / "api", tmp_path / "backup" / "streeteasy-api"
    archive(source).close()
    target.parent.mkdir()
    result = run(source, target, keep=0)
    assert result.returncode == 1
    assert "1 or more" in result.stderr
    assert not (target / "db").exists()
