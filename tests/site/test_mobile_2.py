"""Phone layout, round 2: building units and the buildings list."""

from pathlib import Path

GROVE = "the-grove-250-west-19th-street-new_york"


def test_minor_columns_marked_on_building_pages(client):
    building = client.get(f"/buildings/{GROVE}").get_data(as_text=True)
    assert 'class="num col-minor">Floor' in building
    buildings = client.get("/buildings").get_data(as_text=True)
    assert 'class="col-minor">Last listed' in buildings
