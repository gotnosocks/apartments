import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_zones_avenue as bzv
from rentfrontier import building_zones_location as bzl


def test_columns_flag_wide_midblock_only():
    frame = pd.DataFrame({"building": ["a", "b", "c", "d", "e", "f"]})
    frontage = pd.DataFrame(
        {
            "building": ["a", "b", "c", "d", "e"],
            "front_width_ft": [70.0, 70.0, 30.0, np.nan, 61.0],
            "corner": [0.0, 1.0, 0.0, 0.0, np.nan],
        }
    )
    np.testing.assert_array_equal(
        bzv.columns(frame, frontage)[:, 0], [1, 0, 0, 0, 0, 0]
    )


def test_design_appends_avenue():
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
    frontage = pd.DataFrame(
        {
            "building": blds,
            "front_width_ft": np.where(np.arange(n) % 3 == 0, 70.0, 30.0),
            "corner": (np.arange(n) % 2).astype(float),
        }
    )
    m = bzl.design(frame, **loc, **kw)
    d = bzv.design(frame, frontage=frontage, **loc, **kw)
    assert d.names == list(m.names) + list(bzv.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : len(m.names)], m.x)
    np.testing.assert_array_equal(d.x[:, -1:], bzv.columns(frame, frontage))
    assert 0 < d.x[:, -1].sum() < len(frame)
    for s in np.unique(d.site):
        assert np.ptp(d.x[d.site == s, -1]) == 0
