import inspect

import pytest

from streeteasy_archive import cli, structure_first
from streeteasy_archive.collection_policy import setup
from streeteasy_archive.store import ArchiveStore

ROWS = [
    ("https://streeteasy.com/rental/123", "listing"),
    ("https://streeteasy.com/building/example/4c", "listing"),
    (
        "https://streeteasy.com/building/example?archive_view=unavailable-rentals",
        "inventory",
    ),
    ("https://streeteasy.com/for-rent/east-village", "search"),
    ("https://streeteasy.com/building/example", "building"),
    ("https://streeteasy.com/buildings/east-village?page=40", "directory"),
    ("https://streeteasy.com/building/other/rentals", "building"),
]


def drain(tmp_path, claim, rows, **kwargs):
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    s.enqueue(g, [{"url": u, "kind": k} for u, k in rows])
    order = []
    while row := claim(s, g, **kwargs):
        order.append(row["url"])
    excluded = s.db.execute(
        "SELECT url FROM collection_exclusions ORDER BY url"
    ).fetchall()
    s.close()
    return order, [r[0] for r in excluded]


def test_directory_then_buildings_then_original_order(tmp_path):
    order, _ = drain(
        tmp_path / "a",
        structure_first.claim_structure_first,
        ROWS,
        prefer_inventory=True,
        prefer_units=True,
    )
    original, _ = drain(
        tmp_path / "b",
        structure_first.ORIGINAL_CLAIM,
        ROWS,
        prefer_inventory=True,
        prefer_units=True,
    )
    assert order[:3] == [
        "https://streeteasy.com/buildings/east-village?page=40",
        "https://streeteasy.com/building/example",
        "https://streeteasy.com/building/other/rentals",
    ]
    assert sorted(order) == sorted(original)
    assert order[3:] == [u for u in original if u not in order[:3]]


def test_same_pages_and_order_without_structure_rows(tmp_path):
    rows = [r for r in ROWS if r[1] not in ("directory", "building")]
    for kwargs in (
        {},
        {"prefer_inventory": True},
        {"prefer_inventory": True, "prefer_units": True},
    ):
        name = "-".join(kwargs) or "plain"
        new = drain(
            tmp_path / ("new-" + name),
            structure_first.claim_structure_first,
            rows,
            **kwargs,
        )
        old = drain(
            tmp_path / ("old-" + name), structure_first.ORIGINAL_CLAIM, rows, **kwargs
        )
        assert new == old


def test_filter_matches_store_claim():
    """The copy must track ArchiveStore.claim's candidate filter and its tie-breaks."""

    def sql(fn):
        src = inspect.getsource(fn)
        src = src[src.index("SELECT f.*") : src.index("LIMIT 1")]
        src = "\n".join(line.split("--")[0] for line in src.splitlines())
        return " ".join(src.replace('"""', "").replace("+", "").split())

    original = sql(structure_first.ORIGINAL_CLAIM)
    copy = sql(structure_first._sorted_candidate).replace(" STRUCTURE_RANK ,", "")
    assert copy == original


def test_claim_order_is_scoped():
    assert ArchiveStore.claim is structure_first.ORIGINAL_CLAIM
    with structure_first.claim_order("structure-first"):
        assert ArchiveStore.claim is structure_first.claim_structure_first
        with structure_first.claim_order("original"):
            assert ArchiveStore.claim is structure_first.ORIGINAL_CLAIM
        assert ArchiveStore.claim is structure_first.claim_structure_first
    assert ArchiveStore.claim is structure_first.ORIGINAL_CLAIM
    with pytest.raises(ValueError):
        with structure_first.claim_order("buildings"):
            pass


def test_crawl_commands_default_to_structure_first(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        cli, "run_crawler", lambda args, generation, lock: seen.append(args) or 0
    )
    assert cli.main(["--data", str(tmp_path), "backfill"]) == 0
    assert cli.main(
        ["--data", str(tmp_path), "resume", "--claim-order", "original"]
    ) in (0, 3)
    assert seen[0].claim_order == "structure-first"
    assert [a.claim_order for a in seen] == ["structure-first", "original"]


def test_indexed_candidate_matches_the_sort(tmp_path):
    import random

    rng = random.Random(7)
    s = ArchiveStore(tmp_path)
    g = s.new_generation()
    setup(s, g)
    kinds = ["directory", "building", "inventory", "listing", "sitemap", "search"]
    urls = [f"https://streeteasy.com/building/b{i % 9}/u{i}" for i in range(400)]
    s.enqueue(g, [{"url": u, "kind": rng.choice(kinds)} for u in urls])
    for u in urls:
        r = rng.random()
        if r < 0.1:
            s.db.execute("UPDATE frontier SET state='done' WHERE url=?", (u,))
        elif r < 0.2:
            s.db.execute("UPDATE frontier SET next_attempt=1e12 WHERE url=?", (u,))
        elif r < 0.3:
            s.db.execute(
                "UPDATE frontier SET listing_key='k'||(rowid % 5) WHERE url=?", (u,)
            )
        elif r < 0.33:
            s.db.execute(
                "UPDATE frontier SET state='inflight', listing_key='k1' WHERE url=?",
                (u,),
            )
        if rng.random() < 0.7:
            s.db.execute("INSERT OR IGNORE INTO scope_urls VALUES(?,?,'t')", (g, u))
    checked = 0
    for scoped in (False, True):
        for prefix in (None, "https://streeteasy.com/building/b3"):
            for inv in (False, True):
                for units in (False, True):
                    s.db.execute("SAVEPOINT drain")
                    while True:
                        a = (s, g, 1e9, prefix, scoped, inv, units)
                        old = structure_first._sorted_candidate(*a)
                        new = structure_first._indexed_candidate(*a)
                        assert (old and old["url"]) == (new and new["url"])
                        if old is None:
                            break
                        checked += 1
                        s.db.execute(
                            "UPDATE frontier SET state='inflight' WHERE url=?",
                            (old["url"],),
                        )
                    s.db.execute("ROLLBACK TO drain")
                    s.db.execute("RELEASE drain")
    assert checked > 500
    s.db.execute(
        "INSERT INTO frontier(generation,url,kind) VALUES(?,?,'closing')", (g, "x")
    )
    assert structure_first._other_kinds_pending(s, g)
    s.close()
