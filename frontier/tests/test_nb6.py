import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rentfrontier import features, run


def test_nb6_plutoasof_v3_is_nb5s_builder_plus_stuyvesant_town():
    new = features.FEATURE_SETS["nb6-plutoasof-v3"]
    old = features.FEATURE_SETS["nb5-plutoasof-v3"]
    assert new.func is old.func
    assert new.keywords == {
        **old.keywords,
        "id": "nb6-plutoasof-v3",
        "hoods": ("Flatiron", "Gramercy Park", "Stuyvesant Town/PCV"),
    }


def test_nb6_sets_read_nb5s_sources_from_the_six_neighbourhoods_snapshots():
    """The nb6 set is in every group its nb5 counterpart is in, and each
    snapshot it reads is the six neighbourhoods' one."""
    name, like = "nb6-plutoasof-v3", "nb5-plutoasof-v3"
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    assert {k for k, v in groups.items() if name in v} == {
        k for k, v in groups.items() if like in v
    }
    assert features.lot_files(name) == {
        "registry": features.NB6_REGISTRY_FILE,
        "pluto": features.NB6_PLUTO_FILE,
    }
    assert features.AREA_SNAPSHOTS[name] == {
        "basemap": features.NB6_BASEMAP_FILE,
        "footprints": features.NB6_FOOTPRINTS_FILE,
    }
    assert features.EXTRAS_SNAPSHOTS[name] == features.NB6_EXTRAS_FILE
    assert features.LPC_SNAPSHOTS[name] == features.NB6_LPC_FILE
    assert features.description_files(name) == features._NB6_DESCRIPTIONS
    assert set(features._NB6_DESCRIPTIONS) == set(features._NB4_DESCRIPTIONS) | {
        "descriptions_stuy"
    }
    assert features.PLUTO_RELEASES_SNAPSHOTS == dict.fromkeys(
        features.NB6_SETS, features.NB6_PLUTO_RELEASES_FILE
    )


def test_build_reads_the_sets_own_pluto_releases(monkeypatch):
    seen = {}

    def spy(frame, train):
        seen["released"] = features._RELEASED.get()
        return None

    for name in ("nb6-plutoasof-v3", "nb5-plutoasof-v3", "nb3-coded-v2"):
        monkeypatch.setitem(features.FEATURE_SETS, name, spy)
        features.build(name, pd.DataFrame(), [])
        seen[name] = seen.pop("released")
    assert seen == {
        "nb6-plutoasof-v3": features.NB6_PLUTO_RELEASES_FILE,
        "nb5-plutoasof-v3": features.PLUTO_RELEASES_FILE,
        "nb3-coded-v2": None,
    }


def test_run_records_the_sets_own_pluto_releases(monkeypatch):
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    for name, path in (
        ("nb6-plutoasof-v3", features.NB6_PLUTO_RELEASES_FILE),
        ("nb5-plutoasof-v3", features.PLUTO_RELEASES_FILE),
    ):
        assert run.feature_sources(name)["pluto_releases"]["path"] == path


def test_nb6_snapshots_keep_nb4s_rows_and_add_stuyvesant_towns():
    """The nb6 registry, MapPLUTO and footprints hold nb4's rows unchanged plus
    Stuyvesant Town/PCV's, each of its buildings on its own BIN."""
    pairs = (
        (features.NB4_REGISTRY_FILE, features.NB6_REGISTRY_FILE, "building"),
        (features.NB4_PLUTO_FILE, features.NB6_PLUTO_FILE, "bbl"),
        (features.NB4_FOOTPRINTS_FILE, features.NB6_FOOTPRINTS_FILE, "bin"),
    )
    if not all(Path(p).exists() for old, new, _ in pairs for p in (old, new)):
        pytest.skip("external snapshots not on this machine")
    for old, new, key in pairs:
        o, n = pd.read_parquet(old), pd.read_parquet(new)
        assert len(n) > len(o) and not n[key].duplicated().any()
        kept = n[n[key].isin(o[key])].sort_values(key).reset_index(drop=True)
        o = o.sort_values(key).reset_index(drop=True)
        pd.testing.assert_frame_equal(kept[o.columns], o)
    registry = pd.read_parquet(features.NB6_REGISTRY_FILE)
    stuy = registry[registry.bbl.isin(["1009720001", "1009780001"])]
    assert len(stuy) == 57 and not stuy.bin.eq("1000000").any()


def test_stuyvesant_town_tests_drop_the_indicator_or_add_the_stabilized_share():
    base, nostuy = (
        features.FEATURE_SETS["nb6-plutoasof-v3"],
        features.FEATURE_SETS["nb6-nostuy-v1"],
    )
    assert nostuy.func is base.func
    assert nostuy.keywords == {
        **base.keywords,
        "id": "nb6-nostuy-v1",
        "hoods": ("Flatiron", "Gramercy Park"),
    }
    for name, on in (
        ("nb6-stab-v1", "nb6-plutoasof-v3"),
        ("nb6-nostuy-stab-v1", "nb6-nostuy-v1"),
    ):
        stab = features.FEATURE_SETS[name]
        assert stab.func is features.stabilized_v1
        assert stab.keywords == {"id": name, "base": on}
    assert features.RENTSTAB == {
        "nb6-stab-v1",
        "nb6-nostuy-stab-v1",
        "nb6-nostuy-stabopen-v1",
        "nb6-nostuy-stabopen-v2",
        "nb6-nostuy-explain-v1",
    }
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    for name in (
        "nb6-nostuy-v1",
        "nb6-stab-v1",
        "nb6-nostuy-stab-v1",
        "nb6-nostuy-open-v1",
        "nb6-nostuy-stabopen-v1",
        "nb6-nostuy-open-v2",
        "nb6-nostuy-stabopen-v2",
        "nb6-nostuy-owner-v1",
        "nb6-nostuy-explain-v1",
    ):
        assert {k for k, v in groups.items() if name in v} - {
            "RENTSTAB",
            "BLOCKLOTS",
        } == {k for k, v in groups.items() if "nb6-plutoasof-v3" in v}
        assert features.lot_files(name) == features.lot_files("nb6-plutoasof-v3")


def test_run_records_the_rentstab_snapshot(monkeypatch):
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    assert run.feature_sources("nb6-stab-v1")["rentstab"]["path"] == (
        features.RENTSTAB_FILE
    )
    assert "rentstab" not in run.feature_sources("nb6-plutoasof-v3")


def test_stabilized_units_use_the_bill_before_the_listing_year(tmp_path, monkeypatch):
    registry = pd.DataFrame({"building": ["a", "b"], "bbl": ["1", "2"]})
    stab = pd.DataFrame(
        {
            "bbl": ["1", "1", "1", "2"],
            "year": [2012, 2019, 2023, 2010],
            "units": [40, 30, 10, 5],
        }
    )
    registry.to_parquet(tmp_path / "r.parquet")
    stab.to_parquet(tmp_path / "s.parquet")
    monkeypatch.setattr(features, "lot_registry", lambda: str(tmp_path / "r.parquet"))
    monkeypatch.setattr(features, "RENTSTAB_FILE", str(tmp_path / "s.parquet"))
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "a", "a", "b", "b", "c"],
            "period": pd.to_datetime(
                [
                    "2012-06-01",  # the 2011 bill: none yet
                    "2013-01-01",  # the 2012 bill
                    "2022-03-01",  # 2021 missing: carry 2019 forward
                    "2023-09-01",  # the 2023 bill is not out the year before
                    "2014-01-01",  # b's 2010 bill, three years on
                    "2015-01-01",  # b left the bills after 2010
                    "2016-01-01",  # not in the registry
                ]
            ),
        }
    )
    assert features.stabilized_units(frame).tolist() == [0, 40, 30, 30, 5, 0, 0]


def test_open_sets_add_the_open_share_in_place_of_the_indicator():
    for name, on in (
        ("nb6-nostuy-open-v1", "nb6-nostuy-v1"),
        ("nb6-nostuy-stabopen-v1", "nb6-nostuy-stab-v1"),
    ):
        open_set = features.FEATURE_SETS[name]
        assert open_set.func is features.open_space_v1
        assert open_set.keywords == {"id": name, "base": on}
        assert name in features.FOOTPRINTS


def test_footprint_area_takes_holes_out():
    square = [[-74.0, 40.74], [-73.999, 40.74], [-73.999, 40.741], [-74.0, 40.741]]
    hole = [[-73.9998, 40.7402], [-73.9992, 40.7402], [-73.9992, 40.7408]]
    whole = features.footprint_area(
        json.dumps({"type": "Polygon", "coordinates": [square + square[:1]]})
    )
    holed = features.footprint_area(
        json.dumps(
            {"type": "Polygon", "coordinates": [square + square[:1], hole + hole[:1]]}
        )
    )
    # About 84 m by 111 m.
    assert 0.95 < whole / (84.3 * 111.2 * 10.7639) < 1.05
    assert 0.80 < holed / whole < 0.85


def test_lot_open_share_counts_footprints_built_by_the_listing_year(
    tmp_path, monkeypatch
):
    registry = pd.DataFrame(
        {"building": ["a", "b", "c", "d"], "bin": ["1", "2", "9", "8"]}
    ).assign(bbl=["L", "M", "N", "P"])
    footprints = pd.DataFrame(
        {
            "bin": ["1", "3", "2", "8"],
            "base_bbl": ["L", "L", "C", "P"],
            "construction_year": ["1900", "2015", None, "1950"],
            "geometry": ["300", "200", "400", "100"],
        }
    )
    registry.to_parquet(tmp_path / "r.parquet")
    footprints.to_parquet(tmp_path / "f.parquet")
    monkeypatch.setattr(features, "lot_registry", lambda: str(tmp_path / "r.parquet"))
    monkeypatch.setattr(
        features, "area_snapshot", lambda: ("unused", str(tmp_path / "f.parquet"))
    )
    monkeypatch.setattr(features, "footprint_area", float)
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b", "c", "d"],
            "period": pd.to_datetime(
                ["2010-01-01", "2016-01-01", "2016-01-01", "2016-01-01", "2016-01-01"]
            ),
        }
    )
    lotarea = {"a": 1000, "b": 800, "c": 500, "d": 0}
    monkeypatch.setattr(
        features,
        "building_lots",
        lambda f: pd.DataFrame({"lotarea": f.building.map(lotarea).to_numpy()}),
    )
    out = features.lot_open_share(frame)
    # a: 300 built by 2010, 500 by 2016; b: its footprint's base lot C (a
    # condominium's), no year; c: no footprint; d: no lot area.
    assert out[:3].tolist() == [0.7, 0.5, 0.5]
    assert np.isnan(out[3:]).all()


def test_open_v2_sets_measure_over_the_lots_a_footprint_spans(monkeypatch):
    for name, on in (
        ("nb6-nostuy-open-v2", "nb6-nostuy-v1"),
        ("nb6-nostuy-stabopen-v2", "nb6-nostuy-stab-v1"),
    ):
        open_set = features.FEATURE_SETS[name]
        assert open_set.func is features.open_space_v2
        assert open_set.keywords == {"id": name, "base": on}
        assert name in features.FOOTPRINTS and name in features.BLOCKLOTS
    monkeypatch.setattr(run.data, "sha256", lambda path: "x")
    assert run.feature_sources("nb6-nostuy-open-v2")["blocklots"]["path"] == (
        features.BLOCKLOTS_FILE
    )
    assert "blocklots" not in run.feature_sources("nb6-nostuy-open-v1")


def _square(lon, lat, side, hole=None):
    ring = [[lon, lat], [lon + side, lat], [lon + side, lat + side], [lon, lat + side]]
    rings = [ring + ring[:1]]
    if hole is not None:
        rings.append(hole + hole[:1])
    return rings


def test_rings_contain_points_outside_holes_and_in_any_polygon():
    grid = features.facing_grid()
    hole = [[-73.9997, 40.7403], [-73.9993, 40.7403], [-73.9993, 40.7407]]
    hole.append([-73.9997, 40.7407])
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            _square(-74.0, 40.74, 0.001, hole),
            _square(-73.99, 40.74, 0.001),
        ],
    }
    rings = features._footprint_rings(json.dumps(geometry), grid)
    points = grid(
        np.array([-73.9999, -73.9995, -73.9895, -73.995]),
        np.array([40.7401, 40.7405, 40.7405, 40.7405]),
    )
    # In the first square, in its hole, in the second square, between them.
    assert features._rings_contain(rings, points).tolist() == [
        True,
        False,
        True,
        False,
    ]
    one = features._rings_area(rings[2:])
    assert 0.95 < one / (84.3 * 111.2 * 10.7639) < 1.05
    assert 0.80 < (features._rings_area(rings) - one) / one < 0.85


def test_lot_open_share_v2_joins_the_lots_a_footprint_spans(tmp_path, monkeypatch):
    sq = 84.3 * 111.2 * 10.7639 / 100  # a 0.0001-degree square here, sq ft
    registry = pd.DataFrame(
        {
            "building": ["a", "b", "c", "d", "e"],
            "bin": ["1", "2", "3", "4", "5"],
            "bbl": [f"100001{n}" for n in ("0001", "0002", "0003", "0004", "7501")],
        }
    )
    # a's footprint spans lot 1 and lot 2's point (b, on lot 2, has none of
    # its own); c's covers its lot by 5% more than its area, d's by half as
    # much again; e is a condominium on base lot 6 whose billing lot's point
    # is inside its footprint.
    footprints = pd.DataFrame(
        {
            "bin": ["1", "3", "4", "5"],
            "base_bbl": [f"100001{n}" for n in ("0001", "0003", "0004", "0006")],
            "construction_year": ["1900"] * 4,
            "geometry": [
                json.dumps(
                    {"type": "Polygon", "coordinates": _square(lon, 40.7, 0.0001)}
                )
                for lon in (-74.0, -74.01, -74.02, -74.03)
            ],
        }
    )
    lotarea = [0.6 * sq, 0.6 * sq, sq / 1.05, sq / 1.5, 2 * sq]
    lots = pd.DataFrame(
        {
            "bbl": registry.bbl,
            "lot": ["1", "2", "3", "4", "7501"],
            "lotarea": lotarea,
            "longitude": [-73.99997, -73.99993, -74.00995, -74.01995, -74.02995],
            "latitude": [40.70002, 40.70008, 40.70005, 40.70005, 40.70005],
        }
    )
    registry.to_parquet(tmp_path / "r.parquet")
    footprints.to_parquet(tmp_path / "f.parquet")
    lots.to_parquet(tmp_path / "l.parquet")
    monkeypatch.setattr(features, "lot_registry", lambda: str(tmp_path / "r.parquet"))
    monkeypatch.setattr(
        features, "area_snapshot", lambda: ("unused", str(tmp_path / "f.parquet"))
    )
    monkeypatch.setattr(features, "BLOCKLOTS_FILE", str(tmp_path / "l.parquet"))
    by_building = dict(zip(registry.building, lotarea))
    monkeypatch.setattr(
        features,
        "building_lots",
        lambda f: pd.DataFrame({"lotarea": f.building.map(by_building).to_numpy()}),
    )
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b", "c", "d", "e", "b"],
            "period": pd.to_datetime(
                ["1899-01-01"] + ["2016-01-01"] * 5 + ["1899-01-01"]
            ),
        }
    )
    out = features.lot_open_share_v2(frame)
    # a and b: one footprint over the two lots' 1.2 sq (none before 1900);
    # c: within the overhang, so 0; d: unknown; e: its own lot only; b before
    # a's footprint was built: not yet joined, no footprint of its own.
    assert out[[0, 1, 2]] == pytest.approx([1.0, 1 / 6, 1 / 6], abs=0.01)
    assert out[3] == 0.0
    assert np.isnan(out[4])
    assert out[5] == pytest.approx(0.5, abs=0.01)
    assert np.isnan(out[6])


def test_owner_sets_add_the_complex_in_place_of_the_indicator():
    for name, on in (
        ("nb6-nostuy-owner-v1", "nb6-nostuy-v1"),
        ("nb6-nostuy-explain-v1", "nb6-nostuy-stabopen-v2"),
    ):
        owner_set = features.FEATURE_SETS[name]
        assert owner_set.func is features.owner_v1
        assert owner_set.keywords == {"id": name, "base": on}
        assert name in features.BLOCKLOTS


def test_single_owner_complex_sums_an_owners_lots_on_a_block(tmp_path, monkeypatch):
    lots = pd.DataFrame(
        {
            "bbl": [
                "1000010001",
                "1000010002",
                "1000020001",
                "1000030001",
                "1000030002",
                "1000047501",
                "1000047502",
            ],
            "ownername": [
                "Big Owner, LLC",
                "BIG OWNER LLC",
                "BIG OWNER LLC",
                "Two Towers LLC",
                "UNAVAILABLE OWNER",
                None,
                "CONDO BOARD",
            ],
            "lot": ["0001", "0002", "0001", "0001", "0002", "7501", "7502"],
            "numbldgs": ["2", "1", "5", "2", "9", "1", "5"],
            "unitsres": ["200", "150", "100", "900", "900", "400", "400"],
        }
    )
    registry = pd.DataFrame(
        {
            "building": ["a", "b", "c", "d", "e", "f", "h"],
            "bbl": lots.bbl,
        }
    )
    lots.to_parquet(tmp_path / "l.parquet")
    registry.to_parquet(tmp_path / "r.parquet")
    monkeypatch.setattr(features, "BLOCKLOTS_FILE", str(tmp_path / "l.parquet"))
    monkeypatch.setattr(features, "lot_registry", lambda: str(tmp_path / "r.parquet"))
    frame = pd.DataFrame({"building": ["a", "b", "c", "d", "e", "f", "g", "h"]})
    # a and b: one owner (spelt two ways), 3 buildings and 350 units on block
    # 1; c: the same owner's 100 units on block 2; d: two buildings; e: no
    # owner; f: a condominium's billing lot; g: not in the registry; h: a
    # billing lot with an owner name and enough of everything.
    assert features.single_owner_complex(frame).tolist() == [
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    ]
