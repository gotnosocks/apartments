"""Safe file copying for explicitly requested archive snapshots."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import shutil


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

