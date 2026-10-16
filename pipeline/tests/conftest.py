import importlib.util
import os
import shutil
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixture"

# SQLMesh forks workers to load models. In a test process with DuckDB connections open from
# earlier tests, a fork can deadlock, so the tests load models in the main process.
os.environ["MAX_FORK_WORKERS"] = "1"


@pytest.fixture(scope="session", autouse=True)
def city(tmp_path_factory):
    """Point the project at the fixture's city archive, with a cache for the whole session."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PIPELINE_CITY", str(FIXTURE / "city"))
        patch.setenv("PIPELINE_CITY_CACHE", str(tmp_path_factory.mktemp("city-cache")))
        yield


def helpers():
    """The helpers of test_pipeline.py, loaded by path as pytest loads test modules."""
    path = Path(__file__).with_name("test_pipeline.py")
    spec = importlib.util.spec_from_file_location("pipeline_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def loaded(city, tmp_path_factory):
    """A context on the fixture export with an empty ledger, loaded once in each worker. Tests
    that only read the models or render them share it."""
    state = tmp_path_factory.mktemp("loaded") / "state"
    with pytest.MonkeyPatch.context() as patch:
        ctx = helpers().context(patch, state)
    yield ctx
    ctx.close()


@pytest.fixture(scope="session")
def built(city, tmp_path_factory):
    """A worker's folder with a copy of the fixture export and a state built from it.

    A model reading the export has the export's path in its fingerprint, so a state built on
    one folder serves only builds on the same folder. Each worker runs one test at a time, so
    the tests of a worker can take turns with the folder."""
    root = tmp_path_factory.mktemp("built")
    shutil.copytree(FIXTURE / "export", root / "export")
    with pytest.MonkeyPatch.context() as patch:
        ctx = helpers().context(patch, root / "state", root / "export")
        ctx.plan(auto_apply=True, no_prompts=True)
        ctx.close()
    return root


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Put the tests of a module that use `fixture_build` in a group of their own. With
    `--dist loadgroup`, pytest-xdist runs a group in one worker, and the worker builds the
    fixture's state once for them."""
    for item in items:
        if "fixture_build" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.xdist_group(f"built-{item.module.__name__}"))


@pytest.fixture
def fixture_build(built, tmp_path):
    """Copy the fixture export into the worker's folder and the state built from it into
    `tmp_path / "state"`, and return the export's folder. A plan on the two builds nothing."""
    export = built / "export"
    shutil.rmtree(export)
    shutil.copytree(FIXTURE / "export", export)
    shutil.copytree(built / "state", tmp_path / "state")
    return export
