"""L2 with the smaller-unit flag and a column for units ever advertised that way
(`rentfrontier.drift_building_phase_unitkn_level_bedunit`)."""

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import drift_building_phase_unitkn_level_bedunit as M
from rentfrontier import run


def test_a_frame_without_the_source_columns_is_refused():
    frame = pd.DataFrame({"bedrooms": [1, 2], "bed_flex_at": [True, False]})
    with pytest.raises(ValueError, match="has no bed_text_fewer "):
        M.design(frame)


def test_ever_reads_the_row_and_its_groups_training_rows():
    x = np.array([0.0, 1, 0, 0, 1, 0, 0])
    group = np.array([0, 0, 0, 1, 1, 2, 2])
    train = np.array([1, 1, 0, 1, 0, 1, 1], bool)
    # Group 1's flagged row is held out, so only that row itself takes the 1.
    np.testing.assert_array_equal(M.ever(x, group, train), [1, 1, 1, 0, 1, 0, 0])


def test_with_flag_appends_the_column_and_the_units_ever_column():
    d = td._design(n=400)
    n = len(d.y)
    flex = np.zeros(n, bool)
    flex[[0, 5]] = True
    fewer = np.zeros(n, bool)
    fewer[7] = True
    # Rows 0 to 2 are ads of one unit and rows 6 to 8 of another; the rest stand alone.
    unit = [f"v{i}" for i in range(n)]
    unit[:3] = ["u"] * 3
    unit[6:9] = ["w"] * 3
    frame = pd.DataFrame(
        {
            "building": ["b"] * n,
            "unit_id": unit,
            "price_at": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
            "bed_flex_at": flex,
            "bed_text_fewer": fewer,
        }
    )
    held = np.zeros(n, bool)
    held[[2, 7]] = True
    out = M.with_flag(d, frame, held)
    names = list(out.names)
    assert names[: len(d.names)] == list(d.names)
    assert names[len(d.names) :] == [M.COLUMN, M.EVER]
    x = out.x[:, len(d.names) :]
    np.testing.assert_array_equal(x[:9, 0], [1, 0, 0, 0, 0, 1, 0, 1, 0])
    # Unit u is flagged by its first training row, on a later row and a held-out one too.
    # Unit w's only flagged row is held out, so its training rows stay at 0.
    np.testing.assert_array_equal(x[:9, 1], [1, 1, 1, 0, 0, 1, 0, 1, 0])
    assert out.count[M.COLUMN] == 3
    assert out.count[M.EVER] == 5


def test_run_lists_the_model():
    assert M.NAME == "drift-building-phase-unitkn-level-bedunit"
    assert M.NAME in open(run.__file__).read()
