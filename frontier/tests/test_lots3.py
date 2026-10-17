"""The lots3 sets: their base sets with the lots of drop-lot-v1's ads dropped."""

import json

import numpy as np
import pandas as pd
import pytest
from rentfrontier import features

LOTS3 = {
    "nb9-nostuy-lots3-v1": "nb9-nostuy-api-v1",
    "all-scraped-lots3-v1": "all-scraped-v1",
}


def test_lots3_sets_are_their_base_sets_with_the_drop_list():
    assert features.LOTS3_SETS == LOTS3
    groups = {
        k: v
        for k, v in vars(features).items()
        if k.isupper() and isinstance(v, set) and k not in ("CLASS_UNKNOWN_SETS",)
    }
    for name, base in LOTS3.items():
        new, old = features.FEATURE_SETS[name], features.FEATURE_SETS[base]
        assert new.func is old.func
        assert new.keywords == old.keywords | {"id": name}
        assert {k for k, v in groups.items() if name in v} == {
            k for k, v in groups.items() if base in v
        }
        for table in (
            features.LOT_SNAPSHOTS,
            features.AREA_SNAPSHOTS,
            features.LPC_SNAPSHOTS,
            features.PLUTO_RELEASES_SNAPSHOTS,
            features.EXTRAS_SNAPSHOTS,
            features.DESCRIPTION_SOURCES,
        ):
            assert table[name] == table[base]
        assert features.LOT_DROP_SETS[name] == features.LOT_DROP_FILE
        assert name in features.CLASS_UNKNOWN_SETS
        assert base not in features.LOT_DROP_SETS
        assert base not in features.CLASS_UNKNOWN_SETS


def test_drop_list_reads_its_listing_ids():
    rows = [
        json.loads(line)
        for line in features.LOT_DROP_FILE.read_text().splitlines()
        if line.strip()
    ]
    assert {r["reason"] for r in rows} == {"wrong_building", "city_record_wrong"}
    drops = features.lot_drops(features.LOT_DROP_FILE)
    assert drops == {str(r["listing_id"]) for r in rows}
    assert len(drops) == 1274
    assert features.lot_drops(features.LOT_DROP_FILE) is drops


@pytest.mark.parametrize("name", [*LOTS3, *LOTS3.values()])
def test_build_sets_the_drops_for_the_lots3_sets_only(monkeypatch, name):
    seen = {}

    def probe(frame, train):
        seen["drops"] = features._LOT_DROPS.get()
        seen["class_unknown"] = features._CLASS_UNKNOWN.get()

    monkeypatch.setitem(features.FEATURE_SETS, name, probe)
    features.build(name, pd.DataFrame({"building": ["a"]}), np.ones(1, bool))
    if name in LOTS3:
        assert seen == {
            "drops": features.lot_drops(features.LOT_DROP_FILE),
            "class_unknown": True,
        }
    else:
        assert seen == {"drops": None, "class_unknown": False}
    assert features._LOT_DROPS.get() is None
    assert features._CLASS_UNKNOWN.get() is False


@pytest.fixture
def lots(tmp_path, monkeypatch):
    """A registry of three buildings, MapPLUTO for two of their lots (b's
    with no building class), a drop list holding listing 2, and a frame of
    four rows: listings 1 and 2 in building a, 3 in b, 4 in c (no lot)."""
    registry = tmp_path / "registry.parquet"
    pd.DataFrame(
        {
            "building": ["a", "b", "c"],
            "bbl": ["1000010001", "1000010002", None],
            "bin": ["1000001", "1000002", "1000003"],
            "latitude": [40.745, 40.746, 40.747],
            "longitude": [-74.000, -74.001, -74.002],
        }
    ).to_parquet(registry)
    pluto = tmp_path / "pluto.parquet"
    pd.DataFrame(
        {
            "bbl": ["1000010001", "1000010002"],
            "yearbuilt": [1910, 1965],
            "yearalter1": [2005, 0],
            "yearalter2": [0, 0],
            "numfloors": [5.0, 20.0],
            "unitsres": [10, 200],
            "resarea": [8000, 180000],
            "builtfar": [4.0, 10.0],
            "lotfront": [25.0, 100.0],
            "lotarea": [2500, 10000],
            "bldgclass": ["C4", None],
            "landmark": ["X", None],
            "histdist": ["Ladies' Mile", None],
            "pfirm15_flag": [None, None],
        }
    ).to_parquet(pluto)
    drop = tmp_path / "drop-lot.jsonl"
    drop.write_text(json.dumps({"listing_id": "2", "reason": "wrong_building"}) + "\n")
    monkeypatch.setattr(features, "REGISTRY_FILE", str(registry))
    monkeypatch.setattr(features, "PLUTO_FILE", str(pluto))
    monkeypatch.setitem(
        features.FEATURE_SETS,
        "empty",
        lambda frame, train: features.Features(
            "empty", [], [], np.zeros((len(frame), 0)), np.zeros(0)
        ),
    )
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b", "c"],
            "source_listing_id": [1, 2, 3, 4],
            "unit_id": ["a1", "a2", "b1", "c1"],
            "period": pd.to_datetime(["2020-01-01"] * 4),
        }
    )
    return frame, features.lot_drops(drop)


def _with(drops, class_unknown, f):
    tokens = (
        features._LOT_DROPS.set(drops),
        features._CLASS_UNKNOWN.set(class_unknown),
    )
    try:
        return f()
    finally:
        features._LOT_DROPS.reset(tokens[0])
        features._CLASS_UNKNOWN.reset(tokens[1])


def test_lot_buildings_drops_the_listed_rows_only(lots):
    frame, drops = lots
    assert features.lot_buildings(frame).tolist() == ["a", "a", "b", "c"]
    got = _with(drops, True, lambda: features.lot_buildings(frame))
    assert got.tolist() == ["a", features.NO_LOT, "b", "c"]
    assert frame.building.tolist() == ["a", "a", "b", "c"]


def test_a_dropped_row_reads_no_lot(lots):
    frame, drops = lots
    base = features.building_lots(frame)
    got = _with(drops, True, lambda: features.building_lots(frame))
    assert got.iloc[1].isna().all()
    kept = [0, 2, 3]
    pd.testing.assert_frame_equal(got.iloc[kept], base.iloc[kept])


def test_a_dropped_row_has_unknown_lot_terms(lots):
    frame, drops = lots
    # The dropped row is held out, so the training centres match the base's.
    train = np.array([True, False, True, True])
    pluto = lambda: features.pluto_v1(frame, train, id="t", base="empty")  # noqa: E731
    base = pluto()
    got = _with(drops, True, pluto)
    col = dict(zip(got.names, got.values.T))
    assert col["building class=unknown"].tolist() == [0, 1, 1, 1]
    assert col["building era=unknown"].tolist() == [0, 1, 0, 1]
    for flag in (
        "numfloors_unknown",
        "unitsres_unknown",
        "res_area_per_unit_unknown",
        "built_far_unknown",
    ):
        assert col[flag].tolist() == [0, 1, 0, 1]
    for name in ("log_numfloors", "log_unitsres", "log_built_far"):
        assert col[name][1] == 0.0
    assert col["landmark"].tolist() == [1, 0, 0, 0]
    assert col["historic_district"].tolist() == [1, 0, 0, 0]
    assert col["altered_since_2000"].tolist() == [1, 0, 0, 0]
    # Rows 0 and 2 have a lot and a known class: each term the base set has
    # reads the same for them.
    old = dict(zip(base.names, base.values.T))
    assert old["building class=other"].tolist() == [0, 0, 1, 1]
    assert set(got.names) - set(old) == {"building class=unknown"}
    assert set(old) - set(got.names) == {"building class=other"}
    for name, values in old.items():
        if name in col:
            np.testing.assert_array_equal(col[name][[0, 2]], values[[0, 2]], name)


def test_without_the_drops_pluto_is_unchanged(lots):
    """With no drops and no unknown class, a missing class stays in "other"
    and no row loses its lot."""
    frame, _ = lots
    train = np.ones(4, bool)
    got = features.pluto_v1(frame, train, id="t", base="empty")
    col = dict(zip(got.names, got.values.T))
    assert "building class=unknown" not in col
    assert col["building class=other"].tolist() == [0, 0, 1, 1]
    assert col["numfloors_unknown"].tolist() == [0, 0, 0, 1]
    assert col["landmark"].tolist() == [1, 1, 0, 0]


def test_a_dropped_row_keeps_its_position(lots):
    frame, drops = lots
    train = np.ones(4, bool)
    location = lambda: features.location_v1(frame, train, id="t", base="empty")  # noqa: E731
    base = location()
    got = _with(drops, True, location)
    assert got.names == base.names and len(got.names) > 0
    np.testing.assert_array_equal(got.values, base.values)
    assert np.abs(got.values[1]).sum() > 0


def test_a_dropped_row_has_no_sides_or_frontage(lots, monkeypatch):
    from rentfrontier import descriptions

    frame, drops = lots
    sides = pd.DataFrame(
        {"north": ["avenue"], "south": ["none"], "east": ["none"], "west": ["none"]},
        index=["a"],
    )
    frontage = pd.DataFrame(
        {"street_type": ["avenue"], "front": ["north"]}, index=["a"]
    )
    monkeypatch.setattr(features, "building_sides", lambda: sides)
    monkeypatch.setattr(features, "building_frontage", lambda: frontage)
    monkeypatch.setattr(descriptions, "attach", lambda f: pd.Series([""] * len(f)))
    frame = frame.assign(
        canonical_unit_url=[f"https://x/building/{b}/2A" for b in frame.building],
        window_north=["yes"] * 4,
        window_south=["unknown"] * 4,
        window_east=["unknown"] * 4,
        window_west=["unknown"] * 4,
        view_street=["unknown"] * 4,
        view_courtyard=["unknown"] * 4,
    )
    base = features.unit_sides(frame)
    got = _with(drops, True, lambda: features.unit_sides(frame))
    assert base.avenue.tolist() == [True, True, False, False]
    assert got.avenue.tolist() == [True, False, False, False]
    oriented = _with(drops, True, lambda: features.unit_orientation(frame))
    assert oriented.street_type.iloc[0] == "avenue"
    assert pd.isna(oriented.street_type.iloc[1])
    assert oriented.facing.iloc[1] == "unknown"
    assert features.unit_orientation(frame).facing.iloc[1] == "front"
