"""Rent map clarity (playtest round 3a): base year, area in titles, interval wording."""

from pathlib import Path

ROOT = Path(__file__).parents[2] / "src/apartments/site"
JS = (ROOT / "static/rentmap.js").read_text()
PAGE = (ROOT / "templates/estimates_map.html").read_text()


def test_change_since_a_chosen_year():
    assert '<select id="base-year">' in PAGE
    assert "other <= yi ? [other, yi] : [yi, other]" in JS
    assert "state.base !== yi ? state.base : yi === last ? 0 : last" in JS
    assert "`From ${yearOf(from)} to ${yearOf(to)}" in JS  # a base after the map year


def test_titles_name_the_area_and_interval_is_explained():
    assert 'id="trend-title"' in PAGE and "$('trend-title').textContent" in JS
    assert "not the range of asks" in JS


def test_neighbourhood_growth_caveat_shows_with_an_area():
    assert (
        'id="area-caveat" hidden' in PAGE
        and "the neighbourhood itself only shifts the level" in PAGE
    )
    assert "$('area-caveat').hidden = !state.area;" in JS


def test_the_trend_says_why_it_differs_from_the_median_ask():
    # Playtest round 4 (economist): the model's growth and the raw median ask's differ.
    assert (
        'id="trend-vs-asks"' in PAGE
        and "holds the building and the apartment fixed" in PAGE
    )


def test_the_choices_are_kept_in_the_url():
    # Playtest round 4 (family): a chosen map could not be bookmarked or shared.
    assert "function readUrl()" in JS and "history.replaceState" in JS
    assert "buildControls();\n  readUrl();\n  render();" in JS


def test_trend_explains_growth_against_the_median_ask():
    assert 'id="trend-mix"' in PAGE
    assert "+75% against +83%" in PAGE
