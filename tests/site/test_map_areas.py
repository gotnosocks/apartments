"""The rent map's neighbourhood choice (map.json median_by_area, rentfrontier #203)."""

import json
import sqlite3
from pathlib import Path

from apartments.site import build

JS = (Path(__file__).parents[2] / "src/apartments/site/static/rentmap.js").read_text()


def test_bundle_map_tags_buildings_with_their_neighbourhood(tmp_path):
    db = sqlite3.connect(tmp_path / "site.sqlite")
    db.execute("CREATE TABLE buildings (id TEXT, neighbourhood TEXT)")
    db.executemany(
        "INSERT INTO buildings VALUES (?, ?)", [("a", "Chelsea"), ("b", "West Village")]
    )
    db.commit()
    db.close()
    source = tmp_path / "in.json"
    source.write_text(
        json.dumps({"buildings": [{"id": "a"}, {"id": "b"}, {"id": "c"}]})
    )
    build.bundle_map(source, tmp_path / "map.json", tmp_path / "site.sqlite")
    out = json.loads((tmp_path / "map.json").read_text())["buildings"]
    assert [b.get("neighbourhood") for b in out] == ["Chelsea", "West Village", None]


def test_bundle_map_on_a_build_without_neighbourhoods(tmp_path):
    db = sqlite3.connect(tmp_path / "site.sqlite")
    db.execute("CREATE TABLE buildings (id TEXT)")
    db.commit()
    db.close()
    source = tmp_path / "in.json"
    source.write_text(json.dumps({"buildings": [{"id": "a"}]}))
    build.bundle_map(source, tmp_path / "map.json", tmp_path / "site.sqlite")
    assert (
        "neighbourhood"
        not in json.loads((tmp_path / "map.json").read_text())["buildings"][0]
    )


def test_map_script_uses_the_chosen_areas_median():
    assert "d.median_by_area && d.median_by_area[state.area]" in JS
    assert "const inArea = (b) => !state.area || b.neighbourhood === state.area;" in JS


def test_rentmaps_own_neighbourhood_wins(tmp_path):
    db = sqlite3.connect(tmp_path / "site.sqlite")
    db.execute("CREATE TABLE buildings (id TEXT, neighbourhood TEXT)")
    db.execute("INSERT INTO buildings VALUES ('a', 'Chelsea')")
    db.commit()
    db.close()
    source = tmp_path / "in.json"
    source.write_text(
        json.dumps({"buildings": [{"id": "a", "neighbourhood": "West Village"}]})
    )
    build.bundle_map(source, tmp_path / "map.json", tmp_path / "site.sqlite")
    out = json.loads((tmp_path / "map.json").read_text())["buildings"]
    assert out[0]["neighbourhood"] == "West Village"
