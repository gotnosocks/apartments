import inspect

from streeteasy_archive import structure_first
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
        ArchiveStore.claim,
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
        old = drain(tmp_path / ("old-" + name), ArchiveStore.claim, rows, **kwargs)
        assert new == old


def test_filter_matches_store_claim():
    """The copy must track ArchiveStore.claim's candidate filter and its tie-breaks."""

    def sql(fn):
        src = inspect.getsource(fn)
        src = src[src.index("SELECT f.*") : src.index("LIMIT 1")]
        src = "\n".join(line.split("--")[0] for line in src.splitlines())
        return " ".join(src.replace('"""', "").replace("+", "").split())

    original = sql(ArchiveStore.claim)
    copy = sql(structure_first.claim_structure_first).replace(" STRUCTURE_RANK ,", "")
    assert copy == original


def test_install_replaces_claim(monkeypatch):
    monkeypatch.setattr(ArchiveStore, "claim", ArchiveStore.claim)
    structure_first.install()
    assert ArchiveStore.claim is structure_first.claim_structure_first
