import json

import numpy as np
import pandas as pd

from rentfrontier import frontage as fr


def _street(name, a, b, width_ft, road):
    p, u = fr.densify(np.array([a, b], float), fr.STREET_STEP_M)
    return pd.DataFrame(
        {"x": p[:, 0], "y": p[:, 1], "ux": u[:, 0], "uy": u[:, 1]}
    ).assign(width=width_ft, name=name, road=road)


def _box(x0, x1, y0, y1):
    """A footprint polygon from a box in metres, as GeoJSON in lon/lat."""
    ring = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], float)
    lon = ring[:, 0] / fr.M_PER_LON + fr.LON0
    lat = ring[:, 1] / fr.M_PER_LAT + fr.LAT0
    return json.dumps(
        {"type": "Polygon", "coordinates": [np.column_stack([lon, lat]).tolist()]}
    )


def _toy():
    """A divided boulevard with two 36 ft roadways 40 m apart along y = 0 and y = 40, a 30 ft
    side street running south from it along x = 0, and buildings around them."""
    streets = pd.concat(
        [
            _street("BIG BLVD", (-300, 0), (300, 0), 36.0, 0),
            _street("BIG BLVD", (-300, 40), (300, 40), 36.0, 1),
            _street("SIDE ST", (0, -300), (0, 0), 30.0, 2),
        ],
        ignore_index=True,
    )
    boxes = {
        "1": (100, 130, -40, -12),  # on the boulevard only
        "2": (6, 30, -40, -12),  # at the boulevard and the side street
        "3": (6, 30, -40, -12),  # the same spot, an inside lot in PLUTO
        "4": (15, 35, -150, -130),  # 15 m back from the side street
        "5": (26, 40, -150, -130),  # 26 m back from the side street
        "6": (100, 130, -40, -12),  # a placeholder BIN
    }
    registry = pd.DataFrame(
        {
            "building": list(boxes),
            "bin": ["1000001", "1000002", "1000003", "1000004", "1000005", "1000000"],
            "bbl": ["1000010001", "1000010002", "1000010003", "1000010004", "1000010005", "1000010006"],
        }
    )  # fmt: skip
    footprints = pd.DataFrame(
        {
            "bin": registry.bin[:5],
            "geometry": [_box(*boxes[b]) for b in list(boxes)[:5]],
        }
    )
    pluto = pd.DataFrame(
        {"bbl": registry.bbl[:5], "lottype": ["5", "0", "5", "3", "0"]}
    )
    return fr.frontage(registry, footprints, streets, pluto).set_index("building")


def test_adds_up_the_roadways_of_a_divided_street():
    f = _toy()
    assert f.at["1", "front_width_ft"] == 72.0
    assert f.at["1", "front_street"] == "BIG BLVD"
    assert f.at["2", "front_width_ft"] == 72.0


def test_reach_finds_streets_and_adds_nothing_to_width():
    f = _toy()
    # 15 m back is within the street's half width plus REACH_M; 26 m back is not.
    assert f.at["4", "front_width_ft"] == 30.0
    assert np.isnan(f.at["5", "front_width_ft"])
    assert np.isnan(f.at["6", "front_width_ft"])


def test_corner_from_pluto_then_geometry():
    f = _toy()
    assert (f.at["1", "corner"], f.at["1", "corner_source"]) == (0.0, "pluto")
    assert (f.at["2", "corner"], f.at["2", "corner_source"]) == (1.0, "geometry")
    assert (f.at["3", "corner"], f.at["3", "corner_source"]) == (0.0, "pluto")
    assert (f.at["4", "corner"], f.at["4", "corner_source"]) == (1.0, "pluto")
    assert (f.at["5", "corner"], f.at["5", "corner_source"]) == (0.0, "geometry")
    assert np.isnan(f.at["6", "corner"]) and f.at["6", "corner_source"] == "unknown"
