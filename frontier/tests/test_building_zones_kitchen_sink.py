import json

import numpy as np
import pandas as pd

from rentfrontier import building_zones_kitchen_sink as ks
from rentfrontier import listing_codes


def _at(days):
    return pd.Series(pd.Timestamp("2026-01-01", tz="UTC") + pd.to_timedelta(days, "D"))


def test_past_sums_read_only_earlier_days_of_the_group():
    group = np.array([0, 0, 0, 0, 1, 1])
    at = _at([3, 1, 2, 2, 1, 5])
    x = np.array([[1.0], [10.0], [100.0], [1000.0], [7.0], [9.0]])
    w = np.array([1.0, 1.0, 1.0, 0.0, 1.0, 1.0])
    s, n = ks.past_sums(x, w, group, at)
    # Day 3 of group 0 sums days 1 and 2 (the weight-0 row on day 2 adds nothing); the two
    # day-2 rows see only day 1, and the first row of each group sees nothing.
    np.testing.assert_allclose(s[:, 0], [110.0, 0.0, 10.0, 10.0, 0.0, 7.0])
    np.testing.assert_allclose(n, [2.0, 0.0, 1.0, 1.0, 0.0, 1.0])


def test_past_means_add_the_row_itself_to_earlier_training_rows():
    group = np.array([0, 0, 0])
    at = _at([1, 2, 3])
    x = np.array([[2.0], [4.0], [9.0]])
    train = np.array([True, False, True])
    m = ks.past_means(x, group, at, train)
    # The held-out row on day 2 never enters a later mean.
    np.testing.assert_allclose(m[:, 0], [2.0, 3.0, 5.5])


def test_past_max_skips_later_and_unweighted_rows():
    group = np.array([0, 0, 0, 1])
    at = _at([1, 2, 3, 1])
    v = np.array([5.0, 9.0, 3.0, 4.0])
    w = np.array([True, False, True, True])
    m = ks.past_max(v, group, at, w)
    np.testing.assert_allclose(m, [np.nan, 5.0, 5.0, np.nan])


def test_building_codes_take_the_past_majority(monkeypatch):
    monkeypatch.setattr(ks, "MIN_BUILDINGS", 1)
    monkeypatch.setattr(ks, "MIN_ROWS", 1)
    frame = pd.DataFrame(
        {"listing_id": ["1", "2", "3", "4"], "price_at": _at([1, 2, 3, 4])}
    )
    codes = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4"],
            "states_amenities": [1, 0, 1, 1],
            "amen:POOL": [1, 0, 0, 0],
        }
    )
    site = np.zeros(4, int)
    train = np.ones(4, bool)
    names, x = ks.building_codes(frame, site, codes, train)
    j = names.index("bld:amen_pool")
    # Listing 2 states no amenities, so it reads listing 1 alone; listing 3 ties 1 to 1 and
    # counts as a pool; listing 4 has one pool among three stating ads.
    np.testing.assert_allclose(x[:, j], [1.0, 1.0, 1.0, 0.0])
    np.testing.assert_allclose(x[:, names.index("bld:amenities_unstated")], 0.0)


def test_listing_codes_keep_the_latest_record_as_code_columns():
    codes = {k: listing_codes.Codes() for k in listing_codes.LISTS}
    rec = {
        "propertyDetails": {
            "amenities": {"list": ["POOL", "GYM"]},
            "features": {"list": [], "views": ["CITY"]},
            "roomCount": 3,
        },
        "media": {"photos": [{}, {}], "tour3dUrl": "x"},
        "listingSource": {"sourceType": "FEED"},
    }
    masks, counts, source = listing_codes.parse(json.dumps(rec), codes)
    assert listing_codes.parse("not json", codes) is None
    t = pd.DataFrame(
        {"listing_id": ["1"]}
        | {f"mask_{k}": [m] for k, m in zip(listing_codes.LISTS, masks)}
    )
    t = listing_codes.expand(t, codes)
    assert t["amen:POOL"].item() == t["amen:GYM"].item() == 1
    assert t["views:CITY"].item() == 1
    assert t.states_amenities.item() == 1 and t.states_features.item() == 0
    assert counts == (3, 2, 0, 0, 1) and source == "FEED"
