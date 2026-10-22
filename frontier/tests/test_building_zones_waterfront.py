import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_zones_location as bzl
from rentfrontier import building_zones_waterfront as bzw


def test_columns_flag_within_front_km():
    frame = pd.DataFrame({"building": ["a", "b", "c", "d"]})
    parks = pd.DataFrame(
        {"building": ["a", "b", "c"], "water_km": [0.05, 0.15, np.nan]}
    )
    np.testing.assert_array_equal(bzw.columns(frame, parks)[:, 0], [1, 0, 0, 0])


def test_design_appends_waterfront():
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
    m = bzl.design(frame, **loc, **kw)
    d = bzw.design(frame, **loc, **kw)
    assert d.names == list(m.names) + list(bzw.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : len(m.names)], m.x)
    np.testing.assert_array_equal(d.x[:, -1:], bzw.columns(frame, loc["parks"]))
    assert 0 < d.x[:, -1].sum() < len(frame)
    for s in np.unique(d.site):
        assert np.ptp(d.x[d.site == s, -1]) == 0
