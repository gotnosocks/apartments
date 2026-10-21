import numpy as np
import pandas as pd

from rentfrontier import unit_features as uf


def _rows():
    """Units in one building: 4A states a size twice, 5A once on an ad with no size, 6A on
    the same line has none, PH1 and 19A (near the 20-floor roof) are kept off the line."""
    page = lambda s: f"https://streeteasy.com/building/x/{s}"  # noqa: E731
    return pd.DataFrame(
        {
            "listing_id": [1, 2, 3, 4, 5, 6, 7, 8],
            "building": ["b"] * 7 + ["c"],
            "page": [page("4a"), page("apt-4A"), page("5A"), page("6a"), page("ph1"), page("19A"), page("7B"), page("2C")],
            "bedrooms": [1.0, 1, 1, 1, 1, 1, 2, 1],
            "square_feet": [700.0, 720, np.nan, np.nan, np.nan, np.nan, 50, 650],
            "building_floor_count": [20.0] * 8,
            "laundry_type": ["in_unit", None, "in_building", None, None, None, None, "none"],
        }
    )  # fmt: skip


def test_labels_and_lines():
    assert uf.unit_label(
        pd.Series(["https://x/y/apt-4a/", "https://x/y/ph-1"])
    ).tolist() == ["4A", "PH1"]
    assert uf.floor_and_line("4B") == (4.0, "LB")
    assert uf.floor_and_line("B4") == (4.0, "LB")
    assert uf.floor_and_line("412") == (4.0, "D12")
    assert np.isnan(uf.floor_and_line("GARDEN")[0])  # fmt: skip


def test_sizes_fill_from_the_unit_then_the_line():
    s = uf.sizes(_rows()).set_index("listing_id")
    assert s.loc["1", "size_source"] == "stated" and s.loc["1", "sqft"] == 700
    # 4A and APT-4A are one unit: its stated ads keep their own sizes.
    assert s.loc["2", "sqft"] == 720
    # 5A and 6A take line A's median of unit medians (4A's 710).
    assert (s.loc["3", "size_source"], s.loc["3", "sqft"]) == ("line", 710)
    assert (s.loc["4", "size_source"], s.loc["4", "sqft"]) == ("line", 710)
    # A penthouse and a floor within two of the roof stay off the line.
    assert s.loc["5", "size_source"] == "none" and s.loc["6", "size_source"] == "none"
    # 50 sq ft is out of range.
    assert s.loc["7", "size_source"] == "none" and s.loc["7", "log_size_rel"] == 0
    med = np.median([700, 720, 650])
    np.testing.assert_allclose(s.loc["8", "log_size_rel"], np.log(650 / med))


def test_unit_fill_reaches_ads_without_a_size():
    r = _rows()
    r.loc[8] = [9, "b", "https://x/y/4A", 1.0, np.nan, 20.0, None]
    s = uf.sizes(r).set_index("listing_id")
    assert (s.loc["9", "size_source"], s.loc["9", "sqft"]) == ("unit", 710)


def test_laundry_and_dishwasher():
    t = uf.unit_table(_rows(), pd.Series({"1": 1.0, "3": 0.0}))
    assert t.laundry.tolist()[:4] == ["in_unit", "unstated", "in_building", "unstated"]
    assert t.laundry.iloc[7] == "unstated"
    assert t.dishwasher.tolist()[:3] == [1.0, 0.0, 0.0]
