import pandas as pd

from rentfrontier import exposure


def test_line_labels_exclude_self_and_need_agreement():
    line = pd.Series(["b/J", "b/J", "b/J", "b/J", "b/R", "b/R", None], index=list("abcdefg"))
    own = pd.Series(["rear", "rear", "", "street", "street", "", "rear"], index=line.index)
    got = exposure.line_labels(line, own)
    # c sees rear, rear, street: 2/3 < 75%. a sees rear, street: no. f sees e.
    assert got.line_label.tolist() == ["", "", "", "rear", "", "street", ""]
    assert got.line_votes.tolist() == [2, 2, 3, 2, 0, 1, 0]


def test_bedroom_phrases():
    rear = pd.Series(["the bedroom faces the quiet garden", "a courtyard-facing bedroom",
                      "the bedroom overlooks 8th avenue", "quiet back bedroom"])
    assert rear.str.contains(exposure.BEDROOM_REAR, regex=True).tolist() == [True, True, False, True]
    assert rear.str.contains(exposure.BEDROOM_STREET, regex=True).tolist() == [False, False, True, False]
