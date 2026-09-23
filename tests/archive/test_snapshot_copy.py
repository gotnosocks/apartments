import sqlite3


def test_bulk_copy_rejects_uncheckpointed_wal(tmp_path):
    import pytest
    from streeteasy_archive.snapshot_copy import (
        copy_closed_database,
        checkpoint_database,
    )

    source = tmp_path / "source.sqlite3"
    target = tmp_path / "target.sqlite3"
    db = sqlite3.connect(source)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE evidence(value)")
        db.execute("INSERT INTO evidence VALUES(9)")
        db.commit()
        with pytest.raises(RuntimeError, match="nonempty WAL"):
            copy_closed_database(source, target)
        assert not target.exists()
        checkpoint_database(source)
        copy_closed_database(source, target)
        with sqlite3.connect(target) as reader:
            assert reader.execute("SELECT value FROM evidence").fetchone()[0] == 9
        with pytest.raises(ValueError, match="already exists"):
            copy_closed_database(source, target)
    finally:
        db.close()
