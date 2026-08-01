from apartments.scope import in_scope, normalize_address

TARGETS = {
    "building": {"canonical_address": "130 WEST 15 STREET"},
    "street": {
        "name": "WEST 15 STREET",
        "minimum_house_number": 100,
        "maximum_house_number": 199,
    },
}


def test_normalize_address():
    assert normalize_address("130 W 15th St, Apt 4A") == "130 WEST 15 STREET"
    assert normalize_address("130 West 15 Street #4A") == "130 WEST 15 STREET"


def test_building_scope():
    assert in_scope("130 W 15th St", "building", TARGETS)
    assert not in_scope("132 W 15th St", "building", TARGETS)


def test_street_scope():
    assert in_scope("101 W 15th St", "street", TARGETS)
    assert in_scope("199 West 15 Street", "street", TARGETS)
    assert not in_scope("200 W 15th St", "street", TARGETS)
    assert not in_scope("130 W 16th St", "street", TARGETS)
