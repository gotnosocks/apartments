import importlib.util
import json
from pathlib import Path

import pytest

PIPELINE = Path(__file__).resolve().parents[2] / "ops" / "pipeline"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of test_pipeline.py load the same way.
helpers = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py"))
plant = load("plant", PIPELINE / "plant.py")


@pytest.fixture
def build(monkeypatch, tmp_path):
    """`build.build` from ops/pipeline in this process, as `plant.run` calls its build, with an
    empty corrections ledger."""
    (tmp_path / "ledger").mkdir()
    monkeypatch.setenv("PIPELINE_EXPORT", "")
    monkeypatch.setenv("PIPELINE_STATE", "")
    monkeypatch.setenv("PIPELINE_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setenv("PIPELINE_MEMORY", "1GB")
    build = load("build", PIPELINE / "build.py").build
    return lambda export, folder: build(export, folder / "state", folder / "out")


def test_planted_errors(tmp_path, build):
    """Two ads of each kind, planted in the fixture export. The planted copy passes the
    config's checks of the export, and the build drops or corrects each error with a check of
    its own. A tenfold ask and a bedroom count changed in every record of an ad pass into the
    rows."""
    export = helpers.copy_export(tmp_path)
    report = plant.run(export, tmp_path / "work", per_kind=2, build=build)
    outcomes = {kind: counts["outcomes"] for kind, counts in report["kinds"].items()}
    assert outcomes == {
        "ask_x10_latest": {"kept, clean value": 2},
        "ask_div10_latest": {"kept, clean value": 2},
        "beds_flip_latest": {
            "dropped: conflicting_layout_within_advertisement, invalid_or_missing_layout": 2
        },
        "future_active": {"dropped: future_own_active_event": 2},
        "ask_x10_all": {"kept, planted value": 2},
        "ask_x100_all": {"dropped: invalid_or_extreme_initial_ask": 2},
        "beds_flip_all": {"kept, planted value": 2},
    }
    steps = {
        kind: report["kinds"][kind].get("steps") for kind in outcomes if "ask" in kind
    }
    # A later answer's price change passes `ads.kept_changes`, and `analysis.latest_ask` takes
    # the first ask, the one nearer the building's median.
    assert steps == {
        "ask_x10_latest": {"first, nearer building": 2},
        "ask_div10_latest": {"first, nearer building": 2},
        "ask_x10_all": {"latest": 2},
        "ask_x100_all": None,
    }
    key = json.loads((tmp_path / "work" / "planted" / "key.json").read_text())
    assert len(key) == 14
    assert report == json.loads((tmp_path / "work" / "report.json").read_text())
