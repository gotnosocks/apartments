from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rentfrontier import data, features, run


def test_nb8_base_is_nb7_nostuy_plus_east_village():
    new = features.FEATURE_SETS["nb8-nostuy-v1"]
    old = features.FEATURE_SETS["nb7-nostuy-v1"]
    assert new.func is old.func
    assert new.keywords == {
        **old.keywords,
        "id": "nb8-nostuy-v1",
        "hoods": ("Flatiron", "Gramercy Park", "NoMad", "East Village"),
    }


def test_nb8_tests_are_nb7s_on_the_nb8_base():
    """Each nb8 test is its nb7 counterpart's builder on the nb8 base, in the
    same groups, reading the eight neighbourhoods' snapshots."""
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    for name in features.NB8_SETS:
        like = name.replace("nb8-", "nb7-")
        new, old = features.FEATURE_SETS[name], features.FEATURE_SETS[like]
        if name == "nb8-nostuy-nta-v1":
            assert old.func is features.nta_v1 and new.func is features.nta_v2
        else:
            assert new.func is old.func
        if name != "nb8-nostuy-v1":
            assert new.keywords == {
                **old.keywords,
                "id": name,
                "base": old.keywords["base"].replace("nb7-", "nb8-"),
            }
        assert {k for k, v in groups.items() if name in v} == {
            k for k, v in groups.items() if like in v
        }
        assert features.lot_files(name) == {
            "registry": features.NB8_REGISTRY_FILE,
            "pluto": features.NB8_PLUTO_FILE,
        }
        assert features.AREA_SNAPSHOTS[name] == {
            "basemap": features.NB8_BASEMAP_FILE,
            "footprints": features.NB8_FOOTPRINTS_FILE,
        }
        assert features.EXTRAS_SNAPSHOTS[name] == features.NB8_EXTRAS_FILE
        assert features.LPC_SNAPSHOTS[name] == features.NB8_LPC_FILE
        assert features.PLUTO_RELEASES_SNAPSHOTS[name] == (
            features.NB8_PLUTO_RELEASES_FILE
        )
        assert features.description_files(name) == features._NB8_DESCRIPTIONS
    assert set(features._NB8_DESCRIPTIONS) == set(features._NB7_DESCRIPTIONS) | {
        "descriptions_ev"
    }
    assert "nb8-nostuy-riverparks-v1" not in features.FEATURE_SETS


def test_run_records_the_nb8_snapshots(monkeypatch):
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    sources = run.feature_sources("nb8-nostuy-lister-v1")
    assert sources["pluto_releases"]["path"] == features.NB8_PLUTO_RELEASES_FILE


def test_nb8_snapshots_keep_nb7s_rows_and_add_east_villages():
    """The nb8 registry, MapPLUTO, footprints, NTA, block lots and lister hold
    the nb7 snapshots' rows unchanged plus East Village's."""
    pairs = (
        (features.NB7_REGISTRY_FILE, features.NB8_REGISTRY_FILE, "building"),
        (features.NB7_PLUTO_FILE, features.NB8_PLUTO_FILE, "bbl"),
        (features.NB7_FOOTPRINTS_FILE, features.NB8_FOOTPRINTS_FILE, "bin"),
        (
            "/data1/apartments/external/nta/20261009-98db59b/nta.parquet",
            features.NTA_FILE,
            "building",
        ),
        (
            "/data1/apartments/external/blocklots/20261009-98db59b/blocklots.parquet",
            features.BLOCKLOTS_FILE,
            "bbl",
        ),
        (
            "/data1/apartments/external/lister/20261009-dcee63b/lister.parquet",
            features.LISTER_FILE,
            "listing_id",
        ),
    )
    if not all(Path(p).exists() for old, new, _ in pairs for p in (old, new)):
        pytest.skip("external snapshots not on this machine")
    for old, new, key in pairs:
        o, n = pd.read_parquet(old), pd.read_parquet(new)
        assert len(n) > len(o) and not n[key].duplicated().any()
        kept = n[n[key].isin(o[key])].sort_values(key).reset_index(drop=True)
        o = o.sort_values(key).reset_index(drop=True)
        pd.testing.assert_frame_equal(kept[o.columns], o)
    registry = pd.read_parquet(features.NB8_REGISTRY_FILE)
    assert len(registry) == 5436


def test_dataset_nb8_is_nb7_plus_east_village():
    path = data.DATASET_NB8 / "complete.json"
    if not path.exists():
        pytest.skip("dataset not on this machine")
    import json

    complete = json.loads(path.read_text())
    assert complete["parts"]["nb7"]["path"] == str(data.DATASET_NB7)
    assert complete["rows"] == {"nb7": 148673, "East Village": 66483}


def test_nta_v2_folds_its_areas_into_the_reference(monkeypatch, tmp_path):
    path = tmp_path / "nta.parquet"
    pd.DataFrame(
        {
            "building": ["a", "b", "c", "d"],
            "ntaname": [
                "East Village",
                "Stuyvesant Town-Peter Cooper Village",
                "Gramercy",
                "Chelsea-Hudson Yards",
            ],
        }
    ).to_parquet(path)
    monkeypatch.setattr(features, "NTA_FILE", str(path))
    frame = pd.DataFrame({"building": ["a", "b", "c", "d", "e"]})
    assert features.nta_names(frame, features.NB8_NTA_FOLDED).tolist() == [
        "Chelsea-Hudson Yards",
        "Chelsea-Hudson Yards",
        "Gramercy",
        "Chelsea-Hudson Yards",
        "unknown",
    ]
    assert features.FEATURE_SETS["nb8-nostuy-nta-v1"].keywords == {
        "id": "nb8-nostuy-nta-v1",
        "base": "nb8-nostuy-v1",
    }


def test_nb8_nta_levels_add_to_the_neighbourhood_indicators():
    """On the NB8 rows, nb8-nostuy-nta-v1's NTA levels, nb8-nostuy-v1's
    neighbourhood indicators and an intercept are linearly independent: no NTA
    level is a neighbourhood indicator, and no NTA levels sum to neighbourhood
    indicators. East Village's or Greenwich Village's NTA level would break
    that. (Stuy's is folded because the nostuy base has no Stuy indicator for
    explanatory terms to take over from.)"""
    if not (data.DATASET_NB8 / "complete.json").exists():
        pytest.skip("dataset not on this machine")
    if not Path(features.NTA_FILE).exists():
        pytest.skip("external snapshots not on this machine")
    frame = data.load(data.DATASET_NB8)
    hoods = features.FEATURE_SETS["nb8-nostuy-v1"].keywords["hoods"]
    hoods += ("West Village", "Greenwich Village")

    def rank(folded):
        names = features.nta_names(frame, folded)
        levels = sorted(set(names) - {"Chelsea-Hudson Yards"})
        X = np.column_stack(
            [np.ones(len(frame))]
            + [frame.neighbourhood.eq(h) for h in hoods]
            + [names.eq(n) for n in levels]
        ).astype(float)
        return np.linalg.matrix_rank(X), X.shape[1]

    r, k = rank(features.NB8_NTA_FOLDED)
    assert r == k
    for kept in ("East Village", "Greenwich Village"):
        r, k = rank(tuple(n for n in features.NB8_NTA_FOLDED if n != kept))
        assert r < k, kept
