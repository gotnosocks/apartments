import pytest

from apartments.laundry_measurement import extract


@pytest.mark.parametrize('text,codes,category', [
    ('Laundry on every floor.', [], 'on_floor'),
    ('Every residential floor has a laundry room.', [], 'on_floor'),
    ('Laundry room available on the same floor.', [], 'on_floor'),
    ('Additional laundry machines available on the floor.', [], 'on_floor'),
    ('Laundry is right on the floor just steps away from the apartment.', [], 'on_floor'),
    ('The building laundry room is down the hall from 2B.', [], 'on_floor'),
    ('Laundry on every floor.', ['WASHER_DRYER'], 'in_unit'),
    ('No building laundry.', ['WASHER_DRYER'], 'in_unit'),
    ('No building laundry.', ['LAUNDRY'], None),
    ('No laundry in the unit or the building.', [], 'none'),
    ('No laundry on-site.', [], 'none'),
    ('No laundry.', [], None),
    ('In-unit washer and dryer.', [], 'in_unit'),
    ('In-unit washer.', [], None),
    ('Washer/dryer hookups for tenant installation.', ['WASHER_DRYER'], None),
    ('Washer / Dryer hook up.', ['WASHER_DRYER'], None),
    ('Washer/Dryer hook-up.', ['WASHER_DRYER'], None),
    ('Select apartments have an in-unit washer and dryer.', [], None),
    ('Laundry on the second floor.', [], None),
    ('Roof deck across the hall, common laundry room.', [], 'in_building'),
    ('Laundry nook across the hall from the bedroom.', [], None),
    ('Laundry on every floor is not available.', ['LAUNDRY'], None),
    ('Laundry coming on every floor.', [], None),
    ('', [], None),
    ('$L42', [], None),
])
def test_scoped_laundry_does_not_infer_absence_or_private_dryer(text, codes, category):
    raw = {'description': text, 'propertyDetails': {'features': {'list': codes}}}
    result = extract(raw)
    assert result['most_convenient_reported_option'] == category
    for claim in result['claims']:
        if claim['source_path'] == '/description':
            assert text[claim['start']:claim['end']] == claim['literal']


def test_same_floor_implies_shared_access_but_not_private_equipment():
    result = extract({'description': 'Laundry on every floor.'})
    assert result['states'] == {'private': None, 'shared_building': True, 'shared_same_floor': True}


def test_conflicting_scopes_preserve_all_claims_and_withhold_category():
    result = extract({'description': 'No building laundry. Laundry on every floor.'})
    assert set(result['conflicts']) == {'shared_building', 'shared_same_floor'}
    assert result['most_convenient_reported_option'] is None
    assert len(result['claims']) == 2
