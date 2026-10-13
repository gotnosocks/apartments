import streeteasy_archive.neighborhoods  # noqa: F401  (registers the neighborhoods)
from streeteasy_archive.scope import NEIGHBORHOODS, configure, expand
from streeteasy_archive.store import ArchiveStore

AREAS = {
    "midtown-west": "Midtown West",
    "hudson-yards": "Hudson Yards",
    "hells-kitchen": "Hell's Kitchen",
}
NAMES = [*AREAS.values(), "Chelsea", "Midtown South", "Upper West Side"]


def test_midtown_west_keeps_its_child_areas(tmp_path):
    assert NEIGHBORHOODS["midtown-west"] == (set(AREAS), set(AREAS.values()))
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    configure(store, generation, neighborhood="midtown-west")
    data = {
        "scripts": [
            {
                "json": [
                    {"areaName": a, "urlPath": f"/building/b{i}/1a"}
                    for i, a in enumerate(NAMES)
                ]
            }
        ]
    }
    expand(
        store,
        generation,
        data,
        "https://streeteasy.com/for-rent/midtown-west",
        neighborhood="midtown-west",
    )
    urls = {r[0] for r in store.db.execute("SELECT url FROM scope_urls")}
    found = {
        i
        for i in range(len(NAMES))
        if f"https://streeteasy.com/building/b{i}/1a" in urls
    }
    assert found == {0, 1, 2}
    store.close()
