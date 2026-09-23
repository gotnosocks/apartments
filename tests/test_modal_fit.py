"""Cloud guards; no scientific imports, data analysis, or Modal connections."""

import importlib.util
from pathlib import Path
import pytest

pytest.importorskip("modal")
spec = importlib.util.spec_from_file_location(
    "modal_fit", Path(__file__).parents[1] / "models/modal_fit.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "values", [(1, 100, 4), (100, 0, 4), (100, 100, 1), (100, 100, 100)]
)
def test_invalid_sampling_budget(values):
    with pytest.raises(ValueError):
        module.validate_settings(*values)


@pytest.mark.parametrize("value", ["../other", "/absolute", "", "a/b"])
def test_snapshot_path_guard(value):
    with pytest.raises(ValueError):
        module.safe_id(value)


def test_existing_output_rejected_before_remote_call(tmp_path):
    with pytest.raises(ValueError, match="never overwritten"):
        module.main(output=str(tmp_path), draws=20, tune=20, chains=2)


def test_cpu_default_submits_only_volume_identifiers(monkeypatch):
    calls = []
    monkeypatch.setattr(
        module.fit_cpu, "remote", lambda *args: calls.append(args) or {"files": []}
    )
    module.main(snapshot="chelsea-test", run_id="test-run", draws=20, tune=20, chains=2)
    assert calls == [
        ("chelsea-test", "test-run", {"draws": 20, "tune": 20, "chains": 2})
    ]


def test_optional_gpu_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        module, "run_gpu", lambda *args: calls.append(args) or {"files": []}
    )
    module.main(
        snapshot="chelsea-test", run_id="gpu-run", gpu=True, draws=20, tune=20, chains=2
    )
    assert calls[0][1] == "gpu-run"


def test_default_app_has_no_gpu_function_or_image():
    assert set(module.app._local_state.functions) == {"fit_cpu"}


def test_cpu_dispatch_does_not_initialize_gpu_app(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("CPU run must not initialize the GPU app")

    monkeypatch.setattr(module, "run_gpu", forbidden)
    monkeypatch.setattr(module.fit_cpu, "remote", lambda *args: {"files": []})
    module.main(snapshot="chelsea-test", run_id="cpu-only", draws=20, tune=20, chains=2)
