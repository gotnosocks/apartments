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
