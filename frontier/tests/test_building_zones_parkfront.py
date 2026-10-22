import json

import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_park_front as bpf
from rentfrontier import building_zones_location as bzl
from rentfrontier import building_zones_parkfront as bzk


def test_columns_flag_within_front_m():
    frame = pd.DataFrame({"building": ["a", "b", "c", "d"]})
    front = pd.DataFrame(
        {"building": ["a", "b", "c"], "park_edge_m": [12.0, 40.0, np.nan]}
    )
    np.testing.assert_array_equal(bzk.columns(frame, front)[:, 0], [1, 0, 0, 0])


def _square(x0, y0, side):
    """A GeoJSON square `side` metres wide with its corner at (x0, y0) metres."""
    f = bpf.frontage

    def pt(x, y):
        return [float(f.LON0 + x / f.M_PER_LON), float(f.LAT0 + y / f.M_PER_LAT)]

    ring = [
        pt(x0, y0),
        pt(x0 + side, y0),
        pt(x0 + side, y0 + side),
        pt(x0, y0 + side),
        pt(x0, y0),
    ]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


def test_table_measures_outline_to_park_edge():
    registry = pd.DataFrame(
        {
            "building": ["near", "far", "nofoot", "lost"],
            "bin": [1000001.0, 1000002.0, 1000000.0, 1000003.0],
        }
    )
    footprints = pd.DataFrame(
        {
            "bin": [1000001, 1000002],
            "geometry": [_square(-50.0, 0.0, 20.0), _square(-300.0, 0.0, 20.0)],
        }
    )
    parks = pd.DataFrame(
        {
            "acres": [40.0, 40.0, 1.0],
            "typecategory": ["Flagship Park", "Parkway", "Playground"],
            "geometry": [
                _square(0.0, 0.0, 400.0),
                _square(-60.0, 50.0, 5.0),
                _square(-280.0, 0.0, 5.0),
            ],
        }
    )
    t = bpf.table(registry, footprints, parks).set_index("building").park_edge_m
    # The near building's east wall stands 30 m from the park. The parkway and the small
    # playground beside the buildings don't count.
    assert 29.0 < t["near"] < 31.0
    assert t["far"] > 250.0
    assert np.isnan(t["nofoot"])
    assert np.isnan(t["lost"])


def test_design_appends_parkfront():
    frame, tables, units, trucks, floors, _ = tbf._design()
    blds = frame.building.astype(str).unique()
    n = len(blds)
    loc = dict(
        transit=pd.DataFrame(
            {
                "building": blds,
                "station_km": np.linspace(0.1, 1.2, n),
                "routes_800m": np.arange(n) % 7,
            }
        ),
        parks=pd.DataFrame(
            {
                "building": blds,
                "park_km": np.linspace(0.02, 0.9, n),
                "big_park_km": np.linspace(0.5, 3.0, n),
                "water_km": np.linspace(3.0, 0.1, n),
            }
        ),
        noise=pd.DataFrame(
            {"building": blds, "noise_per_year": np.linspace(0, 300, n)}
        ),
    )
    kw = dict(
        units=units,
        trucks=trucks,
        gyms=tbf.tby.gyms_for(frame),
        ages=tbf.tbs.ages_for(frame),
        floors=floors,
        **tables,
    )
    front = pd.DataFrame(
        {"building": blds, "park_edge_m": np.where(np.arange(n) % 4 == 0, 20.0, 300.0)}
    )
    m = bzl.design(frame, **loc, **kw)
    d = bzk.design(frame, park_front=front, **loc, **kw)
    assert d.names == list(m.names) + list(bzk.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : len(m.names)], m.x)
    np.testing.assert_array_equal(d.x[:, -1:], bzk.columns(frame, front))
    assert 0 < d.x[:, -1].sum() < len(frame)
    for s in np.unique(d.site):
        assert np.ptp(d.x[d.site == s, -1]) == 0
