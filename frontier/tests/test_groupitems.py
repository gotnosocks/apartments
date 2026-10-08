import numpy as np
import pandas as pd

from rentfrontier import descriptions, groupitems


def _frame(n=8):
    beds = np.array([0, 1] * (n // 2))
    return pd.DataFrame(
        {
            "audit_id": [f"a{i}" for i in range(n)],
            "bedrooms": beds,
            "price_basis": ["ask"] * n,
            "log_rent": np.log(1000.0) + 0.5 * beds,
        }
    )


def test_raw_slope_recovers_a_planted_gap_and_doubling():
    f = _frame()
    flag = np.array([1, 1, 0, 0, 1, 1, 0, 0], dtype=float)
    f["log_rent"] += np.log(1.1) * flag  # 10% more where the flag is on
    assert groupitems.raw_slope(flag, f) == 10.0
    g = _frame()
    walk = np.log2([100, 100, 200, 200, 400, 400, 800, 800])
    g["log_rent"] += np.log(0.98) * walk  # 2% less per doubling
    assert groupitems.raw_slope(walk, g) == -2.0


def test_attributes_count_only_ads_with_text(monkeypatch):
    f = _frame()
    text = ["a lovely walk-in closet in a quiet home"] * 2 + ["walk-in closet"] * 2
    text += ["a sunny home with plenty of light"] * 4
    monkeypatch.setattr(descriptions, "attach", lambda frame: pd.Series(text))
    items, known = groupitems.attributes(f)
    closet = next(i for i in items if i["item"] == "walk_in_closet")
    assert known == 6  # the two short ads are left out
    assert closet["rows"] == 2 and closet["share"] == round(2 / 6, 4)


def test_raw_slope_is_none_without_spread():
    assert groupitems.raw_slope(np.zeros(8), _frame()) is None
