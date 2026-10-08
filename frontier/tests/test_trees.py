import numpy as np
import pandas as pd
from rentfrontier import features, trees

# Metres to degrees of latitude.
DEG = 1 / 111_195.0


def test_live_trees_counts_the_census_published_a_week_before():
    lat, lon = 40.74, -74.0
    table = pd.DataFrame(
        [
            (2005, True, lat + 50 * DEG, lon),
            (2005, True, lat - 90 * DEG, lon),
            (2005, False, lat, lon),  # dead
            (2005, True, lat + 110 * DEG, lon),  # too far
            (2015, True, lat + 10 * DEG, lon),
        ],
        columns=["census", "alive", "latitude", "longitude"],
    )
    at = pd.Series(
        pd.to_datetime(
            ["2016-06-07", "2016-06-08", "2017-10-10", "2017-10-11", "2020-01-01"]
        )
    )
    got = trees.live_trees_near([lat] * 5, [lon] * 5, at, table)
    assert np.isnan(got[0])
    assert got[1:].tolist() == [2, 2, 1, 1]


def test_live_trees_without_a_position_is_unknown():
    table = pd.DataFrame(
        [(2005, True, 40.74, -74.0), (2015, True, 40.74, -74.0)],
        columns=["census", "alive", "latitude", "longitude"],
    )
    got = trees.live_trees_near(
        [np.nan, 40.74],
        [np.nan, -74.0],
        pd.Series(pd.to_datetime(["2020-01-01"] * 2)),
        table,
    )
    assert np.isnan(got[0]) and got[1] == 1


def test_trees_set_is_on_point_in_time_pluto():
    assert features.FEATURE_SETS["nb5-trees-v1"].keywords["base"] == "nb5-plutoasof-v3"
    assert features.NB4_SETS["nb5-trees-v1"] == "nb5-plutoasof-v3"
    assert "nb5-trees-v1" in features.PLUTO_RELEASED_SETS
    assert "nb5-trees-v1" in features.TREES
