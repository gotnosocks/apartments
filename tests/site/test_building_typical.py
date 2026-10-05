"""Building pages: typical rent by bedroom count from the rent map (playtest round 3a)."""

import json

GROVE = "the-grove-250-west-19th-street-new_york"


def write_map(site_root, last_year=2026):
    target = (site_root / "current" / "site.sqlite").resolve().parent / "map.json"
    target.write_text(
        json.dumps(
            {
                "years": [2025, 2026],
                "year_months": [12, 9],
                "interval": "90%",
                "bedrooms": [
                    {"key": "studio", "label": "Studio"},
                    {"key": "1", "label": "1 bedroom"},
                ],
                "buildings": [
                    {"id": GROVE, "first_year": 2019, "last_year": last_year}
                ],
                "rent": {
                    "studio": [[[3000, 3100, 3200], [3100, 3200, 3300]]],
                    "1": [[[4000, 4100, 4200], [4100, 4200, 4300]]],
                },
            }
        )
    )


def test_building_page_shows_typical_rent_by_size(client, site_root):
    write_map(site_root)
    html = " ".join(client.get(f"/buildings/{GROVE}").get_data(as_text=True).split())
    assert 'id="typical-rent"' in html and "Typical rent here, 2026 so far" in html
    assert "$4,200" in html and "$4,100–$4,300" in html
    assert "extrapolation" not in html


def test_extrapolated_building_says_so(client, site_root):
    write_map(site_root, last_year=2020)
    html = " ".join(client.get(f"/buildings/{GROVE}").get_data(as_text=True).split())
    assert "no listings in the fit since 2020" in html


def test_no_map_no_card(client):
    assert 'id="typical-rent"' not in client.get(f"/buildings/{GROVE}").get_data(
        as_text=True
    )
