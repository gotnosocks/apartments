import streeteasy_archive.neighborhoods  # noqa: F401  (registers flatiron-gramercy-park)
from streeteasy_archive.scope import (
    NEIGHBORHOODS,
    configure,
    directory_page,
    expand,
    neighborhood_seeds,
)
from streeteasy_archive.store import ArchiveStore

NAME = "flatiron-gramercy-park"


def test_flatiron_gramercy_park_is_registered_with_both_areas():
    assert NEIGHBORHOODS[NAME] == (
        {"flatiron", "gramercy-park"},
        {"Flatiron", "Gramercy Park"},
    )
    assert NEIGHBORHOODS["greenwich-village"] == (
        {"greenwich-village"},
        {"Greenwich Village"},
    )
    seeds = neighborhood_seeds(NAME)
    assert "https://streeteasy.com/for-rent/flatiron" in seeds
    assert "https://streeteasy.com/buildings/gramercy-park" in seeds
    assert len(seeds) == 6


def test_scope_keeps_both_areas_and_excludes_nomad(tmp_path):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    configure(store, generation, neighborhood=NAME)
    data = {
        "scripts": [
            {
                "json": [
                    {"areaName": "Flatiron", "urlPath": "/building/flat/1a"},
                    {"areaName": "Gramercy Park", "urlPath": "/building/gram/2b"},
                    {"areaName": "NoMad", "urlPath": "/building/nomad/1a"},
                    {"areaName": "Murray Hill", "urlPath": "/building/murray/1a"},
                ]
            }
        ],
        "links": [
            {"url": "https://streeteasy.com/for-rent/gramercy-park?page=2"},
            {"url": "https://streeteasy.com/for-rent/nomad?page=2"},
        ],
    }
    expand(
        store,
        generation,
        data,
        "https://streeteasy.com/for-rent/gramercy-park",
        neighborhood=NAME,
    )
    urls = {r[0] for r in store.db.execute("SELECT url FROM scope_urls")}
    assert {
        "https://streeteasy.com/building/flat/1a",
        "https://streeteasy.com/building/gram/2b",
    } <= urls
    assert "https://streeteasy.com/for-rent/gramercy-park?page=2" in urls
    assert not any("nomad" in url or "murray" in url for url in urls)
    assert directory_page("https://streeteasy.com/buildings/flatiron?page=3", NAME)
    assert not directory_page("https://streeteasy.com/buildings/nomad", NAME)
    store.close()
