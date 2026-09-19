import json

from apartments.corrections import canonical
from apartments.research_pipeline import publish_bundle
from models.floor_elevator_support import summarize, ambiguity_sensitivity, run


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


def test_opposing_claim_sensitivity_removes_whole_building_and_preserves_unknown_only():
    rows = [row(2, 0, 'a', 'opposing'), row(6, 0, 'b', 'opposing'),
            row(None, 1, 'c', 'opposing'), row(4, None, 'd', 'opposing'),
            row(2, 1, 'e', 'lift'), row(8, 1, 'f', 'lift'), row(3, None, 'g', 'unknown')]
    original = summarize(rows)
    assert original['within_building_supported_thresholds'] == [2, 3, 4]
    value = ambiguity_sensitivity(rows)
    assert value['excluded_building_ids'] == ['opposing']
    assert value['excluded'] == {'rows': 4, 'units': 4, 'buildings': 1}
    assert value['excluded_known_floor']['rows'] == 3
    assert value['support']['rows'] == 3
    assert value['support']['within_building_supported_thresholds'] == []
    assert value['support']['elevator_groups'][2]['all']['rows'] == 1
    assert len(rows) == 7


def test_support_witnesses_expose_repeated_unit_and_single_building():
    rows = [row(2, 0, 'a', 'walkup'), row(6, 0, 'b', 'walkup'),
            row(2, 1, 'c', 'lift'), row(6, 1, 'c', 'lift')]
    groups = summarize(rows)['thresholds'][0]['within_group_support']
    assert groups[0]['building_ids_on_both_sides'] == ['walkup']
    assert groups[1]['unit_ids_on_both_sides'] == ['c']


def test_source_only_audit_uses_canonical_alias_without_fabricating_label_candidates(tmp_path):
    source, output = tmp_path/'source', tmp_path/'output'
    rows = [dict(audit_id='a', unit_id='u', building='b', advertised_floor=3, elevator=None),
            dict(audit_id='b', unit_id='v', building='b', advertised_floor=6, elevator=True)]
    publish_bundle(source, {'observations.jsonl': ''.join(canonical(r)+'\n' for r in rows)}, {'version': 'test'})
    manifest = run(source, None, output)
    value = json.loads((output/'support.json').read_text())
    assert value['explicit_source_floor']['floor_levels'] == [3, 6]
    assert 'unvalidated_label_candidate' not in value
    assert manifest['label_audit_manifest_sha256'] is None
    captured = [json.loads(line) for line in (output/'explicit-observations.jsonl').read_text().splitlines()]
    assert captured[0]['floor'] == 3 and captured[0]['elevator'] is None
    assert run(source, None, output) == manifest
