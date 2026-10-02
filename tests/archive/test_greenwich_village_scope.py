import pytest

import streeteasy_archive.neighborhoods  # noqa: F401  (registers greenwich-village)
from streeteasy_archive.cli import main
from streeteasy_archive.scope import (
    NEIGHBORHOODS,
    configure,
    directory_page,
    expand,
    neighborhood_seeds,
)
from streeteasy_archive.store import ArchiveStore


def test_greenwich_village_is_registered_without_changing_existing_scopes():
    assert NEIGHBORHOODS["greenwich-village"] == (
        {"greenwich-village"},
        {"Greenwich Village"},
    )
    assert NEIGHBORHOODS["west-village"] == ({"west-village"}, {"West Village"})
    assert "https://streeteasy.com/for-rent/greenwich-village" in neighborhood_seeds(
        "greenwich-village"
    )


def test_greenwich_village_scope_excludes_noho_and_west_village(tmp_path):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    configure(store, generation, neighborhood="greenwich-village")
    data = {
        "scripts": [
            {
                "json": [
                    {"areaName": "Greenwich Village", "urlPath": "/building/inside/1a"},
                    {"areaName": "Noho", "urlPath": "/building/noho/1a"},
                    {"areaName": "West Village", "urlPath": "/building/wv/1a"},
                ]
            }
        ],
        "links": [
            {"url": "https://streeteasy.com/for-rent/greenwich-village?page=2"},
            {"url": "https://streeteasy.com/for-rent/noho?page=2"},
        ],
    }
    expand(
        store,
        generation,
        data,
        "https://streeteasy.com/for-rent/greenwich-village",
        neighborhood="greenwich-village",
    )
    urls = {r[0] for r in store.db.execute("SELECT url FROM scope_urls")}
    assert "https://streeteasy.com/building/inside/1a" in urls
    assert "https://streeteasy.com/for-rent/greenwich-village?page=2" in urls
    assert not any("noho" in url or "/wv/" in url for url in urls)
    assert directory_page(
        "https://streeteasy.com/buildings/greenwich-village", "greenwich-village"
    )
    assert not directory_page(
        "https://streeteasy.com/buildings/noho", "greenwich-village"
    )
    store.close()


def test_cli_accepts_greenwich_village(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(
            [
                "--data",
                str(tmp_path),
                "resume",
                "--neighborhood",
                "greenwich-village",
                "--help",
            ]
        )
    assert exit_info.value.code == 0
    assert "greenwich-village" in capsys.readouterr().out
