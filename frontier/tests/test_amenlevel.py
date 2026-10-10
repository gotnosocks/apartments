import numpy as np
import pandas as pd

from rentfrontier import features


def frame(rents, days, buildings, beds):
    return pd.DataFrame(
        {
            "price_at": pd.Timestamp("2024-01-01", tz="UTC")
            + pd.to_timedelta(days, unit="D"),
            "log_rent": np.log(rents),
            "building": buildings,
            "bedrooms": beds,
        }
    )


def test_level_reads_only_asks_dated_a_week_before():
    f = frame(
        [3000.0, 4000.0, 3500.0, 5000.0, 9000.0],
        [0, 10, 30, 31, 60],
        ["a", "b", "a", "a", "a"],
        [1, 1, 1, 1, 1],
    )
    level = features.building_level_asof(f)
    later = f.copy()
    later.loc[4, "log_rent"] = np.log(1.0)  # the last ask changes nothing before it
    assert np.allclose(features.building_level_asof(later)[:4], level[:4])
    own = f.copy()
    own.loc[3, "log_rent"] = np.log(1.0)  # nor its own covariate
    assert features.building_level_asof(own)[3] == level[3]
    # Row 2 (day 30) sees building a's day-10-or-earlier rows: row 0 has no
    # earlier same-bedroom ask, so no term; level 0.
    assert level[0] == 0.0 and level[2] == 0.0
    # Row 4 (day 60) sees rows 2 and 3: row 2 against the mean of rows 0, 1.
    z2 = np.log(3500.0) - np.mean(np.log([3000.0, 4000.0]))
    z3 = np.log(5000.0) - np.mean(np.log([3000.0, 4000.0, 3500.0]))
    assert np.isclose(level[4], (z2 + z3) / (2 + features.BUILDING_LEVEL_SHRINK))
