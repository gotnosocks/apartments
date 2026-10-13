import streeteasy_archive.neighborhoods  # noqa: F401  (registers the neighborhoods)
from streeteasy_archive.scope import (
    NEIGHBORHOODS,
    configure,
    expand,
    neighborhood_seeds,
)
from streeteasy_archive.store import ArchiveStore

NAMES = [
    "Downtown Brooklyn",
    "Brooklyn Heights",
    "DUMBO",
    "Boerum Hill",
    "Fort Greene",
    "East Village",
]


def test_registered_with_one_area():
    assert NEIGHBORHOODS["downtown-brooklyn"] == (
        {"downtown-brooklyn"},
        {"Downtown Brooklyn"},
    )
    seeds = neighborhood_seeds("downtown-brooklyn")
    assert "https://streeteasy.com/for-rent/downtown-brooklyn" in seeds
    assert "https://streeteasy.com/buildings/downtown-brooklyn" in seeds
    assert NEIGHBORHOODS["east-village"] == ({"east-village"}, {"East Village"})


def test_scope_keeps_only_downtown_brooklyn(tmp_path):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    configure(store, generation, neighborhood="downtown-brooklyn")
    data = {
        "scripts": [
            {
                "json": [
                    {"areaName": a, "urlPath": f"/building/b{i}/1a"}
                    for i, a in enumerate(NAMES)
                ]
            }
        ],
        "links": [
            {"url": f"https://streeteasy.com/for-rent/{s}?page=2"}
            for s in ("downtown-brooklyn", "brooklyn-heights", "boerum-hill")
        ],
    }
    expand(
        store,
        generation,
        data,
        "https://streeteasy.com/for-rent/downtown-brooklyn",
        neighborhood="downtown-brooklyn",
    )
    urls = {r[0] for r in store.db.execute("SELECT url FROM scope_urls")}
    assert "https://streeteasy.com/building/b0/1a" in urls
    assert not urls & {
        f"https://streeteasy.com/building/b{i}/1a" for i in range(1, len(NAMES))
    }
    assert "https://streeteasy.com/for-rent/downtown-brooklyn?page=2" in urls
    assert not any(
        "brooklyn-heights?page" in u or "boerum-hill?page" in u for u in urls
    )
    store.close()
