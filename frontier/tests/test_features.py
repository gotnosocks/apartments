"""Feature sets: unit-consistent bedrooms (unitbeds-v1)."""

import numpy as np
import pandas as pd
from rentfrontier import features


def test_unit_bedrooms_is_the_lower_median_of_the_units_listings():
    frame = pd.DataFrame(
        {
            "unit_id": ["a", "a", "b", "b", "b", "c", "d", "d"],
            "bedrooms": [1, 2, 0, 1, 1, 3, 2, 2.4],
        }
    )
    np.testing.assert_array_equal(
        features.unit_bedrooms(frame), [1, 1, 1, 1, 1, 3, 2, 2]
    )


def test_unitbeds_is_registered_as_base_v1_by_unit():
    fn = features.FEATURE_SETS["unitbeds-v1"]
    assert fn.func is features.base_v1
    assert fn.keywords == {"id": "unitbeds-v1", "by_unit": True}


def test_unitattrs_adds_the_units_size_to_unitbeds():
    fn = features.FEATURE_SETS["unitattrs-v1"]
    assert fn.func is features.base_v1
    assert fn.keywords == {"id": "unitattrs-v1", "by_unit": True, "unit_size": True}


def test_unit_label_flags():
    import re

    labels = {
        "PHB": "penthouse",
        "PENTHOUSE": "penthouse",
        "GARDEN-A": "garden",
        "GRDN": "garden",
        "LLB": "lower_level",
        "BSMT": "lower_level",
    }
    for label, flag in labels.items():
        hits = [n for n, p in features.UNIT_LABEL_FLAGS.items() if re.search(p, label)]
        assert hits == [flag], (label, hits)
    for label in ("23C", "4B", "307", "G", "B", "PARK"):
        assert not any(re.search(p, label) for p in features.UNIT_LABEL_FLAGS.values())


def test_label_floor_number():
    urls = [
        "https://streeteasy.com/building/x/" + u
        for u in ("23c", "apt-4b", "307", "ph", "4th", "12", "3rd")
    ]
    got = features.label_floor_number(pd.DataFrame({"canonical_unit_url": urls}))
    np.testing.assert_array_equal(got, [23, 4, 3, np.nan, 4, np.nan, 3])
