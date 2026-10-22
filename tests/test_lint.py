import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _has_base() -> bool:
    result = subprocess.run(
        ["git", "-C", ROOT, "merge-base", "HEAD", "origin/master"],
        capture_output=True,
    )
    return result.returncode == 0


@pytest.mark.skipif(shutil.which("uvx") is None, reason="uvx not installed")
@pytest.mark.skipif(not _has_base(), reason="no merge base with origin/master")
def test_changed_python_passes_lint():
    # Only the branch's changed files, so older code that predates the lint
    # rules (docs/coding-standards.md) doesn't fail an unrelated branch.
    result = subprocess.run(
        [ROOT / "ops/lint", "--changed"], capture_output=True, text=True
    )
    assert result.returncode == 0, (
        "Run ops/lint --fix on these files, or fix them by hand:\n"
        + result.stdout
        + result.stderr
    )
