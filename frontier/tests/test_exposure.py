import pandas as pd
import pytest

from rentfrontier import exposure


def test_line_labels_exclude_self_and_need_agreement():
    line = pd.Series(
        ["b/J", "b/J", "b/J", "b/J", "b/R", "b/R", None], index=list("abcdefg")
    )
    own = pd.Series(
        ["rear", "rear", "", "street", "street", "", "rear"], index=line.index
    )
    got = exposure.line_labels(line, own)
    # c sees rear, rear, street: 2/3 < 75%. a sees rear, street: no. f sees e.
    assert got.line_label.tolist() == ["", "", "", "rear", "", "street", ""]
    assert got.line_votes.tolist() == [2, 2, 3, 2, 0, 1, 0]


def test_bedroom_phrases():
    rear = pd.Series(
        [
            "the bedroom faces the quiet garden",
            "a courtyard-facing bedroom",
            "the bedroom overlooks 8th avenue",
            "quiet back bedroom",
        ]
    )
    assert rear.str.contains(exposure.BEDROOM_REAR, regex=True).tolist() == [
        True,
        True,
        False,
        True,
    ]
    assert rear.str.contains(exposure.BEDROOM_STREET, regex=True).tolist() == [
        False,
        False,
        True,
        False,
    ]


def test_compute_prefers_own_evidence_then_the_line(monkeypatch):
    import numpy as np

    from rentfrontier import descriptions, features

    url = "https://streeteasy.com/building/b/{}".format
    labels = ["3j", "5j", "5j", "7j", "2r"]
    frame = pd.DataFrame(
        {
            "unit_id": ["u3j", "u5j", "u5j", "u7j", "u2r"],
            "building": ["b"] * 5,
            "canonical_unit_url": [url(x) for x in labels],
            "price_at": pd.to_datetime(
                ["2020-01-01", "2019-01-01", "2021-01-01", "2020-01-01", "2020-01-01"],
                utc=True,
            ),
        }
    )
    own = {"u3j": (False, True), "u7j": (True, True)}

    def sides(f):
        s = np.array([own.get(u, (False, False)) for u in f.unit_id])
        return pd.DataFrame(
            {
                "avenue": s[:, 0],
                "wide street": False,
                "side street": False,
                "none": s[:, 1],
            },
            index=f.index,
        )

    monkeypatch.setattr(features, "unit_sides", sides)
    monkeypatch.setattr(
        descriptions,
        "attach",
        lambda f: pd.Series(
            ["", "the bedroom faces the garden", "", "", ""], index=f.index
        ),
    )
    got = exposure.compute(frame).set_index("unit_id")
    assert got.loc["u3j", ["exposure", "source"]].tolist() == ["rear", "own"]
    assert got.loc["u7j", ["exposure", "source", "street_kind"]].tolist() == [
        "both",
        "own",
        "avenue",
    ]
    # 5J: no evidence; the line votes rear 1, both 1: no agreement.
    assert got.loc["u5j", ["exposure", "source", "line_votes", "bedroom"]].tolist() == [
        "",
        "",
        2,
        "rear",
    ]
    assert got.loc["u5j", "listings"] == 2
    assert got.loc["u2r", ["exposure", "source", "line_votes"]].tolist() == ["", "", 0]


def test_manual_label_comes_first_and_votes_for_its_line(monkeypatch, tmp_path):
    import numpy as np

    from rentfrontier import descriptions, features

    manual = tmp_path / "manual.csv"
    manual.write_text(
        "building,unit,facing,source,date,note\n"
        'b,APT-1B,street,"Ben, from the listing photos",2026-10-06,\n'
    )
    monkeypatch.setattr(exposure, "MANUAL", manual)
    url = "https://streeteasy.com/building/b/{}".format
    labels = ["1b", "2b", "3b"]
    frame = pd.DataFrame(
        {
            "unit_id": ["u1b", "u2b", "u3b"],
            "building": ["b"] * 3,
            "canonical_unit_url": [url(x) for x in labels],
            "price_at": pd.to_datetime(["2020-01-01"] * 3, utc=True),
        }
    )
    rear = {"u1b"}  # the photos overrule its own (wrong) evidence

    def sides(f):
        r = np.array([u in rear for u in f.unit_id])
        return pd.DataFrame(
            {"avenue": False, "wide street": False, "side street": False, "none": r},
            index=f.index,
        )

    monkeypatch.setattr(features, "unit_sides", sides)
    monkeypatch.setattr(descriptions, "attach", lambda f: pd.Series("", index=f.index))
    got = exposure.compute(frame).set_index("unit_id")
    assert got.loc["u1b", ["exposure", "source", "checked_by"]].tolist() == [
        "street",
        "manual",
        "Ben, from the listing photos",
    ]
    assert got.loc["u2b", ["exposure", "source", "line_votes"]].tolist() == [
        "street",
        "line",
        1,
    ]
    assert got.loc["u2b", "checked_by"] == ""

    manual.write_text("building,unit,facing,source,date,note\nb,1B,courtyard,x,,\n")
    with pytest.raises(ValueError, match="facing must be"):
        exposure.compute(frame)


def test_line_labels_three_of_four_agree():
    line = pd.Series(["b/J"] * 5)
    own = pd.Series(["both", "both", "both", "rear", ""])
    assert exposure.line_labels(line, own).line_label.tolist()[4] == "both"


def test_main_swaps_the_link(monkeypatch, tmp_path):
    from rentfrontier import data

    monkeypatch.setattr(data, "load", lambda: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(data, "apply_rules", lambda f, m, r: (f, m))
    monkeypatch.setattr(
        exposure, "build", lambda f: pd.DataFrame({"unit_id": ["u"], "source": ["own"]})
    )
    exposure.main(["--out", str(tmp_path)])
    exposure.main(["--out", str(tmp_path)])
    link = tmp_path / "labels.parquet"
    assert link.is_symlink() and pd.read_parquet(link).unit_id.tolist() == ["u"]
    assert sorted(p.name for p in tmp_path.iterdir() if "tmp" in p.name) == []
