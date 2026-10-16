"""The NB9 set on NB9 extended by the API re-read of its areas."""

import json
from pathlib import Path

import pandas as pd
import pytest
from rentfrontier import data, features

NAME = "nb9-nostuy-api-v1"


def test_nb9_api_set_is_nb9s_set_on_the_extended_snapshots():
    base = "nb9-nostuy-lots2-v1"
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    assert {k for k, v in groups.items() if NAME in v} == {
        k for k, v in groups.items() if base in v
    }
    assert features.FEATURE_SETS[NAME].func is features.FEATURE_SETS[base].func
    assert features.FEATURE_SETS[NAME].keywords == features.FEATURE_SETS[
        base
    ].keywords | {"id": NAME}
    sources = features.description_files(NAME)
    assert {
        k: v for k, v in sources.items() if not k.startswith("descriptions_api_added")
    } == features.description_files(base)
    assert data.RULE_SOURCES["latest-ask-v5"] == data.LATEST_ASK_V5


def test_nb9_api_snapshots_exist_and_cover_nb9s_lots():
    paths = [
        *features.lot_files(NAME).values(),
        *features.AREA_SNAPSHOTS[NAME].values(),
        features.LPC_SNAPSHOTS[NAME],
        features.PLUTO_RELEASES_SNAPSHOTS[NAME],
        features.EXTRAS_SNAPSHOTS[NAME],
        *features.description_files(NAME).values(),
        data.DATASET_NB9_API / "complete.json",
        data.LATEST_ASK_V5,
    ]
    if not data.LATEST_ASK_V5.exists():
        pytest.skip("snapshots not on this machine")
    assert [p for p in paths if not Path(p).exists()] == []
    complete = json.loads((data.DATASET_NB9_API / "complete.json").read_text())
    assert complete["base"]["path"] == str(data.DATASET_NB9)
    assert complete["rows"]["base"] + complete["rows"]["added"] == 355099
    registry = pd.read_parquet(features.lot_files(NAME)["registry"])
    lots2 = pd.read_parquet(features.NB9_LOTS2_REGISTRY_FILE)
    merged = lots2.merge(registry, on="building", suffixes=("", "_api"))
    assert len(merged) == len(lots2)
    assert (merged.bbl.fillna(-1) == merged.bbl_api.fillna(-1)).all()
    extras = pd.read_parquet(features.EXTRAS_SNAPSHOTS[NAME])
    assert not extras.listing_id.duplicated().any()
