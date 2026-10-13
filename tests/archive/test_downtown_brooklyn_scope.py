import pytest

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


AREAS = {
    "downtown-brooklyn": "Downtown Brooklyn",
    "fort-greene": "Fort Greene",
    "boerum-hill": "Boerum Hill",
}


@pytest.mark.parametrize("slug", sorted(AREAS))
def test_registered_with_one_area(slug):
    assert NEIGHBORHOODS[slug] == ({slug}, {AREAS[slug]})
    seeds = neighborhood_seeds(slug)
    assert f"https://streeteasy.com/for-rent/{slug}" in seeds
    assert f"https://streeteasy.com/buildings/{slug}" in seeds
    assert NEIGHBORHOODS["east-village"] == ({"east-village"}, {"East Village"})


@pytest.mark.parametrize("slug", sorted(AREAS))
def test_scope_keeps_only_its_own_area(tmp_path, slug):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    configure(store, generation, neighborhood=slug)
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
            for s in [*AREAS, "brooklyn-heights"]
        ],
    }
    expand(
        store,
        generation,
        data,
        f"https://streeteasy.com/for-rent/{slug}",
        neighborhood=slug,
    )
    urls = {r[0] for r in store.db.execute("SELECT url FROM scope_urls")}
    own = NAMES.index(AREAS[slug])
    assert f"https://streeteasy.com/building/b{own}/1a" in urls
    assert not urls & {
        f"https://streeteasy.com/building/b{i}/1a"
        for i in range(len(NAMES))
        if i != own
    }
    assert f"https://streeteasy.com/for-rent/{slug}?page=2" in urls
    others = [s for s in [*AREAS, "brooklyn-heights"] if s != slug]
    assert not any(f"/{s}?page" in u for u in urls for s in others)
    store.close()


COMBINED = "downtown-brooklyn-fort-greene-boerum-hill"


def test_combined_scope_keeps_all_three(tmp_path):
    assert NEIGHBORHOODS[COMBINED] == (set(AREAS), set(AREAS.values()))
    seeds = neighborhood_seeds(COMBINED)
    for slug in AREAS:
        assert f"https://streeteasy.com/buildings/{slug}" in seeds
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    configure(store, generation, neighborhood=COMBINED)
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
            for s in [*AREAS, "brooklyn-heights"]
        ],
    }
    expand(
        store,
        generation,
        data,
        "https://streeteasy.com/for-rent/fort-greene",
        neighborhood=COMBINED,
    )
    urls = {r[0] for r in store.db.execute("SELECT url FROM scope_urls")}
    keep = {NAMES.index(a) for a in AREAS.values()}
    assert {f"https://streeteasy.com/building/b{i}/1a" for i in keep} <= urls
    assert not urls & {
        f"https://streeteasy.com/building/b{i}/1a"
        for i in range(len(NAMES))
        if i not in keep
    }
    assert {f"https://streeteasy.com/for-rent/{s}?page=2" for s in AREAS} <= urls
    assert not any("brooklyn-heights?page" in u for u in urls)
    store.close()
