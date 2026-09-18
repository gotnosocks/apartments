import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "bayesian_experiments", Path(__file__).parents[1] / "models/bayesian_experiments.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def args(tmp_path):
    return SimpleNamespace(
        output=tmp_path / "experiments",
        input=tmp_path / "input.parquet",
        deadline="2099-01-01T00:00:00+00:00",
        variants=["building", "unit"],
        draws=2000,
        tune=1500,
        adaptation="low_rank",
        fit_timeout=3600,
    )


def test_controller_stops_on_failed_diagnostics(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        output = Path(command[command.index("--output") + 1])
        output.mkdir()
        (output / "diagnostics.json").write_text(json.dumps({"acceptable": False}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    options = args(tmp_path)
    m.run(options)
    assert len(calls) == 1
    assert Path(calls[0][1]).parent == options.output
    state = json.loads((options.output / "progress.json").read_text())
    assert state["status"] == "needs_attention"
    assert state["runs"][0]["status"] == "needs_diagnostics"


def test_controller_respects_deadline_without_launching(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("No fit should launch after deadline")

    monkeypatch.setattr(m.subprocess, "run", unexpected)
    options = args(tmp_path)
    options.deadline = "2000-01-01T00:00:00+00:00"
    m.run(options)
    state = json.loads((options.output / "progress.json").read_text())
    assert state["status"] == "deadline" and state["runs"] == []
