import json

import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_parks as bp
from rentfrontier import building_zones_floor as bzm
from rentfrontier import building_zones_parks as bzp


def _square(lon, lat, half):
    ring = [
        [lon - half, lat - half],
        [lon + half, lat - half],
        [lon + half, lat + half],
        [lon - half, lat + half],
        [lon - half, lat - half],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def test_shore_drops_shared_borders():
    # Two squares sharing an edge at lon -73.99: the shared edge is land, the rest shore.
    a = _square(-74.00, 40.70, 0.01)
    b = _square(-73.98, 40.70, 0.01)
    s = bp.shore([a, b])
    x_shared = bp.metres([-73.99], [40.70])[0, 0]
    assert np.abs(s[:, 0] - x_shared).min() > bp.LAND_M * 0.9
    assert len(s) > 100


def test_table_measures_to_edges():
    parks = pd.DataFrame(
        {
            "acres": [5.0, 200.0],
            "geometry": [
                json.dumps(_square(-74.00, 40.70, 0.001)),
                json.dumps(_square(-73.90, 40.70, 0.01)),
            ],
        }
    )
    boroughs = [_square(-73.95, 40.70, 0.2)]
    b = pd.DataFrame({"building": ["x"], "latitude": [40.70], "longitude": [-74.00]})
    t = bp.table(b, parks, boroughs).iloc[0]
    # Inside the small park: 0.001 deg of longitude from its nearest edge.
    np.testing.assert_allclose(t.park_km, 0.001 * bp.M_PER_LON / 1000, rtol=0.05)
    np.testing.assert_allclose(t.big_park_km, 0.09 * bp.M_PER_LON / 1000, rtol=0.02)
    # The shore square reaches 0.15 deg west of the building, its nearest side.
    np.testing.assert_allclose(t.water_km, 0.15 * bp.M_PER_LON / 1000, rtol=0.02)


def test_columns_floor_and_fill():
    parks = pd.DataFrame(
        {
            "building": ["a", "b", "c"],
            "park_km": [0.01, 0.4, 1.0],
            "big_park_km": [1.0, 2.0, 3.0],
            "water_km": [0.2, 0.3, 0.6],
        }
    )
    frame = pd.DataFrame({"building": ["a", "c", "zz"]})
    c = bzp.columns(frame, parks)
    np.testing.assert_allclose(c[:, 0], np.log([bzp.MIN_KM, 1.0, 0.4]))
    np.testing.assert_allclose(c[:, 1], np.log([1.0, 3.0, 2.0]))
    np.testing.assert_allclose(c[:, 2], np.log([0.2, 0.6, 0.3]))


def test_design_appends_parks():
    frame, tables, units, trucks, floors, _ = tbf._design()
    kw = dict(
        units=units,
        trucks=trucks,
        gyms=tbf.tby.gyms_for(frame),
        ages=tbf.tbs.ages_for(frame),
        floors=floors,
        **tables,
    )
    m = bzm.design(frame, **kw)
    blds = frame.building.astype(str).unique()
    parks = pd.DataFrame(
        {
            "building": blds,
            "park_km": np.linspace(0.02, 0.9, len(blds)),
            "big_park_km": np.linspace(0.5, 3.0, len(blds)),
            "water_km": np.linspace(3.0, 0.1, len(blds)),
        }
    )
    d = bzp.design(frame, parks=parks, **kw)
    assert d.names == list(m.names) + list(bzp.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : len(m.names)], m.x)
    new = d.x[:, len(m.names) :]
    for s in np.unique(d.site):
        assert np.ptp(new[d.site == s], axis=0).max() == 0
