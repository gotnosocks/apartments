import numpy as np
import pandas as pd
from rentfrontier import cohort


def test_label_floor_rules():
    assert cohort.label_floor("#4D") == ("one-or-two-digit-prefix-letter", 4)
    assert cohort.label_floor("1205")[1] == 12
    assert cohort.label_floor("N3A")[1] == 3
    assert cohort.label_floor("5RE")[1] == 5
    assert cohort.label_floor("3rd floor")[1] is None  # needs "3RDFL" or "3RDFLOOR"
    assert cohort.label_floor("3RDFL")[1] == 3
    assert cohort.label_floor("PH") == (None, None)
    assert cohort.label_floor(None) == (None, None)


def test_floor_of():
    assert cohort.floor_of({"advertised_floor": 7.0}, ["2A"], 5) == (
        7.0,
        "explicit_source_floor",
    )
    nan = {"advertised_floor": np.nan}
    assert cohort.floor_of(nan, ["4D", "#4D"], 6) == (4, "label_proxy")
    assert (
        cohort.floor_of(nan, ["4D", "5D"], 6)[1]
        == "unresolved_or_conflicting_capture_labels"
    )
    assert cohort.floor_of(nan, ["9D"], 6)[1] == "above_captured_building_floor_count"
    assert (
        cohort.floor_of(nan, ["12D"], None)[1]
        == "two_digit_label_without_building_count"
    )
    assert cohort.floor_of(nan, ["3D"], None) == (3, "label_proxy")


def test_consensus():
    assert cohort.consensus([1, 1.0]) == 1
    assert cohort.consensus([1, 2]) is None
    assert cohort.consensus([1, None]) is None
    assert cohort.consensus([True]) is None
    assert cohort.consensus([]) is None


def test_analysis_rows_keep_one_row_per_unit_month_and_exclude():
    h = pd.DataFrame(
        {
            "audit_id": list("abcdef"),
            "unit_id": ["u1", "u1", "u2", "u3", "u4", "u4"],
            "building_id": ["b"] * 6,
            "source_listing_id": list("123456"),
            "price_at": [
                "2020-01-03T00:00:00+00:00",
                "2020-01-20T00:00:00+00:00",
                "2020-01-05T00:00:00+00:00",
                "2020-01-05T00:00:00+00:00",
                "2020-02-01T00:00:00+00:00",
                "2020-02-09T00:00:00+00:00",
            ],
            "rent": [3000, 3100, 500, 3000, 3000, 3200],
            "bedrooms": [1, 1, 1, 1, 1, 2],
            "bathrooms": [1, 1, 1, 1, 1, 1],
            "square_feet": [600, 100, None, 700, 700, 700],
            "furnished": [None, None, None, True, None, None],
        }
    )
    rows, cov = cohort.analysis_rows(h)
    # u1: two asks in January -> the later one (b), its 100 sq ft made unknown.
    # u2: rent under $750; u3: furnished; u4: conflicting layouts in February.
    assert rows.audit_id.tolist() == ["b"]
    assert np.isnan(rows.square_feet.iloc[0])
    assert cov["exclusions"] == {"invalid_rent": 1, "furnished": 1}
    assert cov["conflicting_unit_month_rows"] == 2
