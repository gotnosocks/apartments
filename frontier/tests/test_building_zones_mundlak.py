import numpy as np

import test_building_zones_floor as tbf
from rentfrontier import building_zones_mundlak as bzm


def test_columns_are_building_means():
    names = [
        "unit:log_size_rel",
        "unit:laundry_in_unit",
        "unit:elev_f2",
        "unit:elev_f3",
        "unit:elev_floor_unknown",
    ]
    x = np.array(
        [
            [0.2, 1, 1, 0, 0],
            [-0.4, 0, 0, 1, 0],
            [0.0, 1, 0, 0, 1],
            [0.5, 0, 0, 0, 0],
            [0.1, 1, 0, 0, 1],
        ]
    )
    site = np.array([0, 0, 0, 1, 2])
    c = dict(zip(bzm.COLUMNS, bzm.columns(x, names, site).T))
    np.testing.assert_allclose(c["bld:mean_log_size_rel"], [-0.2 / 3] * 3 + [0.5, 0.1])
    np.testing.assert_allclose(c["bld:mean_laundry_in_unit"], [2 / 3] * 3 + [0, 1])
    np.testing.assert_allclose(c["bld:mean_floor_unknown"], [1 / 3] * 3 + [0, 1])
    assert np.all(c["bld:mean_dishwasher"] == 0)
    # Known floors are 2, 3 and 1; the third building has none and gets their mean.
    fill = np.log([2, 3, 1]).mean()
    np.testing.assert_allclose(
        c["bld:mean_log_floor"],
        [np.log(6) / 2] * 3 + [0, fill],
    )


def test_design_appends_means_constant_within_buildings():
    frame, tables, units, trucks, floors, d = tbf._design()
    m = bzm.design(
        frame,
        units=units,
        trucks=trucks,
        gyms=tbf.tby.gyms_for(frame),
        ages=tbf.tbs.ages_for(frame),
        floors=floors,
        **tables,
    )
    assert m.names == list(d.names) + list(bzm.COLUMNS)
    np.testing.assert_array_equal(m.x[:, : len(d.names)], d.x)
    new = m.x[:, len(d.names) :]
    for s in np.unique(m.site):
        assert np.ptp(new[m.site == s], axis=0).max() == 0
    j = d.names.index("unit:laundry_in_unit")
    k = m.names.index("bld:mean_laundry_in_unit")
    np.testing.assert_allclose(
        np.bincount(m.site, m.x[:, k]), np.bincount(m.site, d.x[:, j])
    )
