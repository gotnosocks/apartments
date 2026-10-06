import math

import numpy as np
import pandas as pd
from rentfrontier import garden


def test_clear_distances_stop_at_walls_and_skip_touching_ones():
    ring = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], float)
    # A wall 20 m north of the north facade, and a party wall touching the east one.
    starts = np.array([[-20, 30], [10.5, -5]], float)
    ends = np.array([[30, 30], [10.5, 15]], float)
    dist = garden.clear_distances(ring, (starts, ends))
    assert np.allclose(dist["north"], 20.0)
    assert np.allclose(dist["south"], 0.3 + garden.OPEN_REACH_M)
    assert np.allclose(dist["east"], 0.5)
    assert garden.openness(dist["north"]) == 20.0
    assert math.isnan(garden.openness(dist["east"]))


def test_labels_and_rear_yard():
    assert garden.label(True, np.nan) == "stated"
    assert garden.label(False, np.nan) == ""
    assert garden.label(False, garden.SHUT_OPEN_M) == "open rear"
    assert garden.label(False, garden.SHUT_OPEN_M - 1) == "walled rear"
    lots = pd.DataFrame(
        {
            "lotdepth": [100, 100, 100, 80],
            "bldgdepth": [70, 0, 100, 102],
            "lottype": ["5", "5", "3", "5"],
        }
    )
    assert garden.rear_yard_ft(lots).tolist()[0] == 30
    assert garden.rear_yard_ft(lots).isna().tolist() == [False, True, True, True]


def test_garden_text():
    hits = pd.Series(
        [
            "bedroom overlooking the garden",
            "lovely garden views",
            "views of the rear yards",
            "garden-level unit",
            "shared garden",
        ]
    ).str.contains(garden.GARDEN_TEXT, regex=True)
    assert hits.tolist() == [True, True, True, False, False]
