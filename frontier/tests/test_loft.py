import numpy as np
import pandas as pd
from rentfrontier import loft


def _frame():
    return pd.DataFrame(
        {
            "building": ["b1"] * 6 + ["b2"],
            "price_at": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-02-01",
                    "2020-03-01",
                    "2020-04-01",
                    "2020-04-01",
                    "2020-05-01",
                    "2020-01-01",
                ]
            ),
        }
    )


def test_says_loft_skips_beds_and_platforms():
    assert loft.says_loft("a true soho-style loft with 12 ft ceilings")
    assert not loft.says_loft("studio with a sleeping loft")
    assert not loft.says_loft("lofty ceilings")


def test_prior_share_reads_only_strictly_earlier_ads():
    text = pd.Series(["huge loft", "", "loft space", "flat", "loft", "x", "loft"])
    share = loft.prior_text_share(_frame(), text)
    # rows 0-3 have fewer than three earlier ads with text (row 1 has none)
    assert share[:4].isna().all()
    # rows 3 and 4 share a date, so row 4 does not read row 3
    assert np.isnan(share[4])
    # row 5 reads rows 0, 2, 3 and 4: three of four say loft
    assert share[5] == 3 / 4
    assert np.isnan(share[6])


def test_loft_flags_take_the_class_or_the_text(monkeypatch):
    text = pd.Series(["loft", "loft", "loft", "loft", "flat", "flat", "flat"])
    monkeypatch.setattr(loft.descriptions, "attach", lambda f: text)
    cls = pd.Series(["C7"] * 6 + ["D5"])
    out = loft.loft_flags(_frame(), cls)
    assert list(out.text_loft) == [False] * 3 + [True] * 3 + [False]
    assert list(out.class_loft) == [False] * 6 + [True]
    assert list(out.loft) == [False] * 3 + [True] * 4


def test_prior_share_ignores_row_order_and_index():
    text = pd.Series(["huge loft", "flat", "loft space", "flat", "loft", "x", "loft"])
    labels = [f"r{i}" for i in range(7)]
    frame = _frame().set_axis(labels).iloc[::-1]
    share = loft.prior_text_share(frame, text.set_axis(labels).iloc[::-1])
    # r5, the last b1 ad, reads r0..r4: three of the five say loft
    assert share["r5"] == 3 / 5
    assert share[["r0", "r1", "r2"]].isna().all()
