"""Cloud writer helpers; no Modal SDK and no implicit Volume commits."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import shutil
import time


def checkpoint_database(source):
    """Flush a stopped writer under its external lock; never create a missing DB."""
    source = Path(source).resolve()
    db = sqlite3.connect(source.as_uri()+'?mode=rw', uri=True, timeout=1)
    try:
        busy, _, _ = db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if busy:
            raise RuntimeError('SQLite checkpoint is busy; database cannot be copied safely')
    finally:
        db.close()
    wal = Path(str(source)+'-wal')
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError('SQLite WAL is not empty after checkpoint')


def copy_closed_database(source, destination):
    """Bulk-copy a stable WAL-free source without modifying it.

    Caller owns the writer lock, or the source is an immutable uploaded snapshot.
    This uses bounded filesystem copying instead of many remote SQLite page writes.
    """
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Database copy destination already exists')
    wal = Path(str(source)+'-wal')
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError('Refusing to copy a database with a nonempty WAL')
    shutil.copyfile(source, destination)
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError('Source WAL changed during database copy')
    db = sqlite3.connect(destination.resolve().as_uri()+'?mode=rw', uri=True)
    try:
        mode = db.execute('PRAGMA journal_mode=DELETE').fetchone()[0]
        if mode.lower() != 'delete':
            raise RuntimeError('Copied database must be standalone')
        db.commit()
    finally:
        db.close()


def publish_browser_checkpoint(archive_root, cloud_root):
    """Publish a closed, standalone SQLite copy under the caller's writer lock.

    Readers use the replaced database, never the active writer's cross-container WAL.
    The caller must commit the Volume after this helper returns.
    """
    archive = Path(archive_root).resolve()
    root = Path(cloud_root).resolve()
    relative = archive.relative_to(root).as_posix()
    browser = root/'browser'
    if archive == browser:
        raise ValueError('Browser checkpoint cannot be its own source')
    browser.mkdir(parents=True, exist_ok=True)
    bodies = browser/'bodies'
    if bodies.is_symlink():
        if bodies.resolve() != (root/'bodies').resolve():
            raise ValueError('Browser body link points to another archive')
    elif bodies.exists():
        raise ValueError('Browser bodies must be a link to shared cloud bodies')
    else:
        bodies.symlink_to(root/'bodies', target_is_directory=True)
    partial = browser/'archive.partial.sqlite3'
    for suffix in ('', '-wal', '-shm'):
        Path(str(partial)+suffix).unlink(missing_ok=True)
    checkpoint_database(archive/'archive.sqlite3')
    copy_closed_database(archive/'archive.sqlite3', partial)
    partial.replace(browser/'archive.sqlite3')
    record = {'committed_at':time.time(), 'archive_path':relative}
    metadata = browser/'checkpoint.partial.json'
    metadata.write_text(json.dumps(record,indent=2))
    metadata.replace(browser/'checkpoint.json')
    return record
