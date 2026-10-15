import collections
import json

import numpy as np
import pandas as pd
import pytest
from pathlib import Path

from rentfrontier import data, features


def test_areas_v1_swaps_the_base_neighbourhoods_for_areas_and_drops_constants(
    monkeypatch,
):
    frame = pd.DataFrame(
        {"neighbourhood": ["A", "B", "C", "A"], "x": [1.0, 2.0, 3.0, 4.0]}
    )

    def base(frame, train):
        b = features._Builder(frame)
        b.add("size", "x", frame.x)
        b.add("street", "wide street", np.zeros(len(frame)))
        b.add("neighbourhood", "West Village", np.zeros(len(frame)), 0.5)
        return b.build("base")

    monkeypatch.setitem(features.FEATURE_SETS, "test-base", base)
    out = features.areas_v1(frame, None, id="t", base="test-base", areas=("B", "C"))
    assert out.names == ["x", "B", "C"]
    assert out.groups == ["size", "neighbourhood", "neighbourhood"]
    np.testing.assert_array_equal(
        out.values, [[1, 0, 0], [2, 1, 0], [3, 0, 1], [4, 0, 0]]
    )
    assert len(out.prior_scale) == 3


def test_api_sets_read_the_api_snapshots_in_the_nb9_groups():
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    base = "nb9-nostuy-lots2-v1"
    for region in features.API_AREAS:
        name = f"api-{region}-v1"
        assert region in data.DATASETS_API
        files = features.API_MANHATTAN_FILES
        assert features.lot_files(name) == {
            "registry": files["registry"],
            "pluto": files["pluto"],
        }
        assert features.AREA_SNAPSHOTS[name] == {
            "basemap": files["basemap"],
            "footprints": files["footprints"],
        }
        assert features.LPC_SNAPSHOTS[name] == files["lpc"]
        assert features.PLUTO_RELEASES_SNAPSHOTS[name] == files["plutoreleases"]
        assert features.EXTRAS_SNAPSHOTS[name] == features.API_EXTRAS_FILE
        assert {k for k, v in groups.items() if name in v} == {
            k for k, v in groups.items() if base in v
        }
        assert features.FEATURE_SETS[name].keywords["base"] == base


def test_latest_ask_api_rule_reads_its_file():
    assert data.RULE_SOURCES["latest-ask-api-v1"] == data.LATEST_ASK_API


@pytest.mark.parametrize("region", sorted(features.API_AREAS))
def test_api_areas_are_the_datasets_areas_largest_first(region):
    path = data.DATASETS_API[region] / "observations.jsonl"
    if not path.exists():
        pytest.skip("API datasets not on this machine")
    with open(path) as f:
        counts = collections.Counter(json.loads(line)["neighbourhood"] for line in f)
    areas = features.API_AREAS[region]
    assert set(areas) == set(counts)
    assert counts[areas[0]] == max(counts.values())


@pytest.mark.parametrize("region", sorted(features.API_AREAS))
def test_api_snapshots_exist(region):
    name = f"api-{region}-v1"
    paths = [
        *features.lot_files(name).values(),
        *features.AREA_SNAPSHOTS[name].values(),
        features.LPC_SNAPSHOTS[name],
        features.PLUTO_RELEASES_SNAPSHOTS[name],
        features.EXTRAS_SNAPSHOTS[name],
        *features.description_files(name).values(),
        data.DATASETS_API[region] / "complete.json",
        data.LATEST_ASK_API,
    ]
    if not data.LATEST_ASK_API.exists():
        pytest.skip("API snapshots not on this machine")
    assert [p for p in paths if not Path(p).exists()] == []
