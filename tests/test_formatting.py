import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("uvx") is None, reason="uvx not installed")
def test_python_is_ruff_formatted():
    result = subprocess.run(
        [ROOT / "ops/fmt", "--check"], capture_output=True, text=True
    )
    assert result.returncode == 0, (
        "Run ops/fmt to format these files:\n" + result.stdout + result.stderr
    )
