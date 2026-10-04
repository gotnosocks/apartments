"""Phone layout hooks: the classes the narrow-screen CSS relies on."""

from pathlib import Path

CSS = (Path(__file__).parents[2] / "src/apartments/site/static/site.css").read_text()


def test_listing_tables_carry_the_card_layout_hooks(client):
    html = client.get("/listings").get_data(as_text=True)
    assert '<table class="data listings">' in html
    assert 'data-label="Ask"' in html and 'data-label="Price"' in html
    assert 'class="c-place"' in html


def test_minor_columns_and_contained_labels(client):
    html = client.get("/buildings").get_data(as_text=True)
    assert '<table class="data buildings">' in html and "col-minor" in html
    assert ".col-minor { display: none; }" in CSS
    # absolutely positioned labels stay inside the scrolling box
    assert "position: relative" in CSS[CSS.index(".table-wrap {") :][:120]
