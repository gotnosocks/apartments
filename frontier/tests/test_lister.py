import json

import numpy as np
import pandas as pd

from rentfrontier import features, lister, run


def test_record_lister_reads_name_licence_and_source_type():
    raw = json.dumps(
        {
            "legacy": {
                "sourceGroupLabel": "Corcoran",
                "license": {"licenseType": "Limited Liability Broker"},
            },
            "listingSource": {"sourceType": "PARTNER"},
            "pricing": {"price": 4000},
        }
    )
    assert lister.record_lister(raw) == {
        "lister": "Corcoran",
        "licensed": True,
        "source_type": "PARTNER",
    }
    assert lister.record_lister("{}") == {
        "lister": None,
        "licensed": False,
        "source_type": None,
    }


def test_kind_puts_owner_then_brokerage_names_first():
    names = pd.Series(
        ["Compass", "Related Rentals", "Mirador Real Estate", "AJ Clarke", None, "X"]
    )
    source = pd.Series(["PARTNER", "FEED", "PARTNER", "PARTNER", None, "OWNER"])
    assert lister.kind(names, source).tolist() == [
        "brokerage",
        "management",
        "brokerage",
        "other",
        "other",
        "owner",
    ]


def test_earlier_counts_only_earlier_days_in_the_same_building():
    d = pd.DataFrame(
        {
            "listing_id": list("abcdef"),
            "building": ["b1", "b1", "b1", "b1", "b2", "b1"],
            "lister": ["A", "A", "B", "A", "A", None],
            "listed_at": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-02-01",
                    "2020-02-01",
                    "2020-03-01",
                    "2020-03-01",
                    "2020-04-01",
                ],
                utc=True,
            ),
        },
        index=[10, 11, 12, 13, 14, 15],
    )
    got = lister.earlier_counts(d)
    # b and c share a day, so neither counts the other.
    assert got.earlier.tolist() == [0, 1, 1, 3, 0, 4]
    assert got.earlier_same.tolist() == [0, 1, 0, 2, 0, 0]
    assert list(got.index) == [10, 11, 12, 13, 14, 15]


def test_own_agent_needs_half_of_five_earlier():
    earlier = pd.Series([4, 5, 5, 10])
    same = pd.Series([4, 3, 2, 5])
    assert lister.own_agent(earlier, same).tolist() == [
        "few_earlier",
        "own",
        "outside",
        "own",
    ]


def test_lister_v1_adds_kind_and_agent_against_brokerage_and_outside(
    monkeypatch, tmp_path
):
    snap = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3"],
            "kind": ["management", "brokerage", "owner"],
            "earlier": pd.array([9, 2, 6], dtype="Int64"),
            "earlier_same": pd.array([8, 2, 1], dtype="Int64"),
        }
    )
    path = tmp_path / "lister.parquet"
    snap.to_parquet(path)
    monkeypatch.setattr(features, "LISTER_FILE", str(path))
    frame = pd.DataFrame({"source_listing_id": [1, 2, 3, 4]})
    base = features.Features("b", [], [], np.zeros((4, 0)), np.zeros(0))
    monkeypatch.setitem(features.FEATURE_SETS, "toy", lambda f, t: base)
    got = features.lister_v1(frame, np.ones(4, bool), id="t", base="toy")
    cols = dict(zip(got.names, got.values.T.tolist()))
    # Listing 4 is missing: other kind, fewer than five earlier.
    assert cols == {
        "lister=management": [1, 0, 0, 0],
        "lister=other": [0, 0, 0, 1],
        "lister=owner": [0, 0, 1, 0],
        "building agent=few_earlier": [0, 1, 0, 1],
        "building agent=own": [1, 0, 0, 0],
    }
    assert got.groups == ["lister"] * 3 + ["building agent"] * 2


def test_nostuy_lister_set_is_registered_and_recorded(monkeypatch):
    f = features.FEATURE_SETS["nb6-nostuy-lister-v1"]
    assert f.func is features.lister_v1
    assert f.keywords == {"id": "nb6-nostuy-lister-v1", "base": "nb6-nostuy-v1"}
    assert "nb6-nostuy-lister-v1" in features.LISTER
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    sources = run.feature_sources("nb6-nostuy-lister-v1")
    assert sources["lister"]["path"] == features.LISTER_FILE
    assert "lister" not in run.feature_sources("nb6-nostuy-v1")
