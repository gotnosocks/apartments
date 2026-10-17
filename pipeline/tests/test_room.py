import fcntl
import os
import subprocess
from pathlib import Path

ROOM = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "room"


def room(locks: Path, **env) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(ROOM)],
        env={
            **os.environ,
            "APARTMENTS_LOCKS": str(locks),
            "PIPELINE_BUILD_AVOID": "pipeline-test-no-such-unit-*",
            **env,
        },
        capture_output=True,
        text=True,
    )


def test_room(tmp_path):
    """`ops/pipeline/room` lets the build start with the GPU lock free and memory to spare, and
    gives the reason to wait while a job holds the GPU lock or memory runs short."""
    free = room(tmp_path, PIPELINE_BUILD_GIB="0")
    assert free.returncode == 0, free.stdout + free.stderr
    assert free.stdout.endswith("MiB available\n")

    with open(tmp_path / "gpu.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        held = room(tmp_path, PIPELINE_BUILD_GIB="0")
    assert held.returncode == 1
    assert held.stdout == "gpu: a GPU job holds the GPU lock\n"
    # The check let go of the lock, so another job can take it.
    with open(tmp_path / "gpu.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    short = room(tmp_path, PIPELINE_BUILD_GIB="100000")
    assert short.returncode == 1
    assert short.stdout.startswith("memory: ")
    assert short.stdout.endswith("under 100000 GiB\n")
