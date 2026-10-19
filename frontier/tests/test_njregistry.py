import json

import pandas as pd

from rentfrontier import njregistry


def _square(x0, y0, side=0.0002, hole=None):
    ring = [
        [x0, y0],
        [x0 + side, y0],
        [x0 + side, y0 + side],
        [x0, y0 + side],
        [x0, y0],
    ]
    coordinates = [ring] + ([hole] if hole else [])
    return json.dumps({"type": "Polygon", "coordinates": coordinates})


def _parcels(rows):
    table = pd.DataFrame(rows, columns=["pams_pin", "mun", "address", "geometry"])
    table["lot"] = njregistry.lot_of(table.pams_pin)
    return table


def _buildings(rows):
    columns = ["building", "building_id", "latitude", "longitude", "street", "city"]
    return pd.DataFrame(rows, columns=columns)


def test_address_keys_read_ranges_ordinals_and_slashes():
    keys = njregistry.address_keys
    assert keys("121-125 GARDEN ST") == [
        "121 GARDEN ST",
        "123 GARDEN ST",
        "125 GARDEN ST",
    ]
    assert keys("330-32 VAN HORNE ST.") == ["330 VAN HORNE ST", "332 VAN HORNE ST"]
    assert keys("245 SECOND ST.") == keys("245 2nd Street") == ["245 2 ST"]
    assert keys("1117 GRAND/1118 CLINTON") == ["1117 GRAND", "1118 CLINTON"]
    assert keys("45 RIVER DR.SOUTH") == ["45 RIVER DR S"]
    assert keys("SECAUCUS RD.") == []
    assert keys(None) == []


def test_contains_takes_a_hole_back_out():
    hole = [
        [0.00005, 0.00005],
        [0.00015, 0.00005],
        [0.00015, 0.00015],
        [0.00005, 0.00005],
    ]
    parts = njregistry.rings(_square(0, 0, hole=hole))
    assert njregistry.contains(parts, 0.00002, 0.00018)
    assert not njregistry.contains(parts, 0.00013, 0.00007)
    assert not njregistry.contains(parts, 0.0003, 0.0001)


def test_place_prefers_the_address_and_keys_condos_to_the_lot():
    parcels = _parcels(
        [
            ("0905_13_1", "0905", "78 JACKSON ST", _square(-74.0400, 40.7400)),
            (
                "0905_13_1_C002A",
                "0905",
                "78 JACKSON ST",
                _square(-74.0399, 40.7401, 0.00002),
            ),
            ("0905_13_2", "0905", "80 JACKSON ST", _square(-74.0398, 40.7400)),
        ]
    )
    buildings = _buildings(
        [
            # The point falls in lot 2, the address names lot 1.
            ("78-jackson", "1", 40.7401, -74.0397, "78 Jackson Street", "HOBOKEN"),
            # No lot at 82, so the nearest house number on the same side of the street.
            ("82-jackson", "2", 40.7401, -74.0397, "82 Jackson Street", "Hoboken"),
            # No usable address: the parcel holding the point.
            ("jackson-sq", "3", 40.74005, -74.03975, "Jackson Square", "HOBOKEN"),
            # Off every parcel, within NEAR_M of lot 2.
            ("off-lot", "4", 40.7401, -74.0395, "", "HOBOKEN"),
            ("far", "5", 40.75, -74.03, "", "HOBOKEN"),
            ("no-point", "6", None, None, "", "HOBOKEN"),
        ]
    )
    out = njregistry.place(buildings, parcels).set_index("building")
    assert out.loc["78-jackson", ["method", "lot", "pams_pin"]].tolist() == [
        "address",
        "0905_13_1",
        "0905_13_1",
    ]
    assert out.loc["82-jackson", ["method", "lot"]].tolist() == ["street", "0905_13_2"]
    assert out.loc["jackson-sq", ["method", "lot"]].tolist() == ["parcel", "0905_13_2"]
    assert out.loc["off-lot", "method"] == "near"
    assert 0 < out.loc["off-lot", "distance_m"] <= njregistry.NEAR_M
    assert out.loc["far", "method"] == "none" and pd.isna(out.loc["far", "lot"])
    assert out.loc["no-point", "method"] == "none"


def test_place_keeps_jersey_city_addresses_out_of_hoboken():
    parcels = _parcels(
        [
            ("0905_1_1", "0905", "100 HUDSON ST", _square(-74.0300, 40.7400)),
            ("0906_9_1", "0906", "100 HUDSON ST", _square(-74.0350, 40.7150)),
        ]
    )
    buildings = _buildings(
        [("100-hudson", "1", 40.7401, -74.0299, "100 Hudson St", "JERSEY CITY")]
    )
    out = njregistry.place(buildings, parcels)
    assert out.lot.tolist() == ["0906_9_1"]
