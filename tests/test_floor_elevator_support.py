from models.floor_elevator_support import summarize


def row(floor, elevator, unit, building):
    return {'floor': floor, 'elevator': elevator, 'unit_id': unit, 'building': building}


def test_support_counts_distinct_units_and_within_building_overlap():
    rows = [row(2, 0, 'a', 'walkup'), row(2, 0, 'a', 'walkup'), row(4, 0, 'b', 'walkup'),
            row(2, 1, 'c', 'lift'), row(8, 1, 'd', 'lift')]
    result = summarize(rows)
    assert result['four_cell_thresholds'] == [2]
    assert result['within_building_supported_thresholds'] == [2]
    assert result['duplicate_interaction_thresholds'] == [4]
    cell = result['thresholds'][0]['cells'][0]['at_or_below']
    assert cell == {'rows': 2, 'units': 1, 'buildings': 1}


def test_unknown_elevator_is_not_walkup_or_elevator():
    rows = [row(2, 0, 'a', 'w'), row(4, 1, 'b', 'e'), row(8, None, 'c', 'x'), row(None, 1, 'd', 'e')]
    result = summarize(rows)
    assert result['four_cell_thresholds'] == []
    assert result['duplicate_interaction_thresholds'] == []
    assert result['elevator_groups'][2]['known_floor']['rows'] == 1
    assert result['elevator_groups'][1]['all']['rows'] == 2
    assert result['elevator_groups'][1]['known_floor']['rows'] == 1


def test_between_building_cells_do_not_establish_within_building_contrasts():
    result = summarize([row(2, 0, 'a', 'a'), row(4, 0, 'b', 'b'),
                        row(2, 1, 'c', 'c'), row(4, 1, 'd', 'd')])
    assert result['four_cell_thresholds'] == [2]
    assert result['within_building_supported_thresholds'] == []


def test_changing_elevator_claim_is_flagged_not_imputed():
    result = summarize([row(2, 0, 'a', 'b'), row(4, 1, 'a', 'b')])
    assert result['contradictory_or_changing_elevator_buildings'] == 1
