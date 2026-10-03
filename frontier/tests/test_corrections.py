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
        ]
    )
    frame = pd.DataFrame(
        {
            "audit_id": list("abcdefgh"),
            "building": "x",
            "unit_id": "x/1",
            "bedrooms": [2, 2, 2, 1, 1, 1, 0, 1],
        }
    )
    rows = corrections.bedroom_corrections(frame, text)
    assert rows.audit_id.tolist() == ["a"]
    r = rows.iloc[0]
    assert (r.recorded, r.corrected, r.action) == (2.0, 1.0, "correct_bedrooms")
    assert r.evidence == "bright 1 bedroom in chelsea."
