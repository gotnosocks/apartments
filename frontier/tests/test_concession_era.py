import numpy as np
import pandas as pd
import pytest

from rentfrontier import descriptions, features


def _base(frame, train):
    return features.Features(
        "fake-base",
        ["text:concession"],
        ["description"],
        np.zeros((len(frame), 1)),
        np.ones(1),
    )


def test_concession_era_splits_at_the_new_york_year(monkeypatch):
    frame = pd.DataFrame(
        {
            # 2020-01-01 04:30 UTC is still 2019 in New York.
            "price_at": [
                "2019-06-01T12:00:00Z",
                "2020-01-01T04:30:00Z",
                "2020-01-01T06:00:00Z",
                "2023-03-01T12:00:00Z",
                "2023-03-01T12:00:00Z",
            ]
        }
    )
    text = pd.Series(
        [
            "one month free on a 12 month lease, net effective rent shown.",
            "two months free on this lovely one bedroom apartment.",
            "net effective rent; gross rent is higher than shown here.",
            "a sunny one bedroom with a dishwasher and no concession.",
            "",
        ]
    )
    monkeypatch.setitem(features.FEATURE_SETS, "fake-base", _base)
    monkeypatch.setattr(descriptions, "attach", lambda f: text)
    got = features.concession_era_v1(
        frame, np.ones(len(frame), bool), id="t", base="fake-base"
    )
    assert got.names == ["text:concession", "text:concession, 2020 on"]
    assert got.values[:, 1].tolist() == [0, 0, 1, 1, 0]


def test_concession_era_needs_the_flag_in_its_base(monkeypatch):
    monkeypatch.setitem(
        features.FEATURE_SETS,
        "fake-base",
        lambda f, t: features.Features(
            "fake-base", ["x"], ["g"], np.zeros((len(f), 1)), np.ones(1)
        ),
    )
    with pytest.raises(ValueError):
        features.concession_era_v1(
            pd.DataFrame({"price_at": ["2021-01-01T00:00:00Z"]}),
            np.ones(1, bool),
            base="fake-base",
        )


def test_concession_era_set_is_registered():
    assert features.FEATURE_SETS["nb5-concera-v1"].keywords["base"] == (
        "nb5-plutoasof-v3"
    )
    assert features.NB4_SETS["nb5-concera-v1"] == "nb5-plutoasof-v3"
