"""fit-pricing runs locally by default; --executor modal must reproduce the local runner Namespace."""

import sys
from pathlib import Path
from types import ModuleType

import pytest
from typer.testing import CliRunner

import models
from apartments.cli import app
from apartments.remote_fit_pricing import IGNORED_BY_RUNNER


@pytest.fixture
def routes(monkeypatch):
    """Capture local runner Namespaces and Modal submissions; nothing samples or uploads."""
    from models import bayesian_disk_experiment as disk
    from models import bayesian_floor_spline_experiment as spline

    seen = {"local": [], "modal": []}
    capture = lambda args: seen["local"].append(args) or {"status": "synthetic"}
    monkeypatch.setattr(spline, "run", capture)
    monkeypatch.setattr(disk, "run", capture)
    fake = ModuleType("models.modal_remote_fit")
    fake.main = lambda argv: seen["modal"].append(list(argv))
    monkeypatch.setitem(sys.modules, "models.modal_remote_fit", fake)
    monkeypatch.setattr(models, "modal_remote_fit", fake, raising=False)
    return seen


def invoke(*args):
    return CliRunner().invoke(app, ["fit-pricing", "source", "posterior", *args])


FLOORS = {
    "spline": [
        "--draws",
        "300",
        "--seed",
        "7",
        "--target-accept",
        "0.9",
        "--maxdepth",
        "8",
    ],
    "increments": [
        "--floor-increments",
        "--tune",
        "150",
        "--floor-increment-prior-scale",
        "0.2",
    ],
    "linear": ["--linear-floor", "--chains", "3", "--adaptation", "low_rank"],
}


@pytest.mark.parametrize("floor", FLOORS)
def test_modal_argv_parses_to_the_local_runner_namespace(routes, floor):
    from models import bayesian_disk_experiment as disk
    from models import bayesian_floor_spline_experiment as spline

    local = invoke(*FLOORS[floor])
    remote = invoke(*FLOORS[floor], "--executor", "modal")
    assert local.exit_code == 0 and remote.exit_code == 0, local.output + remote.output
    [expected], [argv] = routes["local"], routes["modal"]
    runner_args = argv[argv.index("--") + 1 :]
    assert argv[argv.index("--runner") + 1] == (
        "models.bayesian_floor_spline_experiment"
        if floor == "spline"
        else "models.bayesian_disk_experiment"
    )
    # The Modal wrapper supplies --dataset (resolved) and a scratch --output itself.
    parser = (spline if floor == "spline" else disk).argument_parser()
    dataset = argv[argv.index("--dataset") + 1]
    parsed = vars(
        parser.parse_args(["--dataset", dataset, "--output", "scratch", *runner_args])
    )
    local_values = vars(expected)
    assert Path(parsed.pop("dataset")) == Path(local_values["dataset"]).resolve()
    parsed.pop("output")
    for key, value in parsed.items():
        assert local_values.get(key) == value, key
    assert (
        set(local_values) - set(parsed) - {"dataset", "output"}
        <= IGNORED_BY_RUNNER[floor]
    )


def test_local_default_never_imports_modal(monkeypatch):
    from models import bayesian_floor_spline_experiment as spline

    for name in ("modal", "models.modal_remote_fit"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.delattr(models, "modal_remote_fit", raising=False)
    monkeypatch.setattr(spline, "run", lambda args: {"status": "synthetic"})
    result = invoke()
    assert result.exit_code == 0, result.output
    assert "modal" not in sys.modules and "models.modal_remote_fit" not in sys.modules


def test_modal_options_and_unsupported_combinations_are_refused(routes):
    assert "require --executor modal" in invoke("--modal-cpu", "8").output
    assert "require --executor modal" in invoke("--modal-full").output
    refused = invoke("--executor", "modal", "--linear-floor", "--execution", "memory")
    assert refused.exit_code == 1 and "only --execution disk" in refused.output
    assert "executor must be" in invoke("--executor", "cloud").output
    assert routes == {"local": [], "modal": []}


def test_modal_options_pass_through(routes):
    result = invoke(
        "--executor",
        "modal",
        "--modal-cpu",
        "8",
        "--modal-memory",
        "32768",
        "--modal-full",
        "--modal-detach",
    )
    assert result.exit_code == 0, result.output
    [argv] = routes["modal"]
    head = argv[: argv.index("--")]
    assert (
        head[head.index("--cpu") + 1] == "8.0"
        and head[head.index("--memory") + 1] == "32768"
    )
    assert "--full" in head and "--detach" in head and "--timeout" in head


def test_real_modal_parser_accepts_the_submitted_argv(routes):
    """Parse only: the real CLI must accept what fit-pricing builds (no Modal calls)."""
    pytest.importorskip("modal")
    assert invoke("--executor", "modal").exit_code == 0
    [argv] = routes["modal"]
    sys.modules.pop("models.modal_remote_fit")
    delattr(models, "modal_remote_fit")
    from models import modal_remote_fit

    args = modal_remote_fit.argument_parser().parse_args(argv)
    assert (
        args.command == "run"
        and args.runner == "models.bayesian_floor_spline_experiment"
    )
    assert args.runner_args[0] == "--" and "--floor-prior-scale" in args.runner_args
