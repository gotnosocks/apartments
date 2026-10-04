"""Phone layout, round 2: building units, buildings list, estimate breakdown, map links."""

from pathlib import Path

GROVE = "the-grove-250-west-19th-street-new_york"
JS = (Path(__file__).parents[2] / "src/apartments/site/static/rentmap.js").read_text()


def test_minor_columns_marked_on_building_and_listing_pages(client):
    building = client.get(f"/buildings/{GROVE}").get_data(as_text=True)
    assert 'class="num col-minor">Floor' in building
    listing = client.get("/listings/a1").get_data(as_text=True)
    assert 'class="num col-minor">95% interval' in listing
    buildings = client.get("/buildings").get_data(as_text=True)
    assert 'class="col-minor">Last listed' in buildings


def test_map_buildings_link_to_their_pages():
    assert "function buildingUrl(id)" in JS
    assert "window.location.href = buildingUrl(" in JS
    assert "html('a', { href: buildingUrl(r.b.id) }" in JS
