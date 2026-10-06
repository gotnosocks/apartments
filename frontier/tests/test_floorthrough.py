import numpy as np
import pandas as pd
from rentfrontier import features, floorthrough


def test_units_per_floor_and_plain_labels(monkeypatch):
    lots = pd.DataFrame({"unitsres": [4, 0, 30], "numfloors": [4, 5, None]})
    monkeypatch.setattr(features, "building_lots", lambda frame: lots)
    upf = floorthrough.units_per_floor(pd.DataFrame(index=range(3)))
    assert upf[0] == 1.0
    assert np.isnan(upf[1:]).all()
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b", "b", "c"],
            "canonical_unit_url": [
                "https://x/building/a/2",
                "https://x/building/a/ph",
                "https://x/building/b/3",
                "https://x/building/b/3a",
                "https://x/building/c/3rd-floor",
            ],
        }
    )
    # c shows one label only: too little to tell.
    assert floorthrough.plain_labels(frame).tolist() == [
        True,
        True,
        False,
        False,
        False,
    ]


def test_numbered_apartments_are_not_floors(monkeypatch):
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b", "b"],
            "canonical_unit_url": [
                "https://x/building/a/4",
                "https://x/building/a/14",
                "https://x/building/b/2",
                "https://x/building/b/3",
            ],
        }
    )
    lots = pd.DataFrame({"unitsres": [48, 48, 4, 4], "numfloors": [4, 4, None, None]})
    monkeypatch.setattr(features, "building_lots", lambda frame: lots)
    assert floorthrough.whole_floor(frame).tolist() == [False, False, True, True]


def test_label_and_text():
    assert floorthrough.label(True, False, False) == "stated"
    assert floorthrough.label(False, True, True) == "whole floor"
    assert floorthrough.label(False, False, True) == "front and rear"
    assert floorthrough.label(False, False, False) == ""
    hits = pd.Series(
        ["sunny floor-through", "floor thru 2br", "floorthrough", "floor throughout"]
    ).str.contains(floorthrough.THROUGH_TEXT, regex=True)
    assert hits.tolist() == [True, True, True, False]


def test_through_v1_registered_with_nb3_files():
    assert "nb3-through-v1" in features.FEATURE_SETS
    assert features.lot_files("nb3-through-v1") == features.lot_files("nb3-coded-v2")
    assert features.area_files("nb3-through-v1") == features.area_files("nb3-coded-v2")
