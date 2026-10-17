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
    # Areas fetched the same listing at different times; the union keeps one row each.
    extras = pd.read_parquet(features.EXTRAS_SNAPSHOTS[NAME], columns=["listing_id"])
    assert not extras.listing_id.duplicated().any()


def test_latest_ask_v7_reads_the_page_price_of_the_typo_asks():
    if not data.LATEST_ASK_V7.exists():
        pytest.skip("latest asks not on this machine")
    v6 = pd.read_parquet(data.LATEST_ASK_V6).set_index("audit_id").latest_ask
    v7 = pd.read_parquet(data.LATEST_ASK_V7).set_index("audit_id").latest_ask
    assert v7.index.equals(v6.index)
    changed = v7[v7 != v6]
    assert len(changed) == 12
    ratio = v6[changed.index] / changed
    assert ratio.between(9, 11).all()
    helena = "da55dfdade398b9453ede1bb64bff13990c7f4c4ac5689ec49502710d31f3d51"
    assert (v6[helena], v7[helena]) == (37380, 3738)
    assert data.DATA_RULES["latest-ask-v7"].keywords == {"path": data.LATEST_ASK_V7}
    assert data.RULE_SOURCES["latest-ask-v7"] == data.LATEST_ASK_V7


def test_latest_ask_v8_corrects_five_backed_typos():
    if not data.LATEST_ASK_V8.exists():
        pytest.skip("latest asks not on this machine")
    v7 = pd.read_parquet(data.LATEST_ASK_V7).set_index("audit_id").latest_ask
    v8 = pd.read_parquet(data.LATEST_ASK_V8).set_index("audit_id").latest_ask
    assert v8.index.equals(v7.index)
    changed = v8[v8 != v7]
    assert len(changed) == 5
    assert (v7[changed.index] / changed).between(9, 11).all()
    quote = "2acab9d140df746900cbce615cffcc23d4e90bcf7cdfa27b0e80dbb8a9b6cb59"
    assert (v7[quote], v8[quote]) == (21545, 2150)
    assert data.DATA_RULES["latest-ask-v8"].keywords == {"path": data.LATEST_ASK_V8}
    assert data.RULE_SOURCES["latest-ask-v8"] == data.LATEST_ASK_V8
