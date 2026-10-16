"""The all-scraped set on data.DATASET_ALL, every area scraped so far."""

import json
from pathlib import Path

import pandas as pd
import pytest
from rentfrontier import data, features

NAME = "all-scraped-v1"


def test_all_scraped_set_is_the_areas_builder_on_the_nb9_base():
    base = "nb9-nostuy-lots2-v1"
    groups = {
        k: v for k, v in vars(features).items() if k.isupper() and isinstance(v, set)
    }
    assert {k for k, v in groups.items() if NAME in v} == {
        k for k, v in groups.items() if base in v
    }
    keywords = features.FEATURE_SETS[NAME].keywords
    assert keywords["base"] == base
    assert "Chelsea" not in keywords["areas"]
    assert len(set(keywords["areas"])) == len(keywords["areas"])
    for areas in features.API_AREAS.values():
        assert set(areas) - {"Chelsea"} <= set(keywords["areas"])
    sources = features.description_files(NAME)
    assert features.description_files("nb9-nostuy-api-v1").items() <= sources.items()
    assert data.DATA_RULES["latest-ask-v6"].keywords == {"path": data.LATEST_ASK_V6}
    assert data.RULE_SOURCES["latest-ask-v6"] == data.LATEST_ASK_V6


def test_all_scraped_snapshots_exist_and_keep_nb9s_lots():
    if not data.LATEST_ASK_V6.exists():
        pytest.skip("snapshots not on this machine")
    paths = [
        *features.lot_files(NAME).values(),
        *features.AREA_SNAPSHOTS[NAME].values(),
        features.LPC_SNAPSHOTS[NAME],
        features.PLUTO_RELEASES_SNAPSHOTS[NAME],
        features.EXTRAS_SNAPSHOTS[NAME],
        *features.description_files(NAME).values(),
        data.DATASET_ALL / "complete.json",
    ]
    assert [p for p in paths if not Path(p).exists()] == []
    complete = json.loads((data.DATASET_ALL / "complete.json").read_text())
    assert complete["parts"]["nb9-api"]["path"] == str(data.DATASET_NB9_API)
    assert complete["rows"]["nb9-api"] == 355099
    total = sum(complete["rows"].values())
    assert len(pd.read_parquet(data.LATEST_ASK_V6, columns=["audit_id"])) == total
    registry = pd.read_parquet(features.lot_files(NAME)["registry"])
    assert not registry.building.duplicated().any()
    nb9 = pd.read_parquet(features.lot_files("nb9-nostuy-api-v1")["registry"])
    merged = nb9.merge(registry, on="building", suffixes=("", "_all"))
    assert len(merged) == len(nb9)
    assert (merged.bbl.fillna(-1) == merged.bbl_all.fillna(-1)).all()
