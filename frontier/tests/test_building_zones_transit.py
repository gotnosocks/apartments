import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_transit as bt
from rentfrontier import building_zones_mundlak as bzm
from rentfrontier import building_zones_transit as bzt


def test_table_counts_services_in_range():
    st = bt.stops(
        pd.DataFrame(
            {
                "gtfs_latitude": [40.7400, 40.7420, 40.7600],
                "gtfs_longitude": [-74.0000, -74.0000, -74.0000],
                "daytime_routes": ["A C E", "C E L", "1"],
            }
        ),
        pd.DataFrame({"stop_lat": [40.7410], "stop_lon": [-74.0050]}),
    )
    b = pd.DataFrame(
        {
            "building": ["near", "far", "nowhere"],
            "latitude": [40.7405, 40.7600, np.nan],
            "longitude": [-74.0000, -74.0000, -74.0],
        }
    )
    t = bt.table(b, st).set_index("building")
    assert list(t.index) == ["near", "far"]
    # A, C, E, L and PATH; the 1 is 2.2 km north.
    assert t.routes_800m["near"] == 5
    assert t.routes_800m["far"] == 1
    np.testing.assert_allclose(t.station_km["near"], 0.0556, atol=0.002)
    assert t.station_km["far"] < 0.001


def test_columns_floor_and_fill():
    transit = pd.DataFrame(
        {
            "building": ["a", "b", "c"],
            "station_km": [0.01, 0.4, 1.0],
            "routes_800m": [9, 3, 0],
        }
    )
    frame = pd.DataFrame({"building": ["a", "a", "c", "zz"]})
    c = bzt.columns(frame, transit)
    np.testing.assert_allclose(c[:, 0], np.log([bzt.MIN_KM, bzt.MIN_KM, 1.0, 0.4]))
    np.testing.assert_allclose(c[:, 1], np.log1p([9, 9, 0, 3]))


def test_design_appends_transit():
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
    transit = pd.DataFrame(
        {
            "building": blds,
            "station_km": np.linspace(0.1, 1.2, len(blds)),
            "routes_800m": np.arange(len(blds)) % 7,
        }
    )
    d = bzt.design(frame, transit=transit, **kw)
    assert d.names == list(m.names) + list(bzt.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : len(m.names)], m.x)
    new = d.x[:, len(m.names) :]
    for s in np.unique(d.site):
        assert np.ptp(new[d.site == s], axis=0).max() == 0
