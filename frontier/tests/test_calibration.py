import numpy as np
import pandas as pd
from rentfrontier import calibration


def frame():
    return pd.DataFrame(
        {
            "unit_id": ["a", "a", "b", "c", "d", "e"],
            "building": [1, 1, 1, 1, 2, 1],
            "period": pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-03-01",
                    "2024-02-01",
                    "2024-02-01",
                    "2024-02-01",
                    "2024-01-01",
                ]
            ),
            "in_fit": [True, False, True, False, False, True],
            "unit_fit_rows": [1, 1, 1, 0, 0, 2],
            "pit": [0.5, 0.95, 0.5, 0.01, 0.5, 0.5],
        }
    )


def test_kinds_split_held_out_rows_by_what_the_fit_saw():
    k = calibration.kinds(frame())
    assert k["held out"].tolist() == [False, True, False, True, True, False]
    assert k["held out, seen unit"].tolist() == [
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    assert k["held out, new unit"].tolist() == [False, False, False, True, False, False]
    assert k["held out, new building"].tolist() == [
        False,
        False,
        False,
        False,
        True,
        False,
    ]
    # Unit a's held-out row is its second listing; c's is its first.
    assert k["first listing"].tolist() == [False, False, False, True, False, False]
    assert k["single listing (LOO)"].tolist() == [
        True,
        False,
        True,
        False,
        False,
        False,
    ]


def test_coverage_counts_pits_inside_the_central_intervals():
    out = calibration.coverage(frame())
    held = out["held out"]
    assert held["rows"] == 3
    assert held["cover_95"] == 2 / 3  # 0.95 and 0.5 inside, 0.01 outside
    assert held["cover_80"] == 1 / 3
    assert np.isclose(held["se_95"], np.sqrt(0.95 * 0.05 / 3))
