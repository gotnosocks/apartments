import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_noise as bn
from rentfrontier import building_zones_floor as bzm
from rentfrontier import building_zones_noise as bzn


def test_table_sums_points_in_radius():
    points = pd.DataFrame(
        {
            "latitude": [40.7000, 40.7010, 40.7100],
            "longitude": [-74.0, -74.0, -74.0],
            "n": [10.0, 6.0, 100.0],
        }
    )
    b = pd.DataFrame(
        {
            "building": ["a", "b", "c"],
            "latitude": [40.7000, 40.7200, np.nan],
            "longitude": [-74.0, -74.0, -74.0],
        }
    )
    t = bn.table(b, points, years=2).set_index("building")
    # The point 111 m north is in range of a; the one 1.1 km north is not.
    assert list(t.index) == ["a", "b"]
    assert t.noise_per_year["a"] == 8.0
    assert t.noise_per_year["b"] == 0.0


def test_columns_fill():
    noise = pd.DataFrame(
        {"building": ["a", "b", "c"], "noise_per_year": [0.0, 9.0, 99.0]}
    )
    frame = pd.DataFrame({"building": ["c", "a", "zz"]})
    np.testing.assert_allclose(bzn.columns(frame, noise)[:, 0], np.log1p([99, 0, 9]))


def test_design_appends_noise():
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
    noise = pd.DataFrame(
        {"building": blds, "noise_per_year": np.linspace(0.0, 300.0, len(blds))}
    )
    d = bzn.design(frame, noise=noise, **kw)
    assert d.names == list(m.names) + list(bzn.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : len(m.names)], m.x)
    new = d.x[:, len(m.names) :]
    for s in np.unique(d.site):
        assert np.ptp(new[d.site == s], axis=0).max() == 0
