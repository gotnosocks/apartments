import numpy as np
import pandas as pd
from rentfrontier import corrections


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
