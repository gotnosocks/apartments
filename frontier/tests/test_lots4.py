"""all-scraped-lots4-v1: the all-areas set on a registry with the reviewed lot overrides."""

import json
from pathlib import Path

import pandas as pd
import pytest
from rentfrontier import data, features

NAME, BASE = "all-scraped-lots4-v1", "all-scraped-v1"
OVERRIDES = [
    data.REPO / "config" / "reviews" / f
    for f in (
        "registry-overrides-20261016-lots.json",
        "registry-overrides-20261017-emptylots.json",
    )
]


def test_lots4_is_the_all_areas_set_with_new_lot_files():
    new, old = features.FEATURE_SETS[NAME], features.FEATURE_SETS[BASE]
    assert new.func is old.func
    assert new.keywords == old.keywords | {"id": NAME}
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    assert {k for k, v in groups.items() if NAME in v} == {
        k for k, v in groups.items() if BASE in v
    }
    for table in (
        features.AREA_SNAPSHOTS,
        features.EXTRAS_SNAPSHOTS,
        features.DESCRIPTION_SOURCES,
    ):
        assert table[NAME] == table[BASE]
    for table in (
        features.LOT_SNAPSHOTS,
        features.LPC_SNAPSHOTS,
        features.PLUTO_RELEASES_SNAPSHOTS,
    ):
        assert table[NAME] != table[BASE]


def test_lots4_registry_moves_only_the_overridden_buildings():
    path = Path(features.lot_files(NAME)["registry"])
    if not path.exists():
        pytest.skip("snapshots not on this machine")
    overrides = {
        o["building"]: o
        for f in OVERRIDES
        for o in json.loads(f.read_text())["overrides"]
    }
    new = pd.read_parquet(path).set_index("building")
    old = pd.read_parquet(features.lot_files(BASE)["registry"]).set_index("building")
    assert new.index.sort_values().equals(old.index.sort_values())
    old = old.loc[new.index]
    moved = new.index[(new.bbl != old.bbl) | (new.bin != old.bin)]
    assert set(moved) <= set(overrides)
    for slug, o in overrides.items():
        assert (new.bbl[slug], new.bin[slug]) == (o["bbl"], o["bin"])
        assert new.method[slug] == "override"
        assert (new.latitude[slug], new.longitude[slug]) == (
            old.latitude[slug],
            old.longitude[slug],
        )
    pluto = pd.read_parquet(features.lot_files(NAME)["pluto"], columns=["bbl"])
    assert {o["bbl"] for o in overrides.values()} <= set(pluto.bbl)
    releases = pd.read_parquet(
        features.PLUTO_RELEASES_SNAPSHOTS[NAME], columns=["release", "bbl"]
    )
    assert not releases.duplicated().any()
    assert {o["bbl"] for o in overrides.values()} <= set(releases.bbl)
