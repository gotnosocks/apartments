import dataclasses

import numpy as np
import test_drift as td

from rentfrontier import drift, drift_building_doorman, run


def test_the_manhattan_copy_keeps_the_doorman_column_on_manhattan_rows_only():
    d = td._design()
    names = list(drift_building_doorman.DOORMAN)
    planted = (np.random.default_rng(4).random((len(d.y), 3)) < 0.3).astype(float)
    x = d.x.copy()
    for j, n in enumerate(names):
        x[:, d.names.index(n)] = planted[:, j]
    d = dataclasses.replace(d, x=x)
    out = drift_building_doorman.manhattan_doorman(d)
    manhattan = drift.site_zone(d)[d.site] == drift.ZONES.index("manhattan")
    assert manhattan.any() and not manhattan.all()
    assert out.names == d.names + [f"{n}_manhattan" for n in names]
    for j, n in enumerate(names):
        copy = out.x[:, out.names.index(f"{n}_manhattan")]
        np.testing.assert_array_equal(copy, planted[:, j] * manhattan)
        assert out.count[f"{n}_manhattan"] == int(copy.sum())
    np.testing.assert_array_equal(out.x[:, : len(d.names)], d.x)
    # The copies are building columns, so the sweep draws them with the slow block.
    assert all(n.startswith(drift.Settings().slow_columns) for n in out.names[-3:])


def test_the_model_takes_the_building_models_settings():
    assert drift_building_doorman.LEVEL_DOF == 4.0
    assert drift_building_doorman.GROUPS == ("building",)
    assert drift_building_doorman.NAME == "drift-building-doorman"
    assert (
        '("drift-building-doorman", "drift_building_doorman")'
        in open(run.__file__).read()
    )
