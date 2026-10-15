import json
import math
import re

import numpy as np
import pandas as pd

from rentfrontier import adfit, data


def test_loo_median_matches_leaving_each_row_out():
    rng = np.random.default_rng(0)
    values = rng.normal(size=40)
    values[[3, 17]] = np.nan
    groups = rng.integers(0, 5, size=40)
    groups[[0, 1, 2]] = [7, 8, 8]  # a group of one and a group of two
    got = adfit.loo_median(values, groups)
    for i in range(40):
        rest = values[(groups == groups[i]) & (np.arange(40) != i)]
        if np.isnan(values[i]):
            rest = values[groups == groups[i]]
        rest = rest[~np.isnan(rest)]
        want = np.median(rest) if len(rest) else np.nan
        assert np.isclose(got[i], want, equal_nan=True), i


def _frame(rows):
    base = dict(
        source_listing_id="1",
        building="b",
        neighbourhood="Chelsea",
        price_at=pd.Timestamp("2016-01-01"),
    )
    frame = pd.DataFrame([{**base, **r} for r in rows])
    frame["log_rent"] = np.log(frame.pop("rent"))
    return frame


COORDS = pd.DataFrame({"latitude": [40.745], "longitude": [-73.992]}, index=["b"])
CENTRES = {
    "harlem": [(40.809, -73.948)],
    "chelsea": [(40.746, -73.999)],
    "kensington": [(40.639, -73.972)],
}


def test_screen_finds_a_cheap_unsized_ask_in_a_loft_unit():
    """The 110 W 26th St case: a one-bedroom with no size in a unit of
    1,600 sq ft lofts, at a third of their asks, lands in tier A."""
    lofts = [
        dict(audit_id=f"l{i}", unit_id="u", bedrooms=1, square_feet=1600, rent=7000)
        for i in range(4)
    ]
    cheap = dict(audit_id="x", unit_id="u", bedrooms=1, square_feet=None, rent=2400)
    small = [
        dict(audit_id=f"s{i}", unit_id=f"s{i}", bedrooms=1, square_feet=600, rent=5000)
        for i in range(5)
    ]
    frame = _frame(lofts + [cheap] + small)
    text = pd.Series(
        ["one bedroom loft for $7,000"] * 4 + ["bright one bed $2,400"] + [""] * 5
    )
    hits = adfit.screen(frame, text, COORDS, CENTRES).set_index("audit_id")
    assert hits.at["x", "tier"] == "A"
    assert {"size_missing_small", "price_far_unit"} <= set(hits.at["x", "flags"])
    assert "l0" not in hits.index


def test_screen_output_hides_rent():
    frame = _frame(
        [
            dict(audit_id="a", unit_id="u", bedrooms=1, square_feet=600, rent=3000),
            dict(audit_id="b", unit_id="u", bedrooms=1, square_feet=600, rent=9000),
        ]
    )
    text = pd.Series(["now $3,000 per month, a roommate wanted", "9,000/month or 9k"])
    hits = adfit.screen(frame, text, COORDS, CENTRES)
    assert not {c for c in hits.columns if re.search("rent|price|log", c)}
    assert not any(re.search(r"\d", s) for s in hits.snippet)


def test_text_flags_and_their_false_alarms():
    rows = [
        dict(audit_id=a, unit_id=a, bedrooms=1, square_feet=600, rent=3000)
        for a in "abcdefghi"
    ]
    text = pd.Series(
        [
            "roommate wanted! a 2 bedroom condo",
            "2 beds with massive living room for rent",
            "a cozy studio in the heart of harlem",
            "studio in kensington house, chelsea",
            "shared bathroom down the hall",
            "located in chelsea",
            "enjoy nightly sunsets from the terrace",
            "sorry, no short-term or summer rentals",
            "a 12 month sublease with option to renew",
        ]
    )
    hits = adfit.screen(_frame(rows), text, COORDS, CENTRES).set_index("audit_id")
    assert hits.at["a", "flags"] == ["room_share"]
    assert hits.at["c", "flags"] == ["far_place"]
    assert hits.at["e", "flags"] == ["shared_bath"]
    assert {"b", "d", "f", "g", "h", "i"}.isdisjoint(hits.index)
    assert all(hits.tier == "B")


def test_place_names_leave_out_compass_words():
    names = adfit.place_centres()
    assert "east village" in names and "upper east side" in names
    assert {"central", "north", "east"}.isdisjoint(names)


def test_a_hold_out_needs_a_quote_that_is_not_a_price():
    ok = dict(
        verdict="quarantine_product_scope",
        quote="room in a shared loft",
        quote_source="ad",
        reason="A room, not a whole apartment.",
    )
    assert adfit.verdict_problems(ok) == []
    assert adfit.verdict_problems(dict(verdict="keep")) == []
    for quote in (
        "$2,395",
        "$3,500/mo",
        "rent: $2,400",
        "$2.4k net",
        "3500",
        "3,500 per month",
    ):
        assert adfit.verdict_problems({**ok, "quote": quote}), quote
    assert adfit.verdict_problems({**ok, "quote": ""})
    assert adfit.verdict_problems({**ok, "quote_source": "price"})
    assert adfit.verdict_problems({**ok, "verdict": "drop"})


def test_only_an_unknown_bedroom_hold_out_may_quote_a_placeholder_ad():
    whole = dict(
        verdict="quarantine_bedrooms_unknown",
        quote="apt",
        quote_source="ad",
        quote_is_whole_ad=True,
        reason="The ad says nothing about the apartment.",
    )
    assert adfit.verdict_problems(whole) == []
    assert adfit.verdict_problems({**whole, "reason": ""})
    assert adfit.verdict_problems({**whole, "verdict": "quarantine_product_scope"})


def test_every_recorded_read_passes_the_verdict_check():
    for path in adfit.READS:
        with open(path) as f:
            for line in filter(str.strip, f):
                read = json.loads(line)
                assert set(read["flags"]) <= set(adfit.FLAGS), read["audit_id"]
                assert adfit.verdict_problems(read) == [], read["audit_id"]


def test_every_registered_dataset_is_screened_for_ad_fit():
    """Registering a dataset newer than NB8 means running
    `frontier/scripts/ad_fit_screen.py` on it, reading its hits and adding its
    cohort to `adfit.SCREENED`."""
    screened = set(adfit.SCREENED.read_text().split())
    for name in dir(data):
        m = re.fullmatch(r"DATASET_NB(\d+)", name)
        if m and int(m[1]) >= 9:
            assert getattr(data, name).name in screened, name


def test_thresholds_are_factors_over_one():
    assert adfit.SIZE_FACTOR > 1 and adfit.PRICE_FACTOR > 1 and 0 < adfit.SMALL < 1
    assert math.isfinite(adfit.FAR_KM)


def test_an_inferred_size_flag_needs_a_far_price():
    """A studio with no size in a building where only the large units list one
    gets bldg_size_small, but it lands in no tier at an ordinary studio ask,
    and in tier A at a third of the building's studio asks."""
    big = [
        dict(audit_id=f"b{i}", unit_id=f"b{i}", bedrooms=0, square_feet=900, rent=4000)
        for i in range(3)
    ] + [
        dict(audit_id=f"t{i}", unit_id=f"t{i}", bedrooms=2, square_feet=1400, rent=7000)
        for i in range(3)
    ]
    studio = dict(audit_id="s", unit_id="s", bedrooms=0, square_feet=None, rent=3800)
    cheap = dict(audit_id="c", unit_id="c", bedrooms=0, square_feet=None, rent=1300)
    sized = [
        dict(audit_id=f"o{i}", unit_id=f"o{i}", bedrooms=0, square_feet=450, rent=3000)
        for i in range(5)
    ]
    frame = _frame(big + [studio, cheap] + sized)
    frame.loc[len(big) + 2 :, "building"] = "elsewhere"
    coords = pd.concat([COORDS, COORDS.rename(index={"b": "elsewhere"})])
    hits = adfit.screen(frame, pd.Series([""] * len(frame)), coords, CENTRES)
    hits = hits.set_index("audit_id")
    assert "s" not in hits.index
    assert hits.at["c", "tier"] == "A"
    assert "bldg_size_small" in hits.at["c", "flags"]


def test_a_shared_bath_in_a_larger_apartment_needs_other_units():
    rows = [
        dict(audit_id=a, unit_id=a, bedrooms=b, square_feet=900, rent=rent)
        for a, b, rent in [
            ("a", 3, 4000),
            ("b", 3, 4000),
            ("c", 0, 2000),
            ("d", 1, 3000),
        ]
    ]
    text = pd.Series(
        [
            "three bedrooms share two shared bathrooms",
            "bathroom shared with other tenants on the floor",
            "studio with a shared bathroom",
            "amenities: roof deck, gym, communal kitchen and dining room",
        ]
    )
    hits = adfit.screen(_frame(rows), text, COORDS, CENTRES).set_index("audit_id")
    assert {"a", "d"}.isdisjoint(hits.index)
    assert hits.at["b", "flags"] == ["shared_bath"]
    assert hits.at["c", "flags"] == ["shared_bath"]


def test_bedroom_check_flags_a_studio_priced_like_the_three_bedrooms():
    """106 E 10th St: studios asking what the building's large units ask. A
    one-bedroom above the two- and three-bedrooms is flagged too, and the
    building's ordinary units are not."""
    rows = [
        dict(audit_id=f"b{k}{i}", unit_id=f"u{k}{i}", bedrooms=k, rent=rent)
        for k, rent in ((0, 2500), (1, 3200), (2, 4200), (3, 5500))
        for i in range(3)
    ]
    rows += [
        dict(audit_id="studio", unit_id="s", bedrooms=0, rent=5000),
        dict(audit_id="one", unit_id="o", bedrooms=1, rent=6000),
    ]
    frame = _frame([dict(square_feet=None, **r) for r in rows])
    got = pd.Series(adfit.bedroom_conflicts(frame), index=frame.audit_id)
    assert got["studio"] and got["one"]
    assert not got.drop(["studio", "one"]).any()
    hits = adfit.screen(frame, pd.Series([""] * len(frame)), COORDS, CENTRES)
    hits = hits.set_index("audit_id")
    assert hits.at["studio", "tier"] == "E"
    assert "beds_price_bldg" in hits.at["studio", "flags"]


def test_bedroom_check_needs_two_other_units_at_the_level():
    rows = [
        dict(audit_id="studio", unit_id="s", bedrooms=0, rent=5000),
        dict(audit_id="big", unit_id="b", bedrooms=3, rent=5000),
        dict(audit_id="small", unit_id="m", bedrooms=0, rent=2500),
    ]
    frame = _frame([dict(square_feet=None, **r) for r in rows])
    assert not adfit.bedroom_conflicts(frame).any()
