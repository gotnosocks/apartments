from copy import deepcopy
import pytest
from models.current_spatial_features import aggregate, bound_building, coordinates, street_candidate


def source():
    return {'id': '12', 'slug': 'demo', 'geoCenter': {'latitude': 40.74, 'longitude': -74.0},
            'latitude': 40.74, 'longitude': -74.0, 'address': {'street': '140 7th Avenue'}}


def test_coordinates_bind_own_building_id_and_slug():
    own = source(); other = deepcopy(own); other['id'] = '99'; other['geoCenter']['latitude'] = 1
    r = bound_building({'buildingId': '12'}, 'https://streeteasy.com/building/demo/3d', [other, own])
    assert r['status'] == 'source_bound' and r['latitude'] == 40.74
    own['slug'] = 'elsewhere'
    assert bound_building({'buildingId': '12'}, 'https://streeteasy.com/building/demo/3d', [own])['status'] == 'building_slug_conflict'


def test_conflicting_coordinate_channels_remain_unknown():
    own = source(); own['latitude'] = 40.75
    assert bound_building({'buildingId': '12'}, 'https://streeteasy.com/building/demo/3d', [own])['status'] == 'invalid_or_conflicting_coordinates'
    assert coordinates({'latitude': True, 'longitude': -74}) is None
    assert coordinates({'latitude': float('nan'), 'longitude': -74}) is None
    own['latitude'] = None
    assert bound_building({'buildingId': '12'}, 'https://streeteasy.com/building/demo/3d', [own])['status'] == 'invalid_or_conflicting_coordinates'


def test_multiple_source_objects_must_agree():
    own = source(); other = deepcopy(own); other['address']['street'] = '141 7th Avenue'
    assert bound_building({'buildingId': '12'}, 'https://streeteasy.com/building/demo/3d', [own, other])['status'] == 'conflicting_building_objects'


@pytest.mark.parametrize('address,expected', [('140 7th Avenue', '7th avenue'),
    ('500-520 West 28th Street', 'west 28th street'), (' 140 Seventh Avenue ', 'seventh avenue'), ('Broadway', None)])
def test_street_candidate_does_not_invent_aliases(address, expected):
    assert street_candidate(address) == expected


def test_building_center_not_weighted_by_advertisement_count():
    a = {'building': 'a', 'unit_id': 'u1', 'status': 'source_bound', 'source_building_id': '1',
         'latitude': 40., 'longitude': -74., 'street_candidate': 'street'}
    b = {**a, 'building': 'b', 'source_building_id': '2', 'unit_id': 'u3', 'latitude': 42.}
    buildings, center = aggregate([a, {**a, 'unit_id': 'u2'}, b])
    assert center['latitude'] == 41 and [r['relative_latitude_degrees'] for r in buildings] == [-1, 1]
    buildings, _ = aggregate([a, {**a, 'latitude': 41.}])
    assert buildings[0]['status'] == 'incomplete_or_conflicting_building_evidence'
