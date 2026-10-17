import fcntl
import os
import subprocess
from pathlib import Path

BUILD_LATEST = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "build-latest"


def room(tmp_path: Path, *args: str, **env) -> subprocess.CompletedProcess:
    """`build-latest --room` with the locks in TMP_PATH and a made-up `systemctl` first on the
    PATH, which prints SYSTEMCTL_OUT, exits with SYSTEMCTL_STATUS and saves its arguments."""
    return subprocess.run(
        [str(BUILD_LATEST), "--room", *args],
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
            "APARTMENTS_LOCKS": str(tmp_path / "locks"),
            "SYSTEMCTL_ARGS": str(tmp_path / "systemctl-args"),
            "PIPELINE_BUILD_GIB": "0",
            **env,
        },
        capture_output=True,
        text=True,
    )


def test_room(tmp_path):
    """`build-latest --room` lets the build start with the GPU lock free, no unit to avoid and
    memory to spare, and gives the reason to wait otherwise."""
    (tmp_path / "bin").mkdir()
    systemctl = tmp_path / "bin" / "systemctl"
    systemctl.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" >"$SYSTEMCTL_ARGS"\n'
        'printf "%s" "$SYSTEMCTL_OUT"\nexit "${SYSTEMCTL_STATUS:-0}"\n'
    )
    systemctl.chmod(0o755)
    # As on thelio, the GPU lock links to heavy.lock.
    (tmp_path / "locks").mkdir()
    (tmp_path / "locks" / "gpu.lock").symlink_to("heavy.lock")

    free = room(tmp_path)
    assert free.returncode == 0, free.stdout + free.stderr
    assert free.stdout.endswith("MiB available\n")
    args = (tmp_path / "systemctl-args").read_text().split("\n")
    assert args[-5:] == ["site-build-*", "frontier-publish-*", "di-*", "bd4-*", ""]

    with open(tmp_path / "locks" / "heavy.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        held = room(tmp_path)
        ours = room(tmp_path, "held")
    assert held.returncode == 1
    assert held.stdout == "gpu: a GPU job holds the GPU lock\n"
    assert ours.returncode == 0, ours.stdout + ours.stderr
    # The check let go of the lock, so another job can take it.
    with open(tmp_path / "locks" / "gpu.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    unit = "site-build-nb9.service loaded active running Site build\n"
    busy = room(tmp_path, SYSTEMCTL_OUT=unit)
    assert busy.returncode == 1
    assert busy.stdout == "units: site-build-nb9.service active\n"
    broken = room(tmp_path, SYSTEMCTL_STATUS="1")
    assert broken.returncode == 1
    assert broken.stdout == "units: systemctl --user list-units failed\n"
    # With no pattern, the check leaves systemctl alone.
    for avoid in ("", " \t"):
        bare = room(tmp_path, PIPELINE_BUILD_AVOID=avoid, SYSTEMCTL_STATUS="1")
        assert bare.returncode == 0, bare.stdout + bare.stderr

    short = room(tmp_path, PIPELINE_BUILD_GIB="100000.5")
    assert short.returncode == 1
    assert short.stdout.startswith("memory: ")
    assert short.stdout.endswith("under 100000.5 GiB\n")
    wrong = room(tmp_path, PIPELINE_BUILD_GIB="5G")
    assert wrong.returncode == 2
    assert "is not a number" in wrong.stderr
