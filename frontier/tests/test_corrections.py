import numpy as np
import pandas as pd
from rentfrontier import corrections, data


def test_first_count_reads_the_first_sentence_only():
    assert corrections.first_count("Sunny 2-bedroom on Bank St. A 3 bed feel.") == 2
    assert corrections.first_count("two  bedrooms, top floor") == 2
    assert corrections.first_count("Studio.") == 0
    assert np.isnan(corrections.first_count("Rare 1.5 bedroom"))
    assert np.isnan(corrections.first_count("Lovely home\n2 bedrooms"))


def test_corrections_need_a_clear_contradiction():
    text = pd.Series(
        [
            "Bright 1 bedroom in Chelsea.",  # corrected: 2 -> 1
            "Bright 1 bedroom with home office.",  # room use: no
            "Large 1 bedroom or 2 bedroom.",  # two counts: no
            "Huge 2 bed. Also a 1 bed feel.",  # two counts: no
            "Charming 1 bedroom.",  # agrees: no
            "Former art studio of a painter.",  # not the apartment: no
            "Sunny 1 or 2 bedroom loft",  # hedge: no
            "",  # no ad: no
            "Huge 3 bed in Bushwick.",  # another area: no
            "Bright 4 bedroom.",  # two more than the record: no
            "Cozy studio.",  # the unit's other listing records 1: no
            "Cozy studio &amp; more.",  # a single-listing unit: corrected 1 -> 0
        ]
    )
    frame = pd.DataFrame(
        {
            "audit_id": list("abcdefghijkl"),
            "building": "x",
            "unit_id": ["x/1"] * 10 + ["x/2", "x/3"],
            "bedrooms": [2, 2, 2, 1, 1, 1, 0, 1, 2, 2, 1, 1],
        }
    )
    frame = pd.concat(
        [
            frame,
            pd.DataFrame(
                {"audit_id": ["m"], "building": "x", "unit_id": "x/2", "bedrooms": [1]}
            ),
        ],
        ignore_index=True,
    )
    text = pd.concat([text, pd.Series(["Sunny one bedroom."])], ignore_index=True)
    rows = corrections.bedroom_corrections(frame, text)
    assert rows.audit_id.tolist() == ["a", "l"]
    assert rows.evidence.iloc[1] == "cozy studio & more."
    r = rows.iloc[0]
    assert (r.recorded, r.corrected, r.action) == (2.0, 1.0, "correct_bedrooms")
    assert r.evidence == "bright 1 bedroom in chelsea."


def test_bath_corrections_only_raise_a_clear_count():
    text = pd.Series(
        [
            "Sunny 2 bedroom, 2 bathroom home.",  # corrected: 1 -> 2
            "Renovated 1.5 baths, a short walk to the park.",  # corrected: 1 -> 1.5
            "Charming 1 bath.",  # fewer than the record: left alone
            "2 baths, one of them a powder room.",  # powder room: no
            "2 bath. Also for rent: a 3 bath unit.",  # two counts: no
            "2 bathrooms shared with a roommate.",  # shared: no
            "Two bathrooms.",  # the record's 1 full + 1 half counted plainly: no
            "Sunny 2 bath home.",  # the unit's other listing records 1 bath: no
            "Charming home.",  # that other listing
        ]
    )
    frame = pd.DataFrame(
        {
            "audit_id": list("abcdefghi"),
            "building": "x",
            "unit_id": [f"x/{i}" for i in range(8)] + ["x/7"],
            "full_baths": [1, 1, 2, 1, 1, 1, 1, 1, 1],
            "half_baths": [0, 0, 0, 0, 0, 0, 1, 0, 0],
            "bathrooms": [1, 1, 2, 1, 1, 1, 1.5, 1, 1],
        }
    )
    rows = corrections.bathroom_corrections(frame, text)
    assert rows.audit_id.tolist() == ["a", "b"]
    assert rows.corrected.tolist() == [2.0, 1.5]
    assert rows.full_baths.tolist() == [2, 1]
    assert rows.half_baths.tolist() == [0, 1]
    assert rows.evidence.iloc[0] == "sunny 2 bedroom, 2 bathroom home."


def test_v2_needs_half_the_units_listings_and_the_right_place(monkeypatch):
    monkeypatch.setattr(corrections.data, "merge_unit_aliases", lambda f: f)
    frame = pd.DataFrame(
        {
            "audit_id": list("abcdefgh"),
            "building": ["1-w-1-street"] * 6 + ["202-8-avenue"] * 2,
            "unit_id": ["u1", "u1", "u1", "u1", "u2", "u3", "u4", "u5"],
            "neighbourhood": ["Chelsea"] * 8,
            "bedrooms": [1, 0, 1, 1, 0, 0, 0, 0],
        }
    )
    text = pd.Series(
        [
            "Cozy studio.",  # u1: one of three others records 0: refused in v2
            "Bright studio.",
            "Sunny 1 bedroom.",
            "Sunny 1 bedroom.",
            "Bright 1 bedroom in Chelsea.",  # u2, alone: corrected 0 -> 1
            "Sunny 1 bedroom in the heart of the West Village.",  # other area
            "Lovely 1-bedroom on seventh ave!",  # building on 8th Avenue
            "Lovely 1 bedroom on eighth avenue.",  # its own avenue: corrected
        ]
    )
    v1 = corrections.bedroom_corrections(frame, text, version=1)
    v2 = corrections.bedroom_corrections(frame, text, version=2)
    assert {"a", "e", "f", "g", "h"} <= set(v1.audit_id)
    assert v2.audit_id.tolist() == ["e", "h"]


def test_v2_baths_must_fit_the_ads_own_bedrooms(monkeypatch):
    monkeypatch.setattr(corrections.data, "merge_unit_aliases", lambda f: f)
    frame = pd.DataFrame(
        {
            "audit_id": list("abc"),
            "building": "x",
            "unit_id": ["u1", "u2", "u3"],
            "neighbourhood": "Chelsea",
            "bedrooms": [1, 0, 1],
            "full_baths": [1, 1, 1],
            "half_baths": [0, 0, 0],
            "bathrooms": [1, 1, 1],
        }
    )
    text = pd.Series(
        [
            "Sunny 1 bedroom, 2 bathroom home.",  # corrected 1 -> 2
            "Awesome studio with 2 baths.",  # a studio with two baths: refused
            "2 room studio, 2 baths.",  # the ad says studio, the record 1 bed
        ]
    )
    assert len(corrections.bathroom_corrections(frame, text, version=1)) == 3
    v2 = corrections.bathroom_corrections(frame, text, version=2)
    assert v2.audit_id.tolist() == ["a"]


def test_v2_majority_joins_units_as_unit_labels_v2(monkeypatch):
    frame = pd.DataFrame(
        {
            "audit_id": list("abc"),
            "building": "1-w-1-street",
            "unit_id": ["u1", "u2", "u2"],
            "neighbourhood": "Chelsea",
            "bedrooms": [1, 1, 1],
        }
    )
    text = pd.Series(["Cozy studio in Chelsea, top floor.", "", ""])
    # Alone, u1 has no other listing; joined with u2, two others record 1.
    monkeypatch.setattr(corrections.data, "merge_unit_aliases", lambda f: f)
    assert corrections.bedroom_corrections(
        frame, text, version=2
    ).audit_id.tolist() == ["a"]

    def joined(f):
        return f.assign(unit_id="u1")

    monkeypatch.setattr(corrections.data, "merge_unit_aliases", joined)
    assert corrections.bedroom_corrections(frame, text, version=2).empty


def test_v2_refuses_ranges_rec_rooms_and_disagreeing_true_counts(monkeypatch):
    monkeypatch.setattr(corrections.data, "merge_unit_aliases", lambda f: f)
    frame = pd.DataFrame(
        {
            "audit_id": list("abcd"),
            "building": "1-w-1-street",
            "unit_id": ["u1", "u2", "u3", "u4"],
            "neighbourhood": "Chelsea",
            "bedrooms": [3, 3, 1, 0],
        }
    )
    text = pd.Series(
        [
            "Massive 4 bedroom. It features 3 true bedrooms.",
            "Grand 4 bedroom townhouse. A gracious 3- 4 bedroom home.",
            "Renovated 2 bedroom with one king sized rec room.",
            "1br",
        ]
    )
    # v1 corrects all four; each is refused in v2 by its own rule.
    v1 = corrections.bedroom_corrections(frame, text, version=1)
    assert v1.audit_id.tolist() == ["a", "b", "c", "d"]
    assert corrections.bedroom_corrections(frame, text, version=2).empty


def test_greenwich_village_ads_may_name_the_west_village():
    frame = pd.DataFrame(
        {
            "neighbourhood": ["Greenwich Village"] * 2 + ["Chelsea"],
            "building": ["1-fifth-avenue"] * 3,
        }
    )
    text = pd.Series(
        [
            "a sunny one bedroom in the west village",
            "a sunny one bedroom in the heart of chelsea",
            "a sunny one bedroom in greenwich village",
        ]
    )
    assert corrections.placed_elsewhere(frame, text).tolist() == [False, True, True]


def test_v3_counts_flatiron_and_gramercy_as_other_neighbourhoods():
    frame = pd.DataFrame(
        {
            "neighbourhood": [
                "Flatiron",
                "Flatiron",
                "Gramercy Park",
                "Chelsea",
                "West Village",
                "Chelsea",
            ],
            "building": ["a", "b", "c", "d", "e", "f"],
        }
    )
    text = pd.Series(
        [
            "sunny 2 bed in gramercy",
            "sunny 2 bed in the heart of chelsea",
            "sunny 2 bed in the west village",
            "sunny 2 bed in the flatiron district",
            "sunny 2 bed in gramercy park",
            "sunny 2 bed in chelsea",
        ]
    )
    v3 = corrections.placed_elsewhere(frame, text, corrections.OTHER_NEIGHBOURHOOD_V3)
    assert v3.tolist() == [False, True, True, True, True, False]
    # v2 is unchanged: it knows only Chelsea and the Villages.
    assert corrections.placed_elsewhere(frame, text).tolist() == [False] * 6
    assert corrections._v(2) == (None, corrections.OTHER_NEIGHBOURHOOD)
    assert corrections._v(3) == (
        data.UNIT_ALIASES_FGP,
        corrections.OTHER_NEIGHBOURHOOD_V3,
    )
