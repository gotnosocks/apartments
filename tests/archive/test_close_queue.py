from streeteasy_archive.cli import main
from streeteasy_archive.store import ArchiveStore


def test_close_queue_lets_a_new_generation_start(tmp_path):
    store = ArchiveStore(tmp_path)
    g = store.new_generation()
    store.enqueue(
        g,
        [
            {"url": "https://streeteasy.com/building/a", "kind": "building"},
            {"url": "https://streeteasy.com/rental/2000000", "kind": "listing"},
        ],
    )
    store.close()
    assert (
        main(
            [
                "--data",
                str(tmp_path),
                "close-queue",
                "--generation",
                str(g),
                "--reason",
                "x",
            ]
        )
        == 0
    )
    store = ArchiveStore(tmp_path)
    states = {r[0] for r in store.db.execute("SELECT state FROM frontier")}
    assert states == {"abandoned"}
    assert store.db.execute(
        "SELECT value FROM metadata WHERE key=?", (f"closed_queue:{g}",)
    ).fetchone()
    assert store.new_generation("update") == g + 1
    store.close()
