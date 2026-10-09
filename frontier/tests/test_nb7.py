from pathlib import Path

import pandas as pd
import pytest

from rentfrontier import data, features, run


def test_nb7_base_is_nb6_nostuy_plus_nomad():
    new = features.FEATURE_SETS["nb7-nostuy-v1"]
    old = features.FEATURE_SETS["nb6-nostuy-v1"]
    assert new.func is old.func
    assert new.keywords == {
        **old.keywords,
        "id": "nb7-nostuy-v1",
        "hoods": ("Flatiron", "Gramercy Park", "NoMad"),
    }


def test_nb7_tests_are_nb6s_on_the_nb7_base():
    """Each nb7 test is its nb6 counterpart's builder on the nb7 base, in the
    same groups, reading the seven neighbourhoods' snapshots."""
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    for name in features.NB7_SETS:
        like = name.replace("nb7-", "nb6-")
        new, old = features.FEATURE_SETS[name], features.FEATURE_SETS[like]
        assert new.func is old.func
        if name != "nb7-nostuy-v1":
            assert new.keywords == {
                **old.keywords,
                "id": name,
                "base": old.keywords["base"].replace("nb6-", "nb7-"),
            }
        assert {k for k, v in groups.items() if name in v} == {
            k for k, v in groups.items() if like in v
        }
        assert features.lot_files(name) == {
            "registry": features.NB7_REGISTRY_FILE,
            "pluto": features.NB7_PLUTO_FILE,
        }
        assert features.AREA_SNAPSHOTS[name] == {
            "basemap": features.NB7_BASEMAP_FILE,
            "footprints": features.NB7_FOOTPRINTS_FILE,
        }
        assert features.EXTRAS_SNAPSHOTS[name] == features.NB7_EXTRAS_FILE
        assert features.LPC_SNAPSHOTS[name] == features.NB7_LPC_FILE
        assert features.PLUTO_RELEASES_SNAPSHOTS[name] == (
            features.NB7_PLUTO_RELEASES_FILE
        )
        assert features.description_files(name) == features._NB7_DESCRIPTIONS
    assert set(features._NB7_DESCRIPTIONS) == set(features._NB6_DESCRIPTIONS) | {
        "descriptions_nomad"
    }
    assert features.PARKS_SNAPSHOTS["nb7-nostuy-riverparks-v1"] == (
        features.NB7_PARKS_FILE
    )


def test_run_records_the_nb7_snapshots(monkeypatch):
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    sources = run.feature_sources("nb7-nostuy-explain-v1")
    assert sources["pluto_releases"]["path"] == features.NB7_PLUTO_RELEASES_FILE
    assert sources["rentstab"]["path"] == features.RENTSTAB_FILE


def test_nb7_snapshots_keep_nb6s_rows_and_add_nomads():
    """The nb7 registry, MapPLUTO, footprints, NTA, block lots and lister hold
    the nb6 snapshots' rows unchanged plus NoMad's."""
    pairs = (
        (features.NB6_REGISTRY_FILE, features.NB7_REGISTRY_FILE, "building"),
        (features.NB6_PLUTO_FILE, features.NB7_PLUTO_FILE, "bbl"),
        (features.NB6_FOOTPRINTS_FILE, features.NB7_FOOTPRINTS_FILE, "bin"),
        (
            "/data1/apartments/external/nta/20261009-a944359/nta.parquet",
            features.NTA_FILE,
            "building",
        ),
        (
            "/data1/apartments/external/blocklots/20261008-d93eec2/blocklots.parquet",
            features.BLOCKLOTS_FILE,
            "bbl",
        ),
        (
            "/data1/apartments/external/lister/20261009-24e19c9/lister.parquet",
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
    registry = pd.read_parquet(features.NB7_REGISTRY_FILE)
    assert len(registry) == 3849


def test_dataset_nb7_is_nb6_plus_nomad():
    path = data.DATASET_NB7 / "complete.json"
    if not path.exists():
        pytest.skip("dataset not on this machine")
    import json

    complete = json.loads(path.read_text())
    assert complete["parts"]["nb6"]["path"] == str(data.DATASET_NB6)
    assert complete["rows"] == {"nb6": 139387, "NoMad": 9286}
