import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_zones_floor as bzm
from rentfrontier import building_zones_location as bzl
from rentfrontier import building_zones_noise as bzn
from rentfrontier import building_zones_parks as bzp
from rentfrontier import building_zones_transit as bzt


def test_design_appends_all_three():
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
    n = len(blds)
    transit = pd.DataFrame(
        {
            "building": blds,
            "station_km": np.linspace(0.1, 1.2, n),
            "routes_800m": np.arange(n) % 7,
        }
    )
    parks = pd.DataFrame(
        {
            "building": blds,
            "park_km": np.linspace(0.02, 0.9, n),
            "big_park_km": np.linspace(0.5, 3.0, n),
            "water_km": np.linspace(3.0, 0.1, n),
        }
    )
    noise = pd.DataFrame({"building": blds, "noise_per_year": np.linspace(0, 300, n)})
    d = bzl.design(frame, transit=transit, parks=parks, noise=noise, **kw)
    assert d.names == list(m.names) + list(bzl.COLUMNS)
    assert list(bzl.COLUMNS) == [*bzt.COLUMNS, *bzp.COLUMNS, *bzn.COLUMNS]
    np.testing.assert_array_equal(d.x[:, : len(m.names)], m.x)
    k = len(m.names)
    # Each block matches its single-feature model's columns.
    for module, t in ((bzt, transit), (bzp, parks), (bzn, noise)):
        w = len(module.COLUMNS)
        np.testing.assert_array_equal(d.x[:, k : k + w], module.columns(frame, t))
        k += w
    new = d.x[:, len(m.names) :]
    for s in np.unique(d.site):
        assert np.ptp(new[d.site == s], axis=0).max() == 0
