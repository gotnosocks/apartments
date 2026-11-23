import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest import mock

OPS = Path(__file__).resolve().parents[1] / "ops" / "modal"


def load_app():
    # app.py builds its Modal image and functions at import; a stub stands in for modal.
    with mock.patch.dict(sys.modules, {"modal": mock.MagicMock()}):
        spec = importlib.util.spec_from_file_location("modal_ops_app", OPS / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def test_the_memory_peak_falls_back_to_the_largest_child_without_memory_peak():
    app = load_app()
    # A child that holds about 200 MB before it exits.
    subprocess.run(
        [
            sys.executable,
            "-c",
            "b = bytearray(200 * 2**20); b[::4096] = b'x' * len(b[::4096])",
        ],
        check=True,
    )
    with mock.patch.object(app.Path, "read_text", side_effect=OSError):
        peak = app._memory_peak()
    assert peak is not None and peak >= 200 * 2**20
