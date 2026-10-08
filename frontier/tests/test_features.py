"""Feature sets: unit-consistent bedrooms (unitbeds-v1)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from rentfrontier import features


def test_unit_bedrooms_is_the_lower_median_of_the_units_listings():
    frame = pd.DataFrame(
        {
            "unit_id": ["a", "a", "b", "b", "b", "c", "d", "d"],
            "bedrooms": [1, 2, 0, 1, 1, 3, 2, 2.4],
        }
    )
    np.testing.assert_array_equal(
        features.unit_bedrooms(frame), [1, 1, 1, 1, 1, 3, 2, 2]
    )


def test_unitbeds_is_registered_as_base_v1_by_unit():
    fn = features.FEATURE_SETS["unitbeds-v1"]
    assert fn.func is features.base_v1
    assert fn.keywords == {"id": "unitbeds-v1", "by_unit": True}


def test_unitattrs_adds_the_units_size_to_unitbeds():
    fn = features.FEATURE_SETS["unitattrs-v1"]
    assert fn.func is features.base_v1
    assert fn.keywords == {"id": "unitattrs-v1", "by_unit": True, "unit_size": True}


def test_unit_label_flags():
    import re

    labels = {
        "PHB": "penthouse",
        "PENTHOUSE": "penthouse",
        "GARDEN-A": "garden",
        "GRDN": "garden",
        "LLB": "lower_level",
        "BSMT": "lower_level",
    }
    for label, flag in labels.items():
        hits = [n for n, p in features.UNIT_LABEL_FLAGS.items() if re.search(p, label)]
        assert hits == [flag], (label, hits)
    for label in ("23C", "4B", "307", "G", "B", "PARK"):
        assert not any(re.search(p, label) for p in features.UNIT_LABEL_FLAGS.values())


def test_label_floor_number():
    urls = [
        "https://streeteasy.com/building/x/" + u
        for u in ("23c", "apt-4b", "307", "ph", "4th", "12", "3rd")
    ]
    got = features.label_floor_number(pd.DataFrame({"canonical_unit_url": urls}))
    np.testing.assert_array_equal(got, [23, 4, 3, np.nan, 4, np.nan, 3])


def test_unitdesc_is_the_description_flags_on_unitfloor():
    fn = features.FEATURE_SETS["unitdesc-v1"]
    assert fn.func is features.desc_v1
    assert fn.keywords == {"id": "unitdesc-v1", "base": "unitfloor-v2"}
    assert "unitdesc-v1" in features.EXTERNAL


def test_description_sets_record_their_source(monkeypatch):
    """Every feature set built on desc_v1, directly or through its base set, is
    listed, so run records hash the descriptions file (unitdesc-v1 did not
    match the old "desc" prefix test)."""
    from rentfrontier import run

    def reads_descriptions(fn):
        while True:
            if getattr(fn, "func", fn) is features.desc_v1:
                return True
            base = getattr(fn, "keywords", {}).get("base")
            if base is None:
                return False
            fn = features.FEATURE_SETS[base]

    built_on_desc = {
        name for name, fn in features.FEATURE_SETS.items() if reads_descriptions(fn)
    }
    assert "unitdescpluto-v1" in built_on_desc
    assert built_on_desc == features.DESCRIPTIONS
    monkeypatch.setattr(run.data, "sha256", lambda path: "sha")
    for name in built_on_desc:
        assert run.feature_sources(name)["descriptions"]["sha256"] == "sha"
    assert "descriptions" not in run.feature_sources("unitfloor-v2")


def test_unitdescpluto_is_the_building_columns_on_unitdesc():
    fn = features.FEATURE_SETS["unitdescpluto-v1"]
    assert fn.func is features.pluto_v1
    assert fn.keywords == {"id": "unitdescpluto-v1", "base": "unitdesc-v1"}
    assert "unitdescpluto-v1" in features.EXTERNAL


def test_unitdescplutotransit_is_transit_on_unitdescpluto(monkeypatch):
    from rentfrontier import run

    fn = features.FEATURE_SETS["unitdescplutotransit-v2"]
    assert fn.func is features.transit_v2
    assert fn.keywords == {"id": "unitdescplutotransit-v2", "base": "unitdescpluto-v1"}
    assert "unitdescplutotransit-v2" in features.EXTERNAL
    # Every set built on transit_v2 records the stations snapshot.
    on_transit = {
        name
        for name, f in features.FEATURE_SETS.items()
        if getattr(f, "func", f) is features.transit_v2
    }
    assert on_transit == features.SUBWAY
    monkeypatch.setattr(run.data, "sha256", lambda path: "sha")
    sources = run.feature_sources("unitdescplutotransit-v2")
    assert {"registry", "pluto", "subway", "descriptions"} <= sources.keys()
    assert "subway" not in run.feature_sources("unitdescpluto-v1")


def test_transit_counts_only_stations_open_that_month(monkeypatch, tmp_path):
    registry = pd.DataFrame(
        {"building": ["a", "b"], "latitude": [40.0, 40.0], "longitude": [-74.0, -73.9]}
    )
    stops = pd.DataFrame(
        {
            "gtfs_stop_id": ["1", "726"],
            "daytime_routes": ["1 2", "7"],
            # "1" is ~850 m east of "a"; "726" is 80 m from "a".
            "gtfs_latitude": [40.0, 40.00072],
            "gtfs_longitude": [-73.99, -74.0],
        }
    )
    registry.to_parquet(tmp_path / "registry.parquet")
    stops.to_parquet(tmp_path / "subway.parquet")
    monkeypatch.setattr(features, "REGISTRY_FILE", str(tmp_path / "registry.parquet"))
    monkeypatch.setattr(features, "SUBWAY_FILE", str(tmp_path / "subway.parquet"))
    # 726 opened 2015-09-13: not yet open for September 2015, open from October.
    assert features.stops_not_open("2015-09-01") == {"726"}
    assert features.stops_not_open("2015-10-01") == frozenset()
    now = features.building_transit(["a"])
    before = features.building_transit(["a"], features.stops_not_open("2015-09-01"))
    assert now.subway_m[0] < 100 and now.routes_10min[0] == 1
    assert before.subway_m[0] > 800 and before.routes_10min[0] == 0


def test_location_bumps_cover_the_sites_with_unit_mean_square():
    rng = np.random.default_rng(0)
    sites = rng.uniform(0, 1500, size=(200, 2))
    bumps = features.location_bumps(sites, sites)
    assert np.isclose((bumps**2).sum(1).mean(), 1.0)
    # A point far from every site sees (almost) no bump.
    assert features.location_bumps(np.array([[1e5, 1e5]]), sites).max() < 1e-12
    # Neighbouring points share bumps; points 2 km apart do not.
    near = features.location_bumps(np.array([[700.0, 700.0], [750.0, 700.0]]), sites)
    far = features.location_bumps(np.array([[0.0, 0.0], [0.0, 2000.0]]), sites)
    cos = lambda m: m[0] @ m[1] / np.linalg.norm(m[0]) / np.linalg.norm(m[1])
    assert cos(near) > 0.9 and cos(far) < 0.05


def test_unitdescplutoloc_is_the_location_surface_on_unitdescpluto():
    fn = features.FEATURE_SETS["unitdescplutoloc-v1"]
    assert fn.func is features.location_v1
    assert fn.keywords == {"id": "unitdescplutoloc-v1", "base": "unitdescpluto-v1"}
    assert "unitdescplutoloc-v1" in features.EXTERNAL


def test_unitdescpluto_v2_is_the_building_facts_without_the_flood_zone():
    fn = features.FEATURE_SETS["unitdescpluto-v2"]
    assert fn.func is features.pluto_v1
    assert fn.keywords == {
        "id": "unitdescpluto-v2",
        "base": "unitdesc-v1",
        "flood_zone": False,
    }
    assert {"unitdescpluto-v2"} <= features.EXTERNAL & features.DESCRIPTIONS


def test_unitdescpluto_v3_dates_alterations_by_the_latest():
    fn = features.FEATURE_SETS["unitdescpluto-v3"]
    assert fn.func is features.pluto_v1
    assert fn.keywords == {
        "id": "unitdescpluto-v3",
        "base": "unitdesc-v1",
        "flood_zone": False,
        "latest_alteration": True,
    }
    assert {"unitdescpluto-v3"} <= features.EXTERNAL & features.DESCRIPTIONS


def test_latest_alteration_takes_the_later_recorded_year(monkeypatch):
    """altered_since_2000 per lot: yearalter1 alone, or the later of the two
    recorded alterations (0 = none recorded)."""
    pairs = [(1987, 2001), (0, 2014), (2008, 2001), (1999, 0), (0, 0), (np.nan, np.nan)]
    n = len(pairs)
    lots = pd.DataFrame(
        {
            "yearbuilt": [1920] * n,
            "yearalter1": [a for a, _ in pairs],
            "yearalter2": [b for _, b in pairs],
            "numfloors": [6] * n,
            "unitsres": [20] * n,
            "resarea": [20_000] * n,
            "builtfar": [4.0] * n,
            "lotfront": [50] * n,
            "bldgclass": ["D1"] * n,
            "landmark": [None] * n,
            "histdist": [None] * n,
            "pfirm15_flag": [None] * n,
        }
    )
    frame = pd.DataFrame({"building": [f"b{i}" for i in range(n)]})
    empty = features.Features("empty", [], [], np.zeros((n, 0)), np.zeros(0))
    monkeypatch.setitem(features.FEATURE_SETS, "empty", lambda frame, train: empty)
    monkeypatch.setattr(features, "building_lots", lambda frame: lots)
    train = np.ones(n, dtype=bool)

    def altered(**kw):
        f = features.pluto_v1(frame, train, base="empty", **kw)
        return f.values[:, f.names.index("altered_since_2000")].tolist()

    assert altered(latest_alteration=True) == [1, 1, 1, 0, 0, 0]
    assert altered() == [0, 0, 1, 0, 0, 0]


def test_frontage_street_parses_addresses():
    assert features.frontage_street("100 West 15 Street, New York") == (
        "W  15 ST",
        "side street",
        "crosstown",
    )
    assert features.frontage_street("200 WEST 23 STREET")[1] == "wide street"
    assert features.frontage_street("300 8 Avenue") == ("8 AVE", "avenue", "avenue")
    assert (
        features.frontage_street("1 Avenue Of The Americas")[0] == "AVE OF THE AMERICAS"
    )
    assert features.frontage_street("4 Chelsea Square") == (None, None, None)
    # Sixth Avenue's centerlines are Avenue of the Americas; spelled-out avenues parse.
    assert features.frontage_street("545 6 Avenue")[0] == "AVE OF THE AMERICAS"
    assert features.frontage_street("138 Seventh Avenue") == (
        "7 AVE",
        "avenue",
        "avenue",
    )
    assert features.frontage_street("212 Rear West 16 Street") == (None, None, None)


def test_unit_orientation_pools_evidence_over_the_unit(monkeypatch):
    from rentfrontier import descriptions

    frontage = pd.DataFrame(
        {"street_type": ["side street", "side street"], "front": ["north", "north"]},
        index=pd.Index(["walkup", "tower"], name="building"),
    )
    monkeypatch.setattr(features, "building_frontage", lambda: frontage)
    rows = [
        # (building, unit, label, windows, text)
        ("tower", "u1", "5A", {"north"}, ""),
        ("tower", "u1", "5A", set(), ""),  # same unit, no windows this time
        ("tower", "u2", "6B", {"south"}, ""),
        ("tower", "u3", "7C", {"north", "south"}, ""),
        ("tower", "u4", "8D", {"east"}, ""),
        ("walkup", "u5", "2F", set(), ""),
        ("walkup", "u6", "2R", set(), ""),
        ("tower", "u7", "9E", set(), "A quiet rear apartment."),
        ("tower", "u8", "10F", set(), ""),  # F is a line letter here
        ("nofront", "u9", "3A", {"east"}, ""),  # no frontage: a window says nothing
        ("tower", "u10", "11G", set(), "A sunny floor-through."),
    ]
    frame = pd.DataFrame(
        {
            "building": [r[0] for r in rows],
            "unit_id": [r[1] for r in rows],
            "canonical_unit_url": [f"https://x/building/{r[0]}/{r[2]}" for r in rows],
            **{
                f"window_{d}": ["yes" if d in r[3] else "unknown" for r in rows]
                for d in ("north", "south", "east", "west")
            },
            "view_street": ["unknown"] * len(rows),
            "view_courtyard": ["unknown"] * len(rows),
        }
    )
    monkeypatch.setattr(
        descriptions, "attach", lambda f: pd.Series([r[4] for r in rows])
    )
    got = features.unit_orientation(frame).facing.tolist()
    assert got == [
        "front",
        "front",
        "rear",
        "front and rear",
        "side",
        "front",
        "rear",
        "rear",
        "unknown",
        "unknown",
        "front and rear",
    ]


def test_unitfacing_records_the_basemap(monkeypatch):
    from rentfrontier import run

    fn = features.FEATURE_SETS["unitfacing-v2"]
    assert fn.func is features.facing_v2
    assert fn.keywords == {"id": "unitfacing-v2", "base": "unitdescpluto-v3"}
    on_facing = {
        name
        for name, f in features.FEATURE_SETS.items()
        if getattr(f, "func", f) is features.facing_v2
    }
    assert on_facing <= features.BASEMAP
    monkeypatch.setattr(run.data, "sha256", lambda path: "sha")
    sources = run.feature_sources("unitfacing-v2")
    assert {"registry", "pluto", "descriptions", "basemap"} <= sources.keys()


def test_street_kind():
    assert features.street_kind("8 AVE", "1") == "avenue"
    assert features.street_kind("AVE OF THE AMERICAS", "1") == "avenue"
    assert features.street_kind("WEST ST", "2") == "avenue"  # the West Side Highway
    assert features.street_kind("W  23 ST", "1") == "wide street"
    assert features.street_kind("W  22 ST", "1") == "side street"
    assert features.street_kind("HIGH LINE", "6") is None


def test_unit_sides_uses_every_side_of_the_building(monkeypatch):
    from rentfrontier import descriptions

    # A corner building: north on a side street, west on an avenue, rear to the south.
    sides = pd.DataFrame(
        {
            "north": ["side street"],
            "south": ["none"],
            "east": ["none"],
            "west": ["avenue"],
        },
        index=["corner"],
    )
    frontage = pd.DataFrame(
        {"street_type": ["side street"], "front": ["north"]}, index=["corner"]
    )
    monkeypatch.setattr(features, "building_sides", lambda: sides)
    monkeypatch.setattr(features, "building_frontage", lambda: frontage)
    rows = [
        ("u1", {"west"}, ""),  # onto the avenue
        ("u2", {"north", "west"}, ""),  # corner unit: both streets
        ("u3", {"south"}, ""),  # rear
        ("u4", set(), "Street-facing one bedroom."),  # text: the address street
        ("u5", set(), ""),  # no evidence
    ]
    frame = pd.DataFrame(
        {
            "building": ["corner"] * len(rows),
            "unit_id": [r[0] for r in rows],
            "canonical_unit_url": [
                f"https://x/building/corner/{i}A" for i in range(len(rows))
            ],
            **{
                f"window_{d}": ["yes" if d in r[1] else "unknown" for r in rows]
                for d in ("north", "south", "east", "west")
            },
            "view_street": ["unknown"] * len(rows),
            "view_courtyard": ["unknown"] * len(rows),
        }
    )
    monkeypatch.setattr(
        descriptions, "attach", lambda f: pd.Series([r[2] for r in rows])
    )
    got = features.unit_sides(frame)
    assert got.avenue.tolist() == [True, True, False, False, False]
    assert got["side street"].tolist() == [False, True, False, True, False]
    assert got["none"].tolist() == [False, False, True, False, False]
    assert not got["wide street"].any()


def test_facing_sets_record_basemap_and_footprints(monkeypatch):
    from rentfrontier import run

    fn = features.FEATURE_SETS["unitfacing-v3"]
    assert fn.func is features.facing_v3

    def on_facing(f):
        """A facing set, or a set built on one (its base chain)."""
        if getattr(f, "func", f) in (features.facing_v3, features.facing_v4):
            return True
        base = getattr(f, "keywords", {}).get("base")
        return base is not None and on_facing(features.FEATURE_SETS[base])

    on_v3 = {n for n, f in features.FEATURE_SETS.items() if on_facing(f)}
    assert on_v3 == features.FOOTPRINTS and on_v3 <= features.BASEMAP
    monkeypatch.setattr(run.data, "sha256", lambda path: "sha")
    for name in ("unitfacing-v3", "unitfacing-v4", "unitfacing-v5", "unitnoise-v1"):
        assert {"basemap", "footprints"} <= run.feature_sources(name).keys()


def _box(x0, y0, x1, y1):
    """A counter-clockwise rectangle outline in grid metres."""
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], float)


def _streets(*lines):
    starts = np.array([a for a, _, _ in lines], float)
    ends = np.array([b for _, b, _ in lines], float)
    return starts, ends, np.array([k for _, _, k in lines])


NO_OCCLUDERS = (np.zeros((0, 2)), np.zeros((0, 2)))


def test_facade_sides_finds_the_avenue_of_a_corner_building():
    # A 7 m avenue front at a corner: the cross street's centerline (13.5 m,
    # sideways) is nearer than the avenue's (15 m, outward).
    streets = _streets(
        ((-15, -100), (-15, 100), "avenue"), ((-15, 16), (100, 16), "side street")
    )
    sides = features.facade_sides(_box(0, 0, 20, 7), streets, NO_OCCLUDERS)
    assert sides["west"] == "avenue" and sides["north"] == "side street"
    assert sides["east"] == "none" and sides["south"] == "none"


def test_facade_sides_party_walls_and_rear_yards_see_no_street():
    streets = _streets(
        ((-40, -100), (-40, 100), "avenue"),
        ((-100, 29), (100, 29), "side street"),
        ((-100, -40), (100, -40), "side street"),
    )
    ring = _box(0, 0, 8, 20)
    open_lot = features.facade_sides(ring, streets, NO_OCCLUDERS)
    assert open_lot["west"] == "avenue" and open_lot["south"] == "side street"
    # A neighbour against the west wall and one across the rear yard.
    neighbours = [_box(-8, 0, -0.1, 20), _box(0, -30, 8, -10)]
    occluders = (
        np.concatenate([r[:-1] for r in neighbours]),
        np.concatenate([r[1:] for r in neighbours]),
    )
    sides = features.facade_sides(ring, streets, occluders)
    assert sides["north"] == "side street"
    assert sides["west"] == "none" and sides["south"] == "none"


def test_facade_sides_keep_a_narrow_front_between_recessed_walls():
    # A 6 m front on the avenue, flanked by walls set back 20 m behind
    # neighbours: two of three west samples are blocked, the front sees it all.
    ring = np.array(
        [
            [0, 0],
            [30, 0],
            [30, 26],
            [0, 26],
            [0, 16],
            [-20, 16],
            [-20, 10],
            [0, 10],
            [0, 0],
        ],
        float,
    )
    streets = _streets(((-40, -100), (-40, 100), "avenue"))
    neighbours = [_box(-38, 0, -1, 9.5), _box(-38, 16.5, -1, 26)]
    occluders = (
        np.concatenate([r[:-1] for r in neighbours]),
        np.concatenate([r[1:] for r in neighbours]),
    )
    assert features.facade_sides(ring, streets, occluders)["west"] == "avenue"


def test_facade_sides_look_straight_out_not_diagonally():
    # The avenue's centerline ends beside the building: a west wall cannot see
    # a street that is only diagonally in front of it.
    streets = _streets(((-15, 40), (-15, 100), "avenue"))
    sides = features.facade_sides(_box(0, 0, 20, 20), streets, NO_OCCLUDERS)
    assert sides["west"] == "none"


def test_facade_sides_sample_short_edges_and_their_own_walls_block():
    # A 2.5 m notch still gets a sample. In a U-shaped outline the inner wall
    # of one arm looks across the courtyard into the other arm: its own walls
    # block it, so only the outer walls see the avenue to the west.
    streets = _streets(((-100, 30), (100, 30), "side street"))
    notch = np.array(
        [
            [0, 0],
            [10, 0],
            [10, 20],
            [6, 20],
            [6, 21.5],
            [3.5, 21.5],
            [3.5, 20],
            [0, 20],
            [0, 0],
        ],
        float,
    )
    assert features.facade_sides(notch, streets, NO_OCCLUDERS)["north"] == "side street"
    u = np.array(
        [
            [0, 0],
            [30, 0],
            [30, 20],
            [20, 20],
            [20, 5],
            [10, 5],
            [10, 20],
            [0, 20],
            [0, 0],
        ],
        float,
    )
    west = _streets(((-10, -100), (-10, 100), "avenue"))
    # Only the inner wall at x=20 faces west from the right arm: with the left
    # arm cut away, the right arm alone would see the avenue through the gap.
    right_arm = np.array([[20, 0], [30, 0], [30, 20], [20, 20], [20, 0]], float)
    assert features.facade_sides(right_arm, west, NO_OCCLUDERS)["west"] == "avenue"
    wing = (u[:-1][5:7], u[1:][5:7])  # the left arm's inner wall, x=10
    assert features.facade_sides(right_arm, west, wing)["west"] == "none"
    assert features.facade_sides(u, west, NO_OCCLUDERS)["west"] == "avenue"


def test_unitdescpluto_v4_reads_the_corrected_registry(monkeypatch):
    seen = []

    def fake_lots(frame):
        seen.append(features._LOTS.get())
        return pd.DataFrame(index=range(len(frame)))

    monkeypatch.setattr(features, "building_lots", fake_lots)
    monkeypatch.setitem(
        features.FEATURE_SETS,
        "probe-v4",
        lambda frame, train: features.building_lots(frame),
    )
    monkeypatch.setitem(
        features.LOT_SNAPSHOTS, "probe-v4", {"registry": "r2", "pluto": "p2"}
    )
    frame = pd.DataFrame({"building": ["a"]})
    features.build("probe-v4", frame, np.array([True]))
    assert seen == [("r2", "p2")]
    assert features._LOTS.get() is None  # reset after the build
    files = features.lot_files("unitdescpluto-v4")
    assert files == {
        "registry": features.REGISTRY_V2_FILE,
        "pluto": features.PLUTO_V2_FILE,
    }
    assert features.lot_files("unitdescpluto-v5") == {
        "registry": features.REGISTRY_V3_FILE,
        "pluto": features.PLUTO_V3_FILE,
    }
    assert features.lot_files("unitdescpluto-v3") == {
        "registry": features.REGISTRY_FILE,
        "pluto": features.PLUTO_FILE,
    }


def test_building_violations_count_the_trailing_year_only(tmp_path, monkeypatch):
    registry = pd.DataFrame(
        {"building": ["a", "b"], "bin": ["1000001", "1000000"], "bbl": ["1", "2"]}
    )
    hpd = pd.DataFrame(
        {
            "violationid": ["v1", "v2", "v3", "v4", "v5"],
            "bin": ["1000001", "1000001", "1000001", "1000001", "1000000"],
            "bbl": ["1", "1", "1", "1", "2"],
            "class": ["B", "C", "A", "B", "C"],
            "inspectiondate": [
                "2020-03-01",  # in the year before 2020-06
                "2019-07-15",  # in it too
                "2020-04-01",  # class A: not counted
                "2020-06-15",  # after the listing's month began: not counted
                "2020-01-01",  # b by lot (placeholder BIN)
            ],
        }
    )
    registry.to_parquet(tmp_path / "r.parquet")
    hpd.to_parquet(tmp_path / "h.parquet")
    monkeypatch.setattr(features, "REGISTRY_FILE", str(tmp_path / "r.parquet"))
    monkeypatch.setattr(features, "HPD_FILE", str(tmp_path / "h.parquet"))
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b", "c"],
            "period": pd.to_datetime(
                ["2020-06-01", "2021-09-01", "2020-06-01", "2020-06-01"]
            ),
        }
    )
    assert features.building_violations(frame).tolist() == [2.0, 0.0, 1.0, 0.0]


def test_facing_v4_marks_loud_streets_on_low_floors(monkeypatch):
    frame = pd.DataFrame({"unit_id": ["a", "b", "c", "d"]})
    looks = pd.DataFrame(
        {
            "avenue": [True, True, False, False],
            "wide street": [False, False, True, True],
            "side street": [False] * 4,
            "none": [False] * 4,
        }
    )
    base = features.Features("b", ["x"], ["g"], np.zeros((4, 1)), np.ones(1))
    monkeypatch.setitem(features.FEATURE_SETS, "probe-base", lambda f, t: base)
    monkeypatch.setattr(features, "unit_sides", lambda f: looks)
    monkeypatch.setattr(
        features, "row_floor", lambda f: pd.Series([2.0, 9.0, 4.0, np.nan])
    )
    out = features.facing_v4(frame, np.ones(4, bool), base="probe-base")
    cols = {n: out.values[:, i] for i, n in enumerate(out.names)}
    assert cols["looks onto an avenue, floors 1-4"].tolist() == [1, 0, 0, 0]
    assert cols["looks onto a wide street, floors 1-4"].tolist() == [0, 0, 1, 0]


def test_facing_reads_the_build_registry(monkeypatch):
    """building_sides and building_frontage read the registry of the set being
    built (LOT_SNAPSHOTS), with the grid origin of the first registry."""
    seen = []
    monkeypatch.setattr(
        features, "_building_sides", lambda path, *area: seen.append(path) or path
    )
    monkeypatch.setattr(
        features,
        "_building_frontage",
        lambda path, *area: seen.append(path) or path,
    )
    assert features.building_sides() == features.REGISTRY_FILE
    token = features._LOTS.set(("r3", "p3"))
    try:
        assert features.building_sides() == "r3"
        assert features.building_frontage() == "r3"
    finally:
        features._LOTS.reset(token)
    assert features.building_frontage() == features.REGISTRY_FILE
    assert features.lot_files("unitfacing-v5") == {
        "registry": features.REGISTRY_V3_FILE,
        "pluto": features.PLUTO_V3_FILE,
    }
    assert features.lot_files("unitfacing-v4")["registry"] == features.REGISTRY_FILE


def test_noise_kinds():
    t = pd.DataFrame(
        {
            "complaint_type": [
                "Noise - Street/Sidewalk",
                "Noise - Commercial",
                "Noise",
                "Noise",
                "Noise - Residential",
                "Noise - Helicopter",
            ],
            "descriptor": [
                "Loud Talking",
                "Loud Music/Party",
                "Noise: Construction Before/After Hours (NM1)",
                "Noise, Barking Dog (NR5)",
                "Loud Music/Party",
                "Other",
            ],
        }
    )
    assert features.noise_kind(t).where(lambda k: k.notna(), None).tolist() == [
        "street and nightlife",
        "street and nightlife",
        "construction",
        None,
        None,
        None,
    ]


def test_nearby_noise_counts_the_year_before_against_chelsea(monkeypatch):
    t = lambda *d: np.array(d, dtype="datetime64[ns]")
    times = {
        "street and nightlife": {
            # a: 3 complaints in 2020, b: 1; nothing in 2021.
            "a": t("2020-02-01", "2020-06-01", "2020-12-15"),
            "b": t("2020-03-01"),
        },
        "construction": {"a": t(), "b": t()},
    }
    monkeypatch.setattr(features, "_noise_times", lambda path, noise_file: times)
    frame = pd.DataFrame(
        {
            "building": ["a", "b", "a", "c"],
            "period": pd.to_datetime(
                ["2021-01-01", "2021-01-01", "2022-06-01", "2021-01-01"]
            ),
        }
    )
    out = features.nearby_noise(frame)
    chelsea = (np.log2(4) + np.log2(2)) / 2
    np.testing.assert_allclose(
        out["street and nightlife"],
        [np.log2(4) - chelsea, np.log2(2) - chelsea, 0.0, 0.0],
    )
    np.testing.assert_allclose(out["construction"], 0.0)


def test_stated_bedrooms_reads_the_first_sentence():
    assert (
        features.stated_bedrooms("Sunny 2-bedroom on Bank St. Has a 3 bed feel.") == 2
    )
    assert features.stated_bedrooms("ONE BED with a garden") == 1
    assert features.stated_bedrooms("Studio, top floor") == 0
    assert features.stated_bedrooms("Renovated 3BR") == 3
    assert features.stated_bedrooms("Sunny 1 bdrm, high floor") == 1
    assert np.isnan(features.stated_bedrooms("Rare 1.5 bedroom with 2 baths"))
    assert np.isnan(features.stated_bedrooms("Charming home\n2 bedrooms"))
    assert np.isnan(features.stated_bedrooms("Charming home<br>2 bedrooms"))
    assert np.isnan(features.stated_bedrooms("Lovely home. 2 bedrooms."))
    assert np.isnan(features.stated_bedrooms(""))


def test_nb_bedtext_flags_ads_stating_another_count(monkeypatch):
    import pandas as pd
    from rentfrontier import descriptions

    fn = features.FEATURE_SETS["nb-bedtext-v1"]
    assert fn.func is features.bedtext_v1
    assert fn.keywords == {"id": "nb-bedtext-v1", "base": "nb-facing-v2"}
    for files in (
        features.description_files,
        features.lot_files,
        features.area_files,
    ):
        assert files("nb-bedtext-v1") == files("nb-facing-v2")
    from rentfrontier import run

    monkeypatch.setattr(run.data, "sha256", lambda path: "sha")
    assert run.feature_sources("nb-bedtext-v1") == run.feature_sources("nb-facing-v2")
    frame = pd.DataFrame(
        {"audit_id": list("abcdef"), "bedrooms": [2, 2, 1, 0, 1, np.nan]}
    )
    text = pd.Series(
        ["One bedroom flex.", "Huge 3 bed loft", "1 br", None, "Bright.", "2 bed"]
    )
    monkeypatch.setattr(descriptions, "attach", lambda f: text)
    monkeypatch.setitem(
        features.FEATURE_SETS,
        "stub-base",
        lambda f, t: features.Features(
            "stub-base", [], [], np.zeros((len(f), 0)), np.zeros(0)
        ),
    )
    out = features.bedtext_v1(frame, np.ones(6, bool), id="t", base="stub-base")
    got = dict(zip(out.names, out.values.T))
    assert got["text:states_fewer_bedrooms"].tolist() == [1, 0, 0, 0, 0, 0]
    assert got["text:states_more_bedrooms"].tolist() == [0, 1, 0, 0, 0, 0]


def test_as_of_sets_count_only_alterations_done_by_the_listing(monkeypatch):
    import pandas as pd

    lots = pd.DataFrame(
        {
            "yearbuilt": [1920] * 4,
            "yearalter1": [1990, 2005, None, 2001],
            "yearalter2": [2015, 0, 0, 2012],
            "numfloors": [5] * 4,
            "unitsres": [10] * 4,
            "resarea": [8000] * 4,
            "builtfar": [4.0] * 4,
            "lotfront": [25.0] * 4,
            "bldgclass": ["C1"] * 4,
            "landmark": [None] * 4,
            "histdist": [None] * 4,
            "pfirm15_flag": [None] * 4,
        }
    )
    monkeypatch.setattr(features, "building_lots", lambda f: lots)
    monkeypatch.setitem(
        features.FEATURE_SETS,
        "stub-base",
        lambda f, t: features.Features(
            "stub-base", [], [], np.zeros((len(f), 0)), np.zeros(0)
        ),
    )
    frame = pd.DataFrame(
        {
            "period": pd.to_datetime(
                ["2012-06-01", "2012-06-01", "2020-01-01", "2010-01-01"]
            )
        }
    )

    def flag(as_of):
        token = features._AS_OF.set(as_of)
        try:
            out = features.pluto_v1(
                frame,
                np.ones(4, bool),
                id="t",
                base="stub-base",
                latest_alteration=True,
            )
        finally:
            features._AS_OF.reset(token)
        return dict(zip(out.names, out.values.T))["altered_since_2000"].tolist()

    # Present-day: 2015 and 2012 alterations count for 2012 and 2010 listings.
    assert flag(False) == [1, 1, 0, 1]
    # As of the listing: the 2015 alteration is after the 2012 listing (and 1990
    # is before 2000); the 2001 alteration counts for the 2010 listing.
    assert flag(True) == [0, 1, 0, 1]
    # A same-year alteration waits for the next year.
    same = frame.assign(period=pd.to_datetime(["2015-06-01"] * 4))
    token = features._AS_OF.set(True)
    try:
        out = features.pluto_v1(
            same, np.ones(4, bool), id="t", base="stub-base", latest_alteration=True
        )
    finally:
        features._AS_OF.reset(token)
    assert dict(zip(out.names, out.values.T))["altered_since_2000"].tolist() == [
        0,
        1,
        0,
        1,
    ]
    # build() sets the flag for the as-of sets only, and resets it after.
    seen = {}
    for name in ("nb-bedtext-v1", "nb-bedtext-v2"):
        monkeypatch.setitem(
            features.FEATURE_SETS,
            name,
            lambda f, t, name=name: seen.setdefault(name, features._AS_OF.get()),
        )
        features.build(name, frame, np.ones(4, bool))
    assert seen == {"nb-bedtext-v1": False, "nb-bedtext-v2": True}
    assert features._AS_OF.get() is False
    assert {"nb-facing-v3", "nb-bedtext-v2"} <= features.AS_OF_SETS
    for files in (features.lot_files, features.area_files, features.description_files):
        assert files("nb-bedtext-v2") == files("nb-bedtext-v1")


def test_relist_counts_only_earlier_listings_of_the_unit(monkeypatch):
    import pandas as pd

    monkeypatch.setitem(
        features.FEATURE_SETS,
        "stub-base",
        lambda f, t: features.Features(
            "stub-base", [], [], np.zeros((len(f), 0)), np.zeros(0)
        ),
    )
    frame = pd.DataFrame(
        {
            "unit_id": ["u1", "u1", "u2", "u1"],
            "price_at": pd.to_datetime(
                ["2020-03-01", "2020-01-01", "2020-01-01", "2021-01-01"], utc=True
            ),
        }
    )
    out = features.relist_v1(frame, np.ones(4, bool), id="t", base="stub-base")
    got = dict(zip(out.names, out.values.T))
    assert got["first_listing_of_unit"].tolist() == [0, 1, 1, 0]
    gap = got["log_months_since_last_listing"]
    # 60 days after u1's first listing, then 306 days after that; centred.
    raw = np.log1p(np.array([60, 306]) / 30.4)
    np.testing.assert_allclose(gap[[0, 3]], raw - raw.mean())
    assert gap[1] == gap[2] == 0.0
    assert features.FEATURE_SETS["nb-relist-v1"].keywords["base"] == "nb-bedtext-v2"
    assert "nb-relist-v1" in features.AS_OF_SETS


def test_coded_reads_outdoor_types_and_extra_rooms(monkeypatch, tmp_path):
    import pandas as pd

    path = tmp_path / "extras.parquet"
    pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4"],
            "outdoor_types": ["TERRACE|PRIVATE_ROOF_DECK", "BALCONY", "", "GARDEN"],
            "room_count": [5, 3, 0, 2],
        }
    ).to_parquet(path)
    monkeypatch.setattr(features, "LISTING_EXTRAS_FILE", str(path))
    monkeypatch.setitem(
        features.FEATURE_SETS,
        "stub-base",
        lambda f, t: features.Features(
            "stub-base", [], [], np.zeros((len(f), 0)), np.zeros(0)
        ),
    )
    frame = pd.DataFrame(
        {"source_listing_id": [1, 2, 3, 4, 9], "bedrooms": [1.0, 1.0, 0.0, 1.0, 1.0]}
    )
    out = features.coded_v1(frame, np.ones(5, bool), id="t", base="stub-base")
    got = dict(zip(out.names, out.values.T))
    assert got["outdoor:terrace"].tolist() == [1, 0, 0, 0, 0]
    assert got["outdoor:roof_deck"].tolist() == [1, 0, 0, 0, 0]
    assert got["outdoor:balcony"].tolist() == [0, 1, 0, 0, 0]
    assert got["outdoor:garden"].tolist() == [0, 0, 0, 1, 0]
    # extra rooms: 5-1=4 -> 4+; 3-1=2 (reference); 0 rooms -> unknown; 2-1=1 -> 0-1
    level = {n.split("=", 1)[1]: got[n].tolist() for n in out.names if "=" in n}
    assert level["4+"] == [1, 0, 0, 0, 0]
    assert level["0-1"] == [0, 0, 0, 1, 0]
    assert level["unknown"] == [0, 0, 1, 0, 1]
    assert "nb-coded-v1" in features.LISTING_EXTRAS
    from rentfrontier import run

    monkeypatch.setattr(run.data, "sha256", lambda p: "sha")
    assert "listing_extras" in run.feature_sources("nb-coded-v1")


def test_prevprice_reads_only_changes_before_the_listing(monkeypatch, tmp_path):
    import json

    import pandas as pd

    path = tmp_path / "history.parquet"
    pd.DataFrame(
        {
            "listing_id": ["10", "11", "20"],
            "price_changes": [
                # u1's first listing: cut twice, the second cut after u1's next listing.
                json.dumps(
                    [
                        ["2020-01-01T10:00:00.000-05:00", 5000],
                        ["2020-02-01T10:00:00.000-05:00", 4500],
                        ["2020-06-01T10:00:00.000-04:00", 4000],
                    ]
                ),
                json.dumps([["2020-05-01T10:00:00.000-04:00", 4800]]),
                json.dumps([["2020-01-01T10:00:00.000-05:00", 3000]]),
            ],
        }
    ).to_parquet(path)
    monkeypatch.setattr(features, "PRICE_HISTORY_FILE", str(path))
    monkeypatch.setitem(
        features.FEATURE_SETS,
        "stub-base",
        lambda f, t: features.Features(
            "stub-base", [], [], np.zeros((len(f), 0)), np.zeros(0)
        ),
    )
    frame = pd.DataFrame(
        {
            "unit_id": ["u1", "u1", "u2", "u1"],
            "source_listing_id": [11, 10, 20, 12],
            "asking_rent": [4800.0, 5000.0, 3000.0, 6000.0],
            "price_at": pd.to_datetime(
                ["2020-05-01", "2020-01-01", "2020-01-01", "2021-01-01"], utc=True
            ),
        }
    )
    out = features.prevprice_v1(frame, np.ones(4, bool), id="t", base="stub-base")
    got = dict(zip(out.names, out.values.T))
    change = got["previous_listing_price_change"]
    # Row 0 sees listing 10 cut once by May (5000 -> 4500), not the June cut.
    np.testing.assert_allclose(change, [np.log(4500 / 5000), 0, 0, 0])
    # Row 3 follows listing 11 (never repriced); first listings get 0.
    count = got["log_previous_listing_repricings"]
    raw = np.log1p(np.array([1, 0]))
    np.testing.assert_allclose(count[[0, 3]], raw - raw.mean())
    assert count[1] == count[2] == 0.0
    assert features.FEATURE_SETS["nb-prevprice-v1"].keywords["base"] == "nb-coded-v1"
    assert "nb-prevprice-v1" in features.AS_OF_SETS
    # v2 keeps only the count, which reads no other row's ask.
    only = features.prevprice_v1(
        frame, np.ones(4, bool), id="t", base="stub-base", change=False
    )
    assert only.names == ["log_previous_listing_repricings"]
    np.testing.assert_allclose(only.values[:, 0], count)
    frame2 = frame.assign(asking_rent=[1.0, 9999.0, 3000.0, 6000.0])
    again = features.prevprice_v1(
        frame2, np.ones(4, bool), id="t", base="stub-base", change=False
    )
    np.testing.assert_allclose(again.values, only.values)
    assert "nb-prevprice-v2" in features.PRICE_HISTORY | features.AS_OF_SETS
    from rentfrontier import run

    monkeypatch.setattr(run.data, "sha256", lambda p: "sha")
    sources = run.feature_sources("nb-prevprice-v1")
    assert "price_history" in sources and "listing_extras" in sources


def test_prevprice_never_reads_the_rows_own_advertisement(monkeypatch, tmp_path):
    import json

    import pandas as pd

    path = tmp_path / "history.parquet"
    pd.DataFrame(
        {
            "listing_id": ["10", "20"],
            "price_changes": [
                json.dumps(
                    [["2020-01-01T00:00:00Z", 5000], ["2020-06-01T00:00:00Z", 4000]]
                ),
                # The current capture's own ad, cut before the capture.
                json.dumps(
                    [["2021-01-01T00:00:00Z", 6000], ["2021-02-01T00:00:00Z", 5400]]
                ),
            ],
        }
    ).to_parquet(path)
    monkeypatch.setattr(features, "PRICE_HISTORY_FILE", str(path))
    monkeypatch.setitem(
        features.FEATURE_SETS,
        "stub-base",
        lambda f, t: features.Features(
            "stub-base", [], [], np.zeros((len(f), 0)), np.zeros(0)
        ),
    )
    frame = pd.DataFrame(
        {
            "unit_id": ["u"] * 3,
            "source_listing_id": [10, 20, 20],  # ad 20: initial ask, then a capture
            "asking_rent": [5000.0, 6000.0, 5400.0],
            "price_at": pd.to_datetime(
                ["2020-01-01", "2021-01-01", "2021-03-01"], utc=True
            ),
        }
    )
    out = features.prevprice_v1(frame, np.ones(3, bool), id="t", base="stub-base")
    change = dict(zip(out.names, out.values.T))["previous_listing_price_change"]
    # Both rows of ad 20 read ad 10 (cut to 4000), never ad 20's own cut.
    np.testing.assert_allclose(change, [0, np.log(0.8), np.log(0.8)])


def test_line_orientation_reads_only_earlier_listings_of_other_units(monkeypatch):
    import pandas as pd

    def sides(frame):
        rows = pd.DataFrame(
            {
                "avenue": frame.s.to_numpy(),
                "wide street": False,
                "side street": False,
                "none": frame.r.to_numpy(),
            },
            index=frame.index,
        )
        return rows.groupby(frame.unit_id.to_numpy()).transform("any")

    monkeypatch.setattr(features, "unit_sides", sides)
    url = "https://streeteasy.com/building/b/{}".format
    frame = pd.DataFrame(
        {
            "audit_id": ["a1", "a2", "a3", "a4", "a5"],
            "unit_id": ["u3j", "u5j", "u5j", "u7j", "u4r"],
            "building": ["b"] * 5,
            "canonical_unit_url": [
                url("3j"),
                url("5j"),
                url("5j"),
                url("7j"),
                url("4r"),
            ],
            "price_at": pd.to_datetime(
                ["2020-01-01", "2019-01-01", "2021-01-01", "2020-01-01", "2018-01-01"],
                utc=True,
            ),
            # 3J shows the courtyard (2020); 4R, another line, faces the street.
            "s": [False, False, False, False, True],
            "r": [True, False, False, False, False],
        }
    )
    got = features.line_orientation(frame).tolist()
    # 5J in 2019 sees nothing earlier; in 2021 it sees 3J. 7J lists the same day
    # as 3J, so not after it. 3J never reads itself. 4R's line has no other unit.
    assert got == ["", "", "rear", "", ""]
    assert features.FEATURE_SETS["nb-lineface-v1"].keywords["base"] == "nb-coded-v1"
    assert "nb-lineface-v1" in features.AS_OF_SETS


def test_line_orientation_skips_labels_without_a_line(monkeypatch):
    import pandas as pd

    def sides(frame):
        return pd.DataFrame(
            {"avenue": False, "wide street": False, "side street": False, "none": True},
            index=frame.index,
        )

    monkeypatch.setattr(features, "unit_sides", sides)
    url = "https://streeteasy.com/building/b/{}".format
    frame = pd.DataFrame(
        {
            "audit_id": ["a1", "a2", "a3", "a4"],
            "unit_id": ["uph", "u12", "u3j", "u5j"],
            "building": ["b"] * 4,
            "canonical_unit_url": [url("ph"), url("12"), url("3j"), url("5j")],
            "price_at": pd.to_datetime(
                ["2019-01-01", "2019-06-01", "2020-01-01", "2021-01-01"], utc=True
            ),
        }
    )
    assert features.line_orientation(frame).tolist() == ["", "", "", "rear"]


def test_line_orientation_votes_per_listing_and_needs_three_quarters(monkeypatch):
    import pandas as pd

    def sides(frame):
        # Evidence per row as given; line_orientation passes audit_id as unit_id.
        rows = pd.DataFrame(
            {
                "avenue": frame.s.to_numpy(),
                "wide street": False,
                "side street": False,
                "none": frame.r.to_numpy(),
            },
            index=frame.index,
        )
        return rows.groupby(frame.unit_id.to_numpy()).transform("any")

    monkeypatch.setattr(features, "unit_sides", sides)
    url = "https://streeteasy.com/building/b/{}".format
    labels = ["1j", "1j", "2j", "2j", "3j", "4j", "9j"]
    frame = pd.DataFrame(
        {
            "audit_id": [f"a{i}" for i in range(7)],
            "unit_id": [f"u{x}" for x in labels],
            "building": ["b"] * 7,
            "canonical_unit_url": [url(x) for x in labels],
            "price_at": pd.to_datetime(
                [
                    "2019-01-01",  # 1J, no evidence yet
                    "2022-01-01",  # 1J shows the rear only now
                    "2020-01-01",  # 2J lists between: must not see 1J's 2022 rear
                    "2023-01-01",  # 2J again: sees 1J rear
                    "2023-06-01",  # 3J faces the street
                    "2024-01-01",  # 4J: 1 rear, 1 street -> no agreement
                    "2024-01-01",
                ],
                utc=True,
            ),
            "s": [False, False, False, False, True, False, False],
            "r": [False, True, False, False, False, False, False],
        }
    )
    got = features.line_orientation(frame).tolist()
    assert got[2] == "" and got[3] == "rear"
    assert got[5] == "" and got[6] == ""


def test_nb3_sets_read_the_three_neighbourhoods_snapshots(monkeypatch):
    for name in ("nb3-coded-v1", "nb3-prevprice-v1", "nb3-lineface-v1"):
        assert features.lot_files(name) == {
            "registry": features.NB3_REGISTRY_FILE,
            "pluto": features.NB3_PLUTO_FILE,
        }
        assert features.area_files(name) == {
            "basemap": features.NB3_BASEMAP_FILE,
            "footprints": features.NB3_FOOTPRINTS_FILE,
        }
        files = features.description_files(name)
        assert set(files) == {"descriptions", "descriptions_wv", "descriptions_gv"}
        assert features.EXTRAS_SNAPSHOTS[name] == features.NB3_EXTRAS_FILE
        for group in (features.EXTERNAL, features.BASEMAP, features.FOOTPRINTS):
            assert name in group
        for group in (features.DESCRIPTIONS, features.AS_OF_SETS):
            assert name in group
        assert name in features.LISTING_EXTRAS
    assert "nb3-prevprice-v1" in features.READS_EARLIER_RENTS
    assert features.FEATURE_SETS["nb3-prevprice-v1"].keywords["base"] == "nb3-coded-v1"
    # Sets outside the list read the first extras files.
    assert features.EXTRAS_SNAPSHOTS.get("nb-coded-v1") is None
    seen = {}

    def spy(frame, train):
        seen["extras"] = features._EXTRAS.get()
        return features.Features("x", [], [], np.zeros((len(frame), 0)), np.zeros(0))

    monkeypatch.setitem(features.FEATURE_SETS, "nb3-coded-v1", spy)
    features.build("nb3-coded-v1", pd.DataFrame({"a": [1]}), np.ones(1, dtype=bool))
    assert seen["extras"] == features.NB3_EXTRAS_FILE
    assert features._EXTRAS.get() is None


def test_greenwich_v1_adds_greenwich_village_beside_the_base(monkeypatch):
    def base(frame, train):
        return features.Features(
            "b", ["x"], ["g"], np.ones((len(frame), 1)), np.ones(1)
        )

    monkeypatch.setitem(features.FEATURE_SETS, "fake-base", base)
    frame = pd.DataFrame(
        {"neighbourhood": ["Chelsea", "West Village", "Greenwich Village"]}
    )
    out = features.greenwich_v1(frame, np.ones(3, dtype=bool), base="fake-base")
    assert out.groups[-1] == "neighbourhood"
    assert out.values[:, -1].tolist() == [0, 0, 1]


def test_nb3_v2_sets_read_lpc_and_otherwise_their_v1s_files(monkeypatch):
    for new, old in (
        ("nb3-coded-v2", "nb3-coded-v1"),
        ("nb3-prevprice-v2", "nb3-prevprice-v1"),
    ):
        assert features.LPC_SNAPSHOTS[new] == features.NB3_LPC_FILE
        assert features.lot_files(new) == features.lot_files(old)
        assert features.area_files(new) == features.area_files(old)
        assert features.description_files(new) == features.description_files(old)
        assert features.EXTRAS_SNAPSHOTS[new] == features.EXTRAS_SNAPSHOTS[old]
        for group in (
            features.EXTERNAL,
            features.BASEMAP,
            features.FOOTPRINTS,
            features.DESCRIPTIONS,
            features.AS_OF_SETS,
            features.LISTING_EXTRAS,
            features.PRICE_HISTORY,
            features.READS_EARLIER_RENTS,
        ):
            assert (new in group) == (old in group)
    assert features.FEATURE_SETS["nb3-prevprice-v2"].keywords["base"] == "nb3-coded-v2"
    assert "nb3-coded-v1" not in features.LPC_SNAPSHOTS
    seen = {}

    def spy(frame, train):
        seen["lpc"] = features._LPC.get()
        return features.Features("x", [], [], np.zeros((len(frame), 0)), np.zeros(0))

    monkeypatch.setitem(features.FEATURE_SETS, "nb3-coded-v2", spy)
    features.build("nb3-coded-v2", pd.DataFrame({"a": [1]}), np.ones(1, dtype=bool))
    assert seen["lpc"] == features.NB3_LPC_FILE
    assert features._LPC.get() is None


def test_nb5_coded_v2_is_nb3_coded_v2_plus_flatiron_and_gramercy_park(monkeypatch):
    frame = pd.DataFrame(
        {"neighbourhood": ["Chelsea", "Flatiron", "Gramercy Park", "West Village"]}
    )
    base = features.Features("b", ["x"], ["g"], np.zeros((4, 1)), np.ones(1))
    monkeypatch.setitem(features.FEATURE_SETS, "nb3-coded-v2", lambda f, t: base)
    out = features.FEATURE_SETS["nb5-coded-v2"](frame, np.ones(4, bool))
    assert out.names == ["x", "Flatiron", "Gramercy Park"]
    assert out.groups == ["g", "neighbourhood", "neighbourhood"]
    assert out.values[:, 1].tolist() == [0, 1, 0, 0]
    assert out.values[:, 2].tolist() == [0, 0, 1, 0]
    assert features.lot_files("nb5-coded-v2") == features.lot_files("nb4-coded-v2")
    assert features.EXTRAS_SNAPSHOTS["nb5-coded-v2"] == features.NB4_EXTRAS_FILE


def test_nb4_coded_v2_is_nb3_coded_v2_plus_flatiron_on_the_nb4_snapshots(
    monkeypatch,
):
    frame = pd.DataFrame(
        {"neighbourhood": ["Chelsea", "Greenwich Village", "Flatiron + Gramercy Park"]}
    )
    base = features.Features(
        "b", ["x"], ["g"], np.ones((3, 1)), np.ones(1, dtype=float)
    )
    seen = {}

    def spy(frame, train):
        seen["lots"] = features._LOTS.get()
        seen["lpc"] = features._LPC.get()
        return base

    monkeypatch.setitem(features.FEATURE_SETS, "nb3-coded-v2", spy)
    out = features.build("nb4-coded-v2", frame, np.ones(3, dtype=bool))
    assert out.names == ["x", "Flatiron + Gramercy Park"]
    assert out.values[:, -1].tolist() == [0, 0, 1]
    assert seen["lots"] == (features.NB4_REGISTRY_FILE, features.NB4_PLUTO_FILE)
    assert seen["lpc"] == features.NB4_LPC_FILE
    new, old = "nb4-coded-v2", "nb3-coded-v2"
    assert features.area_files(new) == {
        "basemap": features.NB4_BASEMAP_FILE,
        "footprints": features.NB4_FOOTPRINTS_FILE,
    }
    assert features.description_files(new) == features._NB4_DESCRIPTIONS
    assert features.EXTRAS_SNAPSHOTS[new] == features.NB4_EXTRAS_FILE
    for group in (
        features.EXTERNAL,
        features.BASEMAP,
        features.FOOTPRINTS,
        features.DESCRIPTIONS,
        features.AS_OF_SETS,
        features.LISTING_EXTRAS,
        features.PRICE_HISTORY,
        features.READS_EARLIER_RENTS,
    ):
        assert (new in group) == (old in group)


def test_lpc_as_of_counts_a_designation_from_its_date(tmp_path):
    registry = tmp_path / "registry.parquet"
    pd.DataFrame(
        {"building": ["a", "b", "c"], "bbl": ["1000010001", "1000010002", None]}
    ).to_parquet(registry)
    token = features._LOTS.set((str(registry), "unused"))
    lpc = tmp_path / "lpc.parquet"
    pd.DataFrame(
        {
            "bbl": ["1000010001", "1000010001", "1000010002"],
            "lm_type": [
                "Historic District",
                "Individual Landmark",
                "Historic District",
            ],
            "status": ["DESIGNATED"] * 3,
            "desdate": ["12/17/2013", "6/22/2010", "4/29/1969"],
        }
    ).to_parquet(lpc)
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b", "c"],
            "price_at": [
                "2012-05-01T00:00:00Z",
                "2014-01-02T00:00:00Z",
                "2011-01-01T00:00:00Z",
                "2020-01-01T00:00:00Z",
            ],
        }
    )
    try:
        landmark, district = features.lpc_as_of(frame, str(lpc))
    finally:
        features._LOTS.reset(token)
    assert landmark.tolist() == [True, True, False, False]
    assert district.tolist() == [False, True, True, False]


def test_nb4_snapshots_keep_nb3s_rows_and_add_flatiron_gramercys():
    """The nb4 registry, MapPLUTO and footprints hold nb3's rows unchanged plus
    Flatiron + Gramercy Park's; the description sources add its evidence file."""
    pairs = (
        (features.NB3_REGISTRY_FILE, features.NB4_REGISTRY_FILE, "building"),
        (features.NB3_PLUTO_FILE, features.NB4_PLUTO_FILE, "bbl"),
        (features.NB3_FOOTPRINTS_FILE, features.NB4_FOOTPRINTS_FILE, "bin"),
    )
    if not all(Path(p).exists() for old, new, _ in pairs for p in (old, new)):
        pytest.skip("external snapshots not on this machine")
    for old, new, key in pairs:
        o, n = pd.read_parquet(old), pd.read_parquet(new)
        assert len(n) > len(o) and not n[key].duplicated().any()
        kept = n[n[key].isin(o[key])].sort_values(key).reset_index(drop=True)
        o = o.sort_values(key).reset_index(drop=True)
        pd.testing.assert_frame_equal(kept[o.columns], o)
    assert set(features._NB4_DESCRIPTIONS) == set(features._NB3_DESCRIPTIONS) | {
        "descriptions_fgp"
    }


def test_nb5_retests_are_the_nb3_sets_on_the_five_neighbourhoods():
    pairs = {
        "nb5-lines-v1": "nb3-lines-v1",
        "nb5-loc-v1": "nb3-loc-v1",
        "nb5-walkup-v1": "nb3-walkup-v1",
        "nb5-parks-v1": "nb3-parks-v1",
        "nb5-water-v1": "nb3-water-v1",
        "nb5-noise-v1": "nb3-noise-v1",
    }
    for new, old in pairs.items():
        new_set, old_set = features.FEATURE_SETS[new], features.FEATURE_SETS[old]
        assert new_set.func is old_set.func
        base = old_set.keywords["base"].replace("nb3-coded-v2", "nb5-coded-v2")
        assert new_set.keywords["base"] == base.replace("nb3-", "nb5-")
        assert features.lot_files(new) == features.lot_files("nb5-coded-v2")
        assert features.area_files(new) == features.area_files("nb5-coded-v2")
    assert "nb5-lines-v1" in features.TRANSIT
    assert features.NOISE_FILES["nb5-noise-v1"] == features.NB4_NOISE_FILE
    assert features.FEATURE_SETS["nb5-noise-v1"].keywords["noise_file"] == (
        features.NB4_NOISE_FILE
    )


def test_nb5_parks_sets_read_manhattans_parks(monkeypatch):
    assert {"nb5-parks-v1", "nb5-water-v1"} <= features.PARKS
    seen = {}
    for name in ("nb3-water-v1", "nb5-water-v1", "nb5-parks-v1"):
        monkeypatch.setitem(
            features.FEATURE_SETS,
            name,
            lambda f, t, name=name: seen.setdefault(name, features.parks_file()),
        )
        features.build(name, pd.DataFrame(), np.zeros(0, bool))
    assert seen == {
        "nb3-water-v1": features.PARKS_FILE,
        "nb5-water-v1": features.NB5_PARKS_FILE,
        "nb5-parks-v1": features.NB5_PARKS_FILE,
    }
    assert features.parks_file() == features.PARKS_FILE


def test_nb5_singles_are_nb5_coded_v2_plus_one_item(monkeypatch):
    from rentfrontier import nearby

    singles = features.NB5_SINGLES
    assert len(singles) == 21
    assert {i for w, i in singles.values() if w == "attr"} == set(
        features.ATTRIBUTE_FLAGS
    )
    assert {i for w, i in singles.values() if w == "near"} == set(nearby.KINDS)
    for name, (what, item) in singles.items():
        spec = features.FEATURE_SETS[name]
        assert spec.keywords["base"] == "nb5-coded-v2"
        assert spec.keywords["id"] == name
        if what == "attr":
            assert spec.func is features.text_flags_v1
            assert spec.keywords["flags"] == {item: features.ATTRIBUTE_FLAGS[item]}
        else:
            assert spec.func is features.nearby_one_v1
            assert spec.keywords["kind"] == item
            assert name in features.PLACES
        assert features.lot_files(name) == features.lot_files("nb5-coded-v2")
        assert features.area_files(name) == features.area_files("nb5-coded-v2")
        assert features.description_files(name) == features.description_files(
            "nb5-coded-v2"
        )
        for group in (features.EXTERNAL, features.DESCRIPTIONS):
            assert (name in group) == ("nb5-coded-v2" in group)
    seen = {}
    for name in ("nb3-nearby-v1", "nb5-near-hospital-v1"):
        monkeypatch.setitem(
            features.FEATURE_SETS,
            name,
            lambda f, t, name=name: seen.setdefault(name, features.places_file()),
        )
        features.build(name, pd.DataFrame(), np.zeros(0, bool))
    assert seen == {
        "nb3-nearby-v1": features.PLACES_FILE,
        "nb5-near-hospital-v1": features.NB4_PLACES_FILE,
    }
    assert features.places_file() == features.PLACES_FILE


def test_dated_alterations_date_only_the_alteration_years(tmp_path):
    """A listing sees the alteration years of the release of the year before
    it; size fields stay today's, as do a lot missing from that release and a
    release older than the building."""
    history = pd.DataFrame(
        {
            "release": [2015, 2015, 2015, 2020, 2020, 2020],
            "bbl": ["1", "2", "3", "1", "2", "3"],
            "yearalter1": ["0", "1990", "0", "2018", "1990", "0"],
            "yearalter2": ["0", "0", "0", "0", "2019", "0"],
            "unitsres": ["10", "20", "1", "12", "20", "1"],
        }
    )
    history.to_parquet(tmp_path / "h.parquet")
    frame = pd.DataFrame(
        {
            "period": pd.to_datetime(
                ["2017-03-01", "2017-03-01", "2017-03-01", "2022-05-01"]
            )
        }
    )
    lots = pd.DataFrame(
        {
            "yearbuilt": ["1920", "1920", "2016", "1920"],
            "yearalter1": ["2018", "1990", "0", "2018"],
            "yearalter2": ["0", "2019", "0", "0"],
            "unitsres": ["12", "20", "40", "12"],
        }
    )
    bbl = np.array(["1", "2", "3", "1"])
    out = features.dated_alterations(frame, bbl, lots, str(tmp_path / "h.parquet"))
    # 2017 listings read the 2015 release: no 2018 or 2019 alteration yet.
    assert out.yearalter1.tolist() == [0, 1990, 0, 2018]
    assert out.yearalter2.tolist() == [0, 0, 0, 0]
    # Size stays today's, and lot 3's building (2016) postdates its 2015 release.
    assert out.unitsres.tolist() == lots.unitsres.tolist()
    assert "nb5-plutoasof-v2" in features.ALTERATION_DATED_SETS
    assert "nb5-plutoasof-v2" in features.NB4_SETS
