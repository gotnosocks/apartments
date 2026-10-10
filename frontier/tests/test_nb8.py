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


# nb8 sets with no nb7 twin; each has its own test below.
NB8_ONLY = {"nb8-nostuy-lines-v1", "nb8-nostuy-retail-v1"}


def test_nb8_tests_are_nb7s_on_the_nb8_base():
    """Each nb8 test is its nb7 counterpart's builder on the nb8 base, in the
    same groups, reading the eight neighbourhoods' snapshots."""
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    for name in features.NB8_SETS:
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
        if name in NB8_ONLY:
            continue
        like = name.replace("nb8-", "nb7-")
        new, old = features.FEATURE_SETS[name], features.FEATURE_SETS[like]
        if name == "nb8-nostuy-nta-v1":
            assert old.func is features.nta_v1 and new.func is features.nta_v2
        elif name == "nb8-nostuy-riverparks-v1":
            assert old.func is features.riverparks_v1
            assert new.func is features.riverparks_v2
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
    assert NB8_ONLY <= set(features.NB8_SETS)
    assert set(features._NB8_DESCRIPTIONS) == set(features._NB7_DESCRIPTIONS) | {
        "descriptions_ev"
    }
    assert features.PARKS_SNAPSHOTS["nb8-nostuy-riverparks-v1"] == (
        features.NB8_PARKS_FILE
    )


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


def test_eastparks_dates_pier_42_and_keeps_riverparks_places():
    """With the nb8 parks file, `riverparks.places` refuses Pier 42 and
    `eastparks.places` is its table plus Pier 42 from 2024-07-03."""
    from rentfrontier import eastparks, riverparks

    paths = (features.NB8_PARKS_FILE, features.NB7_PARKS_FILE, features.RIVERPARKS_FILE)
    if not all(Path(p).exists() for p in paths):
        pytest.skip("external snapshots not on this machine")
    nyc, river = (
        pd.read_parquet(features.NB8_PARKS_FILE),
        pd.read_parquet(features.RIVERPARKS_FILE),
    )
    with pytest.raises(ValueError, match="Pier 42"):
        riverparks.places(nyc, river)
    table = eastparks.places(nyc, river)
    pier = table[table.name.eq("Pier 42")]
    assert len(pier) == 1 and pier.opened.iloc[0] == pd.Timestamp("2024-07-03")
    rest = table[~table.name.eq("Pier 42")].reset_index(drop=True)
    expected = riverparks.places(nyc[~nyc.name.eq("Pier 42")], river)
    pd.testing.assert_frame_equal(
        rest.drop(columns="points"), expected.drop(columns="points")
    )
    old = riverparks.places(pd.read_parquet(features.NB7_PARKS_FILE), river)
    assert set(old.name) <= set(table.name)


def test_eastparks_terms_match_riverparks_before_pier_42(monkeypatch):
    """Before Pier 42 opened, `eastparks.terms` is `riverparks.terms` on a parks
    file without it; from July 2024 a building beside it walks no further."""
    from rentfrontier import eastparks, riverparks

    if not all(
        Path(p).exists()
        for p in (
            features.NB8_PARKS_FILE,
            features.RIVERPARKS_FILE,
            features.NB8_REGISTRY_FILE,
        )
    ):
        pytest.skip("external snapshots not on this machine")
    registry = pd.read_parquet(features.NB8_REGISTRY_FILE).dropna(subset=["latitude"])
    buildings = registry.building.iloc[::50].tolist()
    frame = pd.DataFrame(
        {
            "building": buildings * 2,
            "period": ["2024-06"] * len(buildings) + ["2024-08"] * len(buildings),
        }
    )
    monkeypatch.setattr(features, "lot_registry", lambda: features.NB8_REGISTRY_FILE)
    new = eastparks.terms(frame, features.NB8_PARKS_FILE, features.RIVERPARKS_FILE)
    monkeypatch.setattr(
        pd, "read_parquet", _without_pier_42(pd.read_parquet, features.NB8_PARKS_FILE)
    )
    riverparks.building_minutes.cache_clear()
    old = riverparks.terms(frame, features.NB8_PARKS_FILE, features.RIVERPARKS_FILE)
    riverparks.building_minutes.cache_clear()
    june = frame.period.eq("2024-06").to_numpy()
    pd.testing.assert_frame_equal(new[june], old[june])
    assert (new.park_min[~june] <= old.park_min[~june]).all()


def _without_pier_42(read, path):
    def read_parquet(p, *args, **kwargs):
        table = read(p, *args, **kwargs)
        return table[~table.name.eq("Pier 42")] if str(p) == str(path) else table

    return read_parquet


def test_nb8_lines_is_lines_v1_on_the_nb8_base():
    """nb8-nostuy-lines-v1 has no nb7 twin: it is nb5p3-lines-v1's builder on
    the nb8 base, in its groups, reading the nb8 snapshots and the GTFS."""
    name = "nb8-nostuy-lines-v1"
    new, like = features.FEATURE_SETS[name], features.FEATURE_SETS["nb5p3-lines-v1"]
    assert new.func is like.func is features.lines_v1
    assert new.keywords == {"id": name, "base": "nb8-nostuy-v1"}
    groups = {
        k for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    assert {k for k in groups if name in getattr(features, k)} == {
        k for k in groups if "nb8-nostuy-v1" in getattr(features, k)
    } | {"TRANSIT"}


def test_nb8_lines_price_the_j_z_from_east_village():
    """On the nb8 registry the J/Z is within 8 minutes of enough buildings to
    price; on nb7's it is not."""
    from rentfrontier import lines

    paths = (features.NB8_REGISTRY_FILE, features.NB7_REGISTRY_FILE, features.GTFS_FILE)
    if not all(Path(p).exists() for p in paths):
        pytest.skip("external snapshots not on this machine")

    def priced(registry):
        return lines.priced_lines(
            lines._building_lines(registry, features.GTFS_FILE, frozenset())
        )

    new, old = priced(features.NB8_REGISTRY_FILE), priced(features.NB7_REGISTRY_FILE)
    assert set(new) - set(old) == {"J/Z"} and set(old) <= set(new)


def test_nb8_retail_reads_the_nb8_storefronts(monkeypatch):
    """nb8-nostuy-retail-v1 is retail_v2 on the nb8 base, and its fit records
    the nb8 storefronts snapshot, which is what it reads."""
    name = "nb8-nostuy-retail-v1"
    assert features.FEATURE_SETS[name].func is features.retail_v2
    assert features.FEATURE_SETS[name].keywords == {"id": name, "base": "nb8-nostuy-v1"}
    groups = {
        k for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    assert {k for k in groups if name in getattr(features, k)} == {
        k for k in groups if "nb8-nostuy-v1" in getattr(features, k)
    } | {"STOREFRONTS"}
    assert features.STOREFRONTS_SNAPSHOTS[name] == features.NB8_STOREFRONTS_FILE
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    sources = run.feature_sources(name)
    assert sources["storefronts"]["path"] == features.NB8_STOREFRONTS_FILE
    assert run.feature_sources("nb3-retail-v1")["storefronts"]["path"] == (
        features.STOREFRONTS_FILE
    )


def test_retail_v2_matches_retail_v1_on_the_same_file(monkeypatch):
    """retail_v2 with STOREFRONTS_FILE as its snapshot builds retail_v1's
    terms."""
    if not all(
        Path(p).exists() for p in (features.STOREFRONTS_FILE, features.REGISTRY_FILE)
    ):
        pytest.skip("external snapshots not on this machine")
    registry = pd.read_parquet(features.REGISTRY_FILE)
    frame = pd.DataFrame({"building": registry.building.iloc[::40].tolist()})
    base = features.Features("b", [], [], np.zeros((len(frame), 0)), np.zeros(0))
    monkeypatch.setitem(features.FEATURE_SETS, "b", lambda frame, train: base)
    monkeypatch.setitem(features.STOREFRONTS_SNAPSHOTS, "x", features.STOREFRONTS_FILE)
    train = np.ones(len(frame), bool)
    new = features.retail_v2(frame, train, id="x", base="b")
    old = features.retail_v1(frame, train, id="x", base="b")
    assert new.names == old.names
    np.testing.assert_array_equal(new.values, old.values)
