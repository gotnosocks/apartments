"""Rent map clarity (playtest round 3a): base year, area in titles, interval wording."""

from pathlib import Path

ROOT = Path(__file__).parents[2] / "src/apartments/site"
JS = (ROOT / "static/rentmap.js").read_text()
PAGE = (ROOT / "templates/estimates_map.html").read_text()


def test_change_since_a_chosen_year():
    assert '<select id="base-year">' in PAGE
    assert (
        "median(state.bed, state.base)" in JS and "Since ${d.years[state.base]}" in JS
    )


def test_titles_name_the_area_and_interval_is_explained():
    assert 'id="trend-title"' in PAGE and "$('trend-title').textContent" in JS
    assert "not the range of asks" in JS


def test_neighbourhood_growth_caveat_shows_with_an_area():
    assert (
        'id="area-caveat" hidden' in PAGE
        and "the neighbourhood itself only shifts the level" in PAGE
    )
    assert "$('area-caveat').hidden = !state.area;" in JS
