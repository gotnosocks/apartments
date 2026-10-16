import os
from pathlib import Path

import pytest

# SQLMesh forks workers to load models. In a test process with DuckDB connections open from
# earlier tests, a fork can deadlock, so the tests load models in the main process.
os.environ["MAX_FORK_WORKERS"] = "1"


@pytest.fixture(scope="session", autouse=True)
def city(tmp_path_factory):
    """Point the project at the fixture's city archive, with a cache for the whole session."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PIPELINE_CITY", str(Path(__file__).parent / "fixture" / "city"))
        patch.setenv("PIPELINE_CITY_CACHE", str(tmp_path_factory.mktemp("city-cache")))
        yield
