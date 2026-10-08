import numpy as np
import pandas as pd
from rentfrontier import crime, features

# Metres to degrees of latitude.
DEG = 1 / 111_195.0


def test_felonies_reported_in_the_year_before_the_listing():
    lat, lon = 40.74, -74.0
    table = pd.DataFrame(
        [
            ("2010-01-01", lat + 300 * DEG, lon),  # too far
            ("2010-01-01", lat, lon),  # sets the table's first day
            ("2011-03-01", lat + 100 * DEG, lon),
            ("2011-06-01", lat - 200 * DEG, lon),
            ("2011-06-02", lat, lon),  # the listing's own day: not before it
            ("2012-12-31", lat, lon),  # sets the table's last day
        ],
        columns=["rpt_dt", "latitude", "longitude"],
    )
    at = pd.Series(
        pd.to_datetime(
            [
                "2010-06-01",  # the year before starts before the table
                "2011-06-02",
                "2012-03-01",  # 2011-03-01 is 366 days before
                "2012-06-02",
                "2013-01-01",
                "2013-01-02",  # past the table
            ]
        )
    )
    got = crime.felonies_near([lat] * 6, [lon] * 6, at, table)
    assert np.isnan(got[0]) and np.isnan(got[5])
    assert got[1:5].tolist() == [2, 2, 0, 1]


def test_felonies_without_a_position_is_unknown():
    table = pd.DataFrame(
        [("2010-01-01", np.nan, np.nan), ("2011-01-01", 40.74, -74.0)],
        columns=["rpt_dt", "latitude", "longitude"],
    )
    got = crime.felonies_near(
        [np.nan, 40.74],
        [np.nan, -74.0],
        pd.Series(pd.to_datetime(["2011-01-02"] * 2)),
        table,
    )
    assert np.isnan(got[0]) and got[1] == 1


def test_crime_set_is_on_point_in_time_pluto():
    assert features.FEATURE_SETS["nb5-crime-v1"].keywords["base"] == "nb5-plutoasof-v3"
    assert features.NB4_SETS["nb5-crime-v1"] == "nb5-plutoasof-v3"
    assert "nb5-crime-v1" in features.PLUTO_RELEASED_SETS
    assert "nb5-crime-v1" in features.CRIME
