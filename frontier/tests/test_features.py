"""Feature sets: unit-consistent bedrooms (unitbeds-v1)."""

import numpy as np
import pandas as pd
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
    on_v3 = {
        n
        for n, f in features.FEATURE_SETS.items()
        if getattr(f, "func", f) in (features.facing_v3, features.facing_v4)
    }
    assert on_v3 == features.FOOTPRINTS and on_v3 <= features.BASEMAP
    monkeypatch.setattr(run.data, "sha256", lambda path: "sha")
    for name in ("unitfacing-v3", "unitfacing-v4", "unitfacing-v5"):
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
        features, "_building_sides", lambda path: seen.append(path) or path
    )
    monkeypatch.setattr(
        features, "_building_frontage", lambda path: seen.append(path) or path
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
    monkeypatch.setattr(features, "_noise_times", lambda path: times)
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
