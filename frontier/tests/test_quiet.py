import numpy as np
import pandas as pd
from rentfrontier import features, quiet


def test_centerline_name():
    name = quiet.centerline_name
    assert name("10 PERRY STREET, New York, NY, USA") == ["PERRY ST"]
    assert name("212 WEST 16 STREET, New York") == ["W  16 ST", "16 ST"]
    assert name("1 WEST HOUSTON STREET") == ["W  HOUSTON ST", "HOUSTON ST"]
    assert name("12 WEST WASHINGTON PLACE") == ["W  WASHINGTON PL", "WASHINGTON PL"]
    assert name("55 EAST 10 STREET") == ["E  10 ST", "10 ST"]
    assert name("100 SEVENTH AVENUE SOUTH") == ["7 AVE S"]
    assert name("300 SIXTH AVENUE") == ["AVE OF THE AMERICAS"]
    assert name("20 B'WAY") == ["BROADWAY"]
    assert name("90 WEST STREET") == ["WEST ST"]
    assert name("BRIGHT HORIZONS CHELSEA") == []


def test_label():
    assert quiet.label(True, True, False, False) == "stated"
    assert quiet.label(False, None, True, True) == ""
    assert quiet.label(False, np.nan, True, True) == ""
    assert quiet.label(False, True, True, True) == "busy road"
    assert quiet.label(False, False, True, True) == "quiet street"
    assert quiet.label(False, False, True, False) == "side street"


def test_quiet_text():
    hits = pd.Series(
        [
            "on a quiet tree-lined street",
            "quiet, residential block",
            "the block is very quiet",
            "beautiful tree lined block",
            "quiet bedroom away from the street",
            "quiet street-facing bedroom",
            "quiet streets nearby",
        ]
    ).str.contains(quiet.QUIET_TEXT, regex=True)
    assert hits.tolist() == [True, True, True, True, False, False, False]


def test_distance_to_segments():
    a = np.array([[0.0, 0.0], [0.0, 10.0]])
    b = np.array([[10.0, 0.0], [10.0, 10.0]])
    d = quiet._distance(np.array([5.0, 3.0]), a, b)
    assert np.allclose(d, [3.0, 7.0])
    assert np.allclose(quiet._distance(np.array([-4.0, 3.0]), a, b)[0], 5.0)


def test_quiet_v1_registered_with_nb3_files():
    assert "nb3-quiet-v1" in features.FEATURE_SETS
    assert features.lot_files("nb3-quiet-v1") == features.lot_files("nb3-coded-v2")
    assert features.area_files("nb3-quiet-v1") == features.area_files("nb3-coded-v2")
