import pytest

from apartments.laundry_measurement import extract


@pytest.mark.parametrize('text,codes,category', [
    ('Laundry on every floor.', [], 'on_floor'),
    ('Every residential floor has a laundry room.', [], 'on_floor'),
    ('Laundry room available on the same floor.', [], 'on_floor'),
    ('Additional laundry machines available on the floor.', [], 'on_floor'),
    ('Laundry is right on the floor just steps away from the apartment.', [], 'on_floor'),
    ('The building laundry room is down the hall from 2B.', [], 'on_floor'),
    ('Complimentary laundry with a brand new washer and dryer on your floor!', [], 'on_floor'),
    ('Laundry and roof deck right on the floor.', [], 'on_floor'),
    ('Residents here enjoy the convenience of a washer/dryer on every floor, as well as a common outdoor terrace.', [], 'on_floor'),
    ('The building has laundry with new machines on every floor, a bike room, and full-time super.', [], 'on_floor'),
    ('Residents have access to a washer and dryer on each residential floor.', [], 'on_floor'),
    ('Laundry with machines on your floor.', [], 'on_floor'),
    ('Laundry with new machines on every floor.', ['WASHER_DRYER'], 'in_unit'),
    ('No laundry with new machines on every floor.', ['LAUNDRY'], None),
    ('Laundry with new machines on every floor will be installed next year.', [], None),
    ('Laundry with new machines on every floor except this one.', [], None),
    ('Laundry with new machines on the floor below.', [], None),
    ('Laundry with new machines and trash disposal on every floor.', [], None),
    ('Residents have access to a washer/dryer on every floor of their duplex.', [], None),
    ('Residents will have access to a washer/dryer on every floor.', [], None),
    ('Residents have access to a washer/dryer on every floor except the first.', [], None),
    ('Residents do not have access to a washer/dryer on every floor.', [], None),
    ('Washer/dryer on every floor of this duplex.', [], None),
    ('Laundry on the floor below the apartment.', [], None),
    ('Laundry with a new washer and dryer on the floor above.', [], None),
    ('Laundry on every floor except this one.', [], None),
    ('Laundry on every floor excluding the ground floor.', [], None),
    ('Laundry on the floor of the basement.', [], None),
    ('Laundry on your floor will be installed next year.', [], None),
    ('Getting your laundry done will be easy with an in-unit washer and dryer.', ['WASHER_DRYER'], 'in_unit'),
    ('A separate room could be utilized as a bedroom with a washer/dryer.', ['WASHER_DRYER'], 'in_unit'),
    ('A washer/dryer and fireplace! What more could you want?', ['WASHER_DRYER'], 'in_unit'),
    ('Residents will enjoy the convenience of an in-home washer and dryer.', ['WASHER_DRYER'], 'in_unit'),
    ('The kitchen will include new appliances with a dishwasher and washer dryer in unit.', ['WASHER_DRYER'], None),
    ('The bathroom will have an elegant shower and in-unit washer/dryer.', ['WASHER_DRYER'], None),
    ('Laundry on every floor.', ['WASHER_DRYER'], 'in_unit'),
    ('No building laundry.', ['WASHER_DRYER'], 'in_unit'),
    ('No building laundry.', ['LAUNDRY'], None),
    ('No Laundry Room On-Site.', ['WASHER_DRYER'], 'in_unit'),
    ('No Laundry Room On-Site.', ['LAUNDRY'], None),
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
    ('Laundry on every floor coming next year.', [], None),
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


def test_shared_room_denial_does_not_establish_private_equipment_absence():
    result = extract({'description': 'No Laundry Room On-Site.'})
    assert result['states'] == {'private': None, 'shared_building': False, 'shared_same_floor': False}
    assert result['most_convenient_reported_option'] is None
