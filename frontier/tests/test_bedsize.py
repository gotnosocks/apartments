import numpy as np
import pandas as pd
from rentfrontier import bedsize, features


def test_stated_size_takes_the_largest_bed_stated():
    assert bedsize.stated_size("bedroom fits a king bed") == "king"
    assert bedsize.stated_size("king-size bedroom with closets") == "king"
    assert bedsize.stated_size("room for a queen-sized bed") == "queen"
    assert bedsize.stated_size("will fit a full or queen bed") == "queen"
    assert bedsize.stated_size("fits a twin mattress") == "full"
    assert bedsize.stated_size("california king bedroom") == "king"


def test_stated_size_ignores_names_and_bare_rooms():
    assert bedsize.stated_size("on king street, a huge bedroom") is None
    assert bedsize.stated_size("") is None


def test_apartments_pools_only_ads_stating_a_size(monkeypatch):
    frame = pd.DataFrame(
        {
            "unit_id": ["u1", "u1", "u1", "u2"],
            "building": ["b1", "b1", "b1", "b2"],
            "period": pd.to_datetime(["2020-01", "2021-01", "2022-01", "2020-01"]),
        }
    )
    text = pd.Series(["fits a king bed", "queen size bedroom", "sunny", "sunny"])
    monkeypatch.setattr(bedsize.descriptions, "attach", lambda f: text)
    out = bedsize.apartments(frame).set_index("unit_id")
    assert list(out.index) == ["u1"]
    assert out.loc["u1", "largest"] == "king"
    assert out.loc["u1", "latest"] == "queen"
    assert out.loc["u1", "listings"] == 2


def test_stated_size_takes_the_larger_of_alternatives():
    assert bedsize.stated_size("fits a king or queen bed") == "king"
    assert bedsize.stated_size("can accommodate a king or queen") == "king"


def test_stated_size_skips_full_size_rooms_and_other_words():
    assert bedsize.stated_size("two full-size bedrooms") is None
    assert bedsize.stated_size("fits a full kitchen") is None
    assert bedsize.stated_size("outfits a queen bed") is None
    assert bedsize.stated_size("a speaking room") is None


def test_bedsize_v1_adds_exclusive_terms(monkeypatch):
    frame = pd.DataFrame({"unit_id": ["u1", "u2", "u3"]})
    text = pd.Series(["fits a king bed", "fits a twin bed", "sunny"])
    monkeypatch.setattr(bedsize.descriptions, "attach", lambda f: text)
    base = features.Features("base", ["x"], ["unit"], np.ones((3, 1)), np.ones(1))
    monkeypatch.setitem(features.FEATURE_SETS, "base", lambda f, t: base)
    out = features.bedsize_v1(frame, np.ones(3, bool), id="t", base="base")
    terms = [f"ad states a {s} bed" for s in bedsize.SIZES]
    assert out.names == ["x"] + terms
    values = out.values[:, 1:]
    assert values.tolist() == [[0, 0, 1], [1, 0, 0], [0, 0, 0]]
