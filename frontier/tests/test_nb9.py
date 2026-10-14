import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rentfrontier import data, features, run


def test_nb9_base_is_nb8_nostuy_plus_midtown_west():
    new = features.FEATURE_SETS["nb9-nostuy-v1"]
    old = features.FEATURE_SETS["nb8-nostuy-v1"]
    assert new.func is old.func
    assert new.keywords == {
        **old.keywords,
        "id": "nb9-nostuy-v1",
        "hoods": old.keywords["hoods"] + ("Hell's Kitchen", "Hudson Yards"),
    }


def test_nb9_sets_are_nb8s_on_the_nb9_base():
    """Each nb9 set is its nb8 counterpart's builder on the nb9 base, in the
    same groups, reading the ten neighbourhoods' snapshots."""
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    for name in features.NB9_SETS:
        assert features.lot_files(name) == {
            "registry": features.NB9_REGISTRY_FILE,
            "pluto": features.NB9_PLUTO_FILE,
        }
        assert features.AREA_SNAPSHOTS[name] == {
            "basemap": features.NB9_BASEMAP_FILE,
            "footprints": features.NB9_FOOTPRINTS_FILE,
        }
        assert features.EXTRAS_SNAPSHOTS[name] == features.NB9_EXTRAS_FILE
        assert features.LPC_SNAPSHOTS[name] == features.NB9_LPC_FILE
        assert features.PLUTO_RELEASES_SNAPSHOTS[name] == (
            features.NB9_PLUTO_RELEASES_FILE
        )
        assert features.description_files(name) == features._NB9_DESCRIPTIONS
        like = name.replace("nb9-", "nb8-")
        new, old = features.FEATURE_SETS[name], features.FEATURE_SETS[like]
        assert new.func is old.func
        if name != "nb9-nostuy-v1":
            assert new.keywords == {
                **old.keywords,
                "id": name,
                "base": old.keywords["base"].replace("nb8-", "nb9-"),
            }
        assert {k for k, v in groups.items() if name in v} == {
            k for k, v in groups.items() if like in v
        }
    assert set(features._NB9_DESCRIPTIONS) == set(features._NB8_DESCRIPTIONS) | {
        "descriptions_mw"
    }


def test_run_records_the_nb9_snapshots(monkeypatch):
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    sources = run.feature_sources("nb9-nostuy-lister-v1")
    assert sources["pluto_releases"]["path"] == features.NB9_PLUTO_RELEASES_FILE
    assert sources["lister"]["path"] == features.LISTER_FILE


def test_nb9_snapshots_keep_nb8s_rows_and_add_midtown_wests():
    """The nb9 registry, MapPLUTO, footprints, NTA, block lots and lister hold
    the nb8 snapshots' rows unchanged plus Midtown West's."""
    pairs = (
        (features.NB8_REGISTRY_FILE, features.NB9_REGISTRY_FILE, "building"),
        (features.NB8_PLUTO_FILE, features.NB9_PLUTO_FILE, "bbl"),
        (features.NB8_FOOTPRINTS_FILE, features.NB9_FOOTPRINTS_FILE, "bin"),
        (
            "/data1/apartments/external/nta/20261010-c90ddbd/nta.parquet",
            features.NTA_FILE,
            "building",
        ),
        (
            "/data1/apartments/external/blocklots/20261010-c90ddbd/blocklots.parquet",
            features.BLOCKLOTS_FILE,
            "bbl",
        ),
        (
            "/data1/apartments/external/lister/20261010-b5c71cf/lister.parquet",
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
    registry = pd.read_parquet(features.NB9_REGISTRY_FILE)
    assert len(registry) == 6683


def test_dataset_nb9_is_nb8_plus_hells_kitchen_and_hudson_yards():
    path = data.DATASET_NB9 / "complete.json"
    if not path.exists():
        pytest.skip("dataset not on this machine")
    complete = json.loads(path.read_text())
    assert complete["parts"]["nb8"]["path"] == str(data.DATASET_NB8)
    assert complete["rows"] == {"nb8": 215156, "Midtown West": 81797}
    assert complete["neighbourhoods"]["Hell's Kitchen"] == 64675
    assert complete["neighbourhoods"]["Hudson Yards"] == 17122


def test_nb9_nta_levels_add_to_the_neighbourhood_indicators():
    """On the NB9 rows, nb9-nostuy-nta-v1's NTA levels (nb8's folds),
    nb9-nostuy-v1's neighbourhood indicators and an intercept are linearly
    independent."""
    if not (data.DATASET_NB9 / "complete.json").exists():
        pytest.skip("dataset not on this machine")
    if not Path(features.NTA_FILE).exists():
        pytest.skip("external snapshots not on this machine")
    frame = data.load(data.DATASET_NB9)
    hoods = features.FEATURE_SETS["nb9-nostuy-v1"].keywords["hoods"]
    hoods += ("West Village", "Greenwich Village")
    names = features.nta_names(frame, features.NB8_NTA_FOLDED)
    levels = sorted(set(names) - {"Chelsea-Hudson Yards"})
    X = np.column_stack(
        [np.ones(len(frame))]
        + [frame.neighbourhood.eq(h) for h in hoods]
        + [names.eq(n) for n in levels]
    ).astype(float)
    assert np.linalg.matrix_rank(X) == X.shape[1]


def test_latest_ask_v4_keeps_v3s_rows_and_adds_midtown_wests():
    old, new = data.LATEST_ASK_V3, data.LATEST_ASK_V4
    assert data.DATA_RULES["latest-ask-v4"].keywords == {"path": new}
    if not (old.exists() and new.exists()):
        pytest.skip("latest-ask files not on this machine")
    o = pd.read_parquet(old).set_index("audit_id")
    n = pd.read_parquet(new).set_index("audit_id")
    assert len(n) - len(o) == 81797
    pd.testing.assert_series_equal(n.latest_ask.loc[o.index], o.latest_ask)
