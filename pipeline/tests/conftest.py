import os
from pathlib import Path

import pytest

# SQLMesh forks workers to load models. In a test process with DuckDB connections open from
# earlier tests, a fork can deadlock, so the tests load models in the main process.
os.environ["MAX_FORK_WORKERS"] = "1"

PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "tests" / "fixture"


@pytest.fixture(scope="session", autouse=True)
def city(tmp_path_factory):
    """Point the project at the fixture's city archive, with a cache for the whole session."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PIPELINE_CITY", str(FIXTURE / "city"))
        patch.setenv("PIPELINE_CITY_CACHE", str(tmp_path_factory.mktemp("city-cache")))
        yield


@pytest.fixture(scope="session")
def render_context(city, tmp_path_factory):
    """A context on the fixture export and an empty ledger, for tests that only render models
    or read their definitions. No plan runs on its state, so it renders the models' own names
    rather than the tables of a build. Each worker process loads it once."""
    from sqlmesh import Context

    folder = tmp_path_factory.mktemp("render")
    (folder / "ledger").mkdir()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PIPELINE_EXPORT", str(FIXTURE / "export"))
        patch.setenv("PIPELINE_STATE", str(folder / "state"))
        patch.setenv("PIPELINE_LEDGER", str(folder / "ledger"))
        patch.setenv("PIPELINE_MEMORY", "1GB")
        return Context(paths=str(PROJECT))


@pytest.fixture(scope="session", autouse=True)
def optimized_queries(tmp_path_factory):
    """Keep SQLMesh's cache of optimized model queries in one folder for every context the
    worker process loads, rather than in each test's state. SQLMesh names an entry by a hash of
    the model's query, macros and Python values and of its parents' columns, so a context finds
    the entries of an earlier context only for models with the same text and inputs."""
    from sqlmesh.core.model.cache import OptimizedQueryCache

    shared = tmp_path_factory.mktemp("optimized-queries")
    init = OptimizedQueryCache.__init__

    def init_shared(self, path):
        init(self, shared)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(OptimizedQueryCache, "__init__", init_shared)
        yield


@pytest.fixture(scope="session", autouse=True)
def distributions():
    """Read the venv's packages once per worker process. SQLMesh lists them on each plan to
    record the versions of the packages the Python models import."""
    import functools
    from importlib import metadata

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            metadata,
            "packages_distributions",
            functools.cache(metadata.packages_distributions),
        )
        yield
