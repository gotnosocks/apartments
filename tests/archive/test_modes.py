import json

from streeteasy_archive import cli
from streeteasy_archive.store import ArchiveStore


def _profile(path, generation):
    store = ArchiveStore(path)
    row = store.db.execute(
        "SELECT value FROM metadata WHERE key=?", (f"crawl_profile:{generation}",)
    ).fetchone()
    store.close()
    return json.loads(row[0])


def test_backfill_defaults_to_historical_profile(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        cli, "run_crawler", lambda args, generation, lock: seen.append(args) or 0
    )

    assert cli.main(["--data", str(tmp_path), "backfill"]) == 0
    assert seen[0].include_unavailable is True
    assert seen[0].transport == "oxylabs"
    store = ArchiveStore(tmp_path)
    generation = store.current_generation()
    store.close()
    assert _profile(tmp_path, generation)["include_unavailable"] is True


def test_update_defaults_to_current_and_skips_historical_rows(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    old = store.new_generation("backfill")
    store.enqueue(
        old,
        [
            {"url": "https://streeteasy.com/building/a", "kind": "building"},
            {"url": "https://streeteasy.com/rental/1", "kind": "listing"},
            {"url": "https://api-v6.streeteasy.com/inventory/1", "kind": "inventory"},
        ],
    )
    with store._tx():
        store.db.execute("UPDATE frontier SET state='done' WHERE generation=?", (old,))
    store.finish(old)
    store.close()
    seen = []
    monkeypatch.setattr(
        cli, "run_crawler", lambda args, generation, lock: seen.append(args) or 0
    )

    assert cli.main(["--data", str(tmp_path), "update"]) == 0
    assert seen[0].include_unavailable is False
    assert seen[0].transport == "oxylabs"
    store = ArchiveStore(tmp_path)
    generation = store.current_generation()
    kinds = {
        r["kind"]
        for r in store.db.execute(
            "SELECT kind FROM frontier WHERE generation=?", (generation,)
        )
    }
    store.close()
    assert kinds == {"building", "sitemap", "directory", "search"}
    assert _profile(tmp_path, generation)["include_unavailable"] is False


def test_resume_inherits_profile_and_allows_override(tmp_path, monkeypatch):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation("backfill")
    store.enqueue(
        generation, [{"url": "https://streeteasy.com/building/a", "kind": "building"}]
    )
    with store._tx():
        store.db.execute(
            "INSERT INTO metadata VALUES(?,?)",
            (
                f"crawl_profile:{generation}",
                json.dumps(
                    {
                        "include_unavailable": True,
                        "transport": "http",
                        "delay": 10,
                        "concurrency": 5,
                        "api_rps": 2,
                    }
                ),
            ),
        )
    store.close()
    seen = []
    monkeypatch.setattr(
        cli, "run_crawler", lambda args, generation, lock: seen.append(args) or 0
    )

    assert (
        cli.main(["--data", str(tmp_path), "resume", "--no-include-unavailable"]) == 0
    )
    assert seen[0].include_unavailable is False
    assert seen[0].transport == "oxylabs"
    assert seen[0].delay == 0
