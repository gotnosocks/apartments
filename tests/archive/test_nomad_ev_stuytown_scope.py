import pytest

import streeteasy_archive.neighborhoods  # noqa: F401  (registers the neighborhoods)
from streeteasy_archive.scope import (
    NEIGHBORHOODS,
    configure,
    expand,
    neighborhood_seeds,
)
from streeteasy_archive.store import ArchiveStore

AREAS = {
    "nomad": ("nomad", "NoMad"),
    "east-village": ("east-village", "East Village"),
    "stuyvesant-town-pcv": ("stuyvesant-town", "Stuyvesant Town/PCV"),
}
NAMES = ["NoMad", "East Village", "Stuyvesant Town/PCV", "Gramercy Park", "Kips Bay"]


@pytest.mark.parametrize("name", sorted(AREAS))
def test_registered_with_one_area(name):
    slug, display = AREAS[name]
    assert NEIGHBORHOODS[name] == ({slug}, {display})
    seeds = neighborhood_seeds(name)
    assert f"https://streeteasy.com/for-rent/{slug}" in seeds
    assert f"https://streeteasy.com/buildings/{slug}" in seeds
    assert NEIGHBORHOODS["flatiron-gramercy-park"] == (
        {"flatiron", "gramercy-park"},
        {"Flatiron", "Gramercy Park"},
    )


@pytest.mark.parametrize("name", sorted(AREAS))
def test_scope_keeps_only_its_own_area(tmp_path, name):
    slug, display = AREAS[name]
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    configure(store, generation, neighborhood=name)
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
            for s in ("nomad", "east-village", "stuyvesant-town", "gramercy-park")
        ],
    }
    expand(
        store,
        generation,
        data,
        f"https://streeteasy.com/for-rent/{slug}",
        neighborhood=name,
    )
    urls = {r[0] for r in store.db.execute("SELECT url FROM scope_urls")}
    building = f"https://streeteasy.com/building/b{NAMES.index(display)}/1a"
    assert building in urls
    others = {
        f"https://streeteasy.com/building/b{i}/1a"
        for i, a in enumerate(NAMES)
        if a != display
    }
    assert not urls & others
    assert f"https://streeteasy.com/for-rent/{slug}?page=2" in urls
    assert not any("gramercy-park?page" in u for u in urls)
    store.close()
