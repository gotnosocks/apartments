from apartments.attribute_evidence import extract_attribute_evidence as extract
import pytest


def test_nested_structured_evidence_and_compatibility():
    raw = {'propertyDetails': {'bedroomCount': 0, 'fullBathroomCount': 1, 'halfBathroomCount': 1,
           'features': {'list': ['WASHER_DRYER'], 'views': ['GARDEN']},
           'amenities': {'list': ['DOORMAN', 'LAUNDRY'], 'doormanTypes': ['FULL_TIME'],
                         'sharedOutdoorSpaceTypes': ['COURTYARD']}}}
    result = extract(raw)
    a = result['attributes']
    assert a['bedrooms'] == 0 and a['bathrooms'] == 1.5
    assert a['laundry_type'] == 'in_unit' and a['doorman_type'] == 'full_time'
    assert a['view_exposures']['garden'] is True
    assert a['view_exposures']['courtyard'] is None
    assert not result['conflicts']
    assert any(e['source_path'] == '/propertyDetails/amenities/doormanTypes/0' and e['literal'] == 'FULL_TIME' for e in result['evidence'])


def test_absence_unit_number_and_history_never_supply_attributes():
    result = extract({'propertyDetails': {'address': {'displayUnit': '#14A'},
                      'features': {'list': []}, 'amenities': {'list': []}},
                      'propertyHistory': [{'bedroomCount': 2}], 'latestListing': {'floor': 14}})
    assert all(v is None for k, v in result['attributes'].items() if not isinstance(v, dict))
    assert not result['evidence']


def test_negation_conflict_and_literal_offsets():
    desc = 'No elevator. Pets are not allowed. North-facing windows; no courtyard views.'
    result = extract({'propertyDetails': {'amenities': {'list': ['ELEVATOR']}}, 'description': desc})
    assert result['attributes']['elevator'] is None
    assert result['conflicts']['elevator'] == [True, False]
    assert result['attributes']['pet_policy'] == 'not_allowed'
    assert result['attributes']['window_exposures']['north'] is True
    assert result['attributes']['view_exposures']['courtyard'] is False
    for evidence in result['evidence']:
        if evidence['method'] == 'description_pattern':
            assert desc[evidence['start']:evidence['end']] == evidence['literal']


@pytest.mark.parametrize('phrase', ['non-elevator', 'non elevator', 'non–elevator', 'non—elevator', 'non- elevator'])
def test_non_elevator_denial_is_not_a_positive_claim(phrase):
    text = f'It is one flight up in a {phrase} building.'
    result = extract({'description': text})
    assert result['attributes']['elevator'] is False
    assertions = [e for e in result['evidence'] if e['attribute'] == 'elevator']
    assert len(assertions) == 1 and assertions[0]['value'] is False
    assert phrase in assertions[0]['literal']
    assert text[assertions[0]['start']:assertions[0]['end']] == assertions[0]['literal']
    conflicting = extract({'description': text, 'propertyDetails': {'amenities': {'list': ['ELEVATOR']}}})
    assert conflicting['attributes']['elevator'] is None
    assert conflicting['conflicts']['elevator'] == [True, False]


def test_unrelated_non_prefix_does_not_negate_an_elevator():
    assert extract({'description': 'Non-smoking building with an elevator.'})['attributes']['elevator'] is True
    assert extract({'description': 'An elevator in a non-doorman building.'})['attributes']['elevator'] is True
    assert extract({'description': 'This is not a non-elevator building.'})['attributes']['elevator'] is None


def test_unit_floor_and_exposure_are_distinct_from_amenity_copy():
    result = extract({'description': 'This apartment is on the 14th floor. The second floor gym has west-facing windows. Rooftop terrace offers city views. Courtyard-facing windows. South-facing windows.'})
    a = result['attributes']
    assert a['advertised_floor'] == 14
    assert a['physical_floor'] is None and a['floors_above_ground'] is None
    assert a['window_exposures']['west'] is None
    assert a['view_exposures']['city'] is None
    assert a['view_exposures']['courtyard'] is True
    assert a['window_exposures']['south'] is True


def test_unresolved_description_and_unknown_shape():
    assert extract({'description': '$3f'})['warnings'] == ['unresolved_description_reference']
    assert extract({'description': {'text': 'elevator'}})['warnings'] == ['unsupported_description_shape']


def test_uncertain_negated_optional_and_installation_not_positive():
    a = extract({'description': 'No in-unit laundry. Central AC may be installed. Washer and dryer in the unit hookups. Pets allowed upon approval. Not a full-time doorman.'})['attributes']
    assert a['laundry_type'] is None and a['hvac_type'] is None and a['doorman_type'] is None
    assert a['pet_policy'] == 'approval_required'


def test_explicit_floors_conflict_without_inference():
    result = extract({'propertyDetails': {'floor': 14, 'physicalFloor': 13, 'floorsAboveGround': 12},
                      'description': 'This apartment is on the 15th floor.'})
    assert result['attributes']['advertised_floor'] is None
    assert result['attributes']['physical_floor'] == 13
    assert result['attributes']['floors_above_ground'] == 12
    assert result['conflicts']['advertised_floor'] == [14, 15]


def test_non_finite_numbers_and_incomplete_bathroom_count_are_unknown():
    a = extract({'propertyDetails': {'bedroomCount': True, 'livingAreaSize': float('nan'), 'fullBathroomCount': 1}})['attributes']
    assert a['bedrooms'] is None and a['square_feet'] is None and a['bathrooms'] is None


def test_service_and_hvac_conflicts_remain_visible():
    result = extract({'propertyDetails': {'features': {'list': ['CENTRAL_AC']}, 'amenities': {'doormanTypes': ['FULL_TIME', 'PART_TIME']}},
                      'description': 'Ductless air conditioning.'})
    assert result['attributes']['doorman_type'] is None
    assert result['attributes']['hvac_type'] is None
    assert set(result['conflicts']) == {'doorman_type', 'hvac_type'}


def test_subtype_negation_preserves_conflict_and_not_other_type_absence():
    result = extract({'propertyDetails': {'features': {'list': ['CENTRAL_AC', 'WASHER_DRYER']}},
                      'description': 'No central air conditioning. No in-unit laundry.'})
    assert result['attributes']['hvac_type'] is None
    assert result['attributes']['laundry_type'] is None
    assert result['conflicts']['hvac_type'] == ['central_ac', 'not:central_ac']
    assert result['conflicts']['laundry_type'] == ['in_unit', 'not:in_unit']
    a = extract({'propertyDetails': {'amenities': {'list': ['LAUNDRY']}},
                 'description': 'No in-unit laundry. No central air conditioning.'})['attributes']
    assert a['laundry_type'] == 'in_building'
    assert a['hvac_type'] is None


def test_common_section_scope_survives_newlines_and_resets_at_unit_heading():
    # Snapshot 1898 incorrectly assigned a community terrace's skyline view.
    desc = ('Apartment Features\nNorth-facing windows\n\nCommunity Amenities\n'
            'Resident lounge with kitchen for entertaining\n'
            '8th floor terrace with Hudson River and skyline views\n'
            'On-site laundry\n\nApartment Features\nSouth-facing windows')
    out = extract({'description': desc})
    assert out['attributes']['view_exposures']['skyline'] is None
    assert out['attributes']['window_exposures']['north'] is True
    assert out['attributes']['window_exposures']['south'] is True
    assert out['attributes']['laundry_type'] == 'in_building'
    html = 'Community Amenities:<br />8th floor terrace with skyline views'
    assert extract({'description': html})['attributes']['view_exposures']['skyline'] is None


def test_mixed_central_and_wall_mounted_split_copy_is_ambiguous():
    # Snapshots 1379 and 1400 use this exact contradictory equipment description.
    out = extract({'description': '- CENTRAL A/C Wall Mounted Split Unit'})
    assert out['attributes']['hvac_type'] is None
    assert 'hvac_type' in out['conflicts']
    assert out['warnings'] == ['ambiguous_central_vs_wall_mounted_split']
    assert out['evidence'][0]['ambiguous_equipment_description'] == '- CENTRAL A/C Wall Mounted Split Unit'
    assert extract({'description': 'Central A/C throughout the apartment.'})['attributes']['hvac_type'] == 'central_ac'


def test_coordinated_cardinal_exposures_preserve_partial_unknowns():
    # Source snapshots 3095, 4974, 2024, and 3401.
    examples = [
        ('Northern and Eastern exposure from lots of windows.', ('north', 'east')),
        ('South/West exposure.', ('south', 'west')),
        ('8 large windows facing north, south and west.', ('north', 'south', 'west')),
        ('North, South and East facing windows, lots of light!', ('north', 'south', 'east')),
    ]
    for description, positive in examples:
        out = extract({'description': description})
        directions = out['attributes']['window_exposures']
        assert {key for key, value in directions.items() if value is True} == set(positive)
        assert all(directions[key] is None for key in directions.keys() - set(positive))
        for evidence in out['evidence']:
            assert description[evidence['start']:evidence['end']] == evidence['literal']
    out = extract({'description': 'North entrance and south-facing windows.'})
    assert out['attributes']['window_exposures']['north'] is None
    assert out['attributes']['window_exposures']['south'] is True


def test_coordinated_directions_respect_negation_and_common_scope():
    out = extract({'description': 'No north and south exposures. Community Amenities\nEast and west facing windows.'})
    assert out['attributes']['window_exposures']['north'] is False
    assert out['attributes']['window_exposures']['south'] is False
    assert out['attributes']['window_exposures']['east'] is None
    assert out['attributes']['window_exposures']['west'] is None


def test_case_by_case_pet_policies_and_hyphenated_prohibition():
    # Source snapshots 1150/1152/1197 and 2024.
    for text in ('Pets allowed on a case-by-case basis.', 'Pets Allowed, case-by-case',
                 'Pets are allowed subject to board approval.'):
        assert extract({'description': text})['attributes']['pet_policy'] == 'approval_required'
    assert extract({'description': 'Sorry no-pets.'})['attributes']['pet_policy'] == 'not_allowed'
    assert extract({'description': 'Pets are welcome.'})['attributes']['pet_policy'] == 'allowed_restrictions_unknown'


def test_stacked_in_unit_laundry_and_optional_connection():
    assert extract({'description': 'In unit stacked washer/dryer in dedicated laundry room.'})['attributes']['laundry_type'] == 'in_unit'
    assert extract({'description': 'In unit stacked washer/dryer connections.'})['attributes']['laundry_type'] is None


def test_neighborhood_walking_directions_do_not_establish_walkup_building():
    # Recovered snapshot 70528: a supermarket route, not an apartment amenity.
    text = 'A two-minute walk up Ninth Avenue will get you to Gristedes, a local supermarket.'
    assert extract({'description': text})['attributes']['elevator'] is None
    assert extract({'description': 'Walk up to the roof for sunset.'})['attributes']['elevator'] is None
    assert extract({'description': 'This unit is on the 2nd floor - walk up one flight.'})['attributes']['elevator'] is False
    assert extract({'description': 'Apartment in a walk-up building.'})['attributes']['elevator'] is False


def test_hvac_permission_is_not_installed_equipment():
    # Recovered snapshot 44049 permits a tenant's equipment; it does not supply it.
    text = 'Thru the wall, or window a/c units are permitted. Heat is central.'
    assert extract({'description': text})['attributes']['hvac_type'] is None
    assert extract({'description': 'Window air conditioners are allowed.'})['attributes']['hvac_type'] is None
    assert extract({'description': 'Window air conditioning is installed. Pets are permitted.'})['attributes']['hvac_type'] == 'room_ac'


def test_some_building_residences_do_not_establish_this_units_view():
    # Recovered snapshot 22244 uses generic portfolio copy.
    text = 'Many of the residences offer expansive city views of the Empire State Building and Downtown Manhattan.'
    assert extract({'description': text})['attributes']['view_exposures']['city'] is None
    assert extract({'description': 'Select apartments have south-facing windows.'})['attributes']['window_exposures']['south'] is None
    assert extract({'description': 'This residence offers expansive city views.'})['attributes']['view_exposures']['city'] is True


def test_ambiguous_roof_deck_headline_does_not_supply_unit_views():
    # Recovered snapshots 20975 and 63615 have this unlabeled mixed-feature block.
    for heading in ("CHELSEA'S FINEST ROOF DECK", 'CHELSEA’S FINEST ROOF DECK'):
        text = heading+'\n\nOpen River & City Views\nWasher/Dryer in Unit'
        result = extract({'description': text})
        assert result['attributes']['view_exposures']['city'] is None
        assert result['attributes']['laundry_type'] == 'in_unit'
        text += '\nApartment Features\nNorth-facing windows and city views.'
        result = extract({'description': text})
        assert result['attributes']['view_exposures']['city'] is True
        assert result['attributes']['window_exposures']['north'] is True


@pytest.mark.parametrize('text', [
    "While the building doesn't have on-site laundry, wash-and-fold services are two blocks away.",
    'The building doesn’t have on-site laundry.',
    'We do not provide on-site laundry.',
    "We don't offer any on-site laundry.",
    'On-site laundry is not available.',
    'On-site laundry isn’t provided.',
    'There is no laundry in the building.',
])
def test_building_laundry_denials_remain_scoped_and_preserve_literals(text):
    out = extract({'description': text})
    assert out['attributes']['laundry_type'] is None
    evidence = [e for e in out['evidence'] if e['attribute'] == 'laundry_type']
    assert evidence and all(e['value'] == 'not:in_building' for e in evidence)
    for e in evidence:
        assert text[e['start']:e['end']] == e['literal']


def test_no_building_laundry_does_not_deny_private_equipment():
    text = "The building doesn't have on-site laundry."
    private = extract({'description': text,
        'propertyDetails': {'features': {'list': ['WASHER_DRYER']}}})
    assert private['attributes']['laundry_type'] == 'in_unit'
    assert not private['conflicts']
    conflict = extract({'description': text,
        'propertyDetails': {'amenities': {'list': ['LAUNDRY']}}})
    assert conflict['attributes']['laundry_type'] is None
    assert conflict['conflicts']['laundry_type'] == ['in_building', 'not:in_building']


def test_nearby_negation_does_not_reverse_affirmed_laundry():
    for text in ("The building doesn't have a gym. On-site laundry is available.",
                 'The building offers on-site laundry; pets are not permitted.'):
        assert extract({'description': text})['attributes']['laundry_type'] == 'in_building'
    # Complex "not only" syntax remains unresolved under the existing scanner;
    # it must not become evidence denying the facility.
    out = extract({'description': 'The building does not only offer on-site laundry, but also a gym.'})
    assert not any(e['value'] == 'not:in_building' for e in out['evidence'])
