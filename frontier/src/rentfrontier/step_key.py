"""Keys for the publish steps after the summary: the rent map and the kit.

Each step hashes what it reads and names its output directory
`<run>-<key[:7]>`. The record it hashes holds

    run        the sha256 of the run's result.json and posterior.npz
    summary    the sha256 of the bundle's complete.json, which lists a sha256
               for each of the bundle's files, and of its design-parts.npz,
               which Modeling adds to bundles after the summary has run
    sources    the sha256 of each .py file in the rentfrontier package and of
               frontier/uv.lock
    options    the step's own options, such as the rent map's draws

When the directory for a key already holds the step's output, the step keeps
it and exits. A merge that leaves the frontier package alone then keeps both
outputs, where keying by commit reran both on every merge. The package goes
in whole: the steps import some modules only on some paths (design_parts
imports design and summary only when a bundle lacks its parts), and over the
hundred merges to 2026-10-18 the 14 commits touching the package and the 13
touching the modules the kit imports were nearly the same.

The all-scraped posterior.npz is 13.4 GB, so `file_sha256` keeps each large
file's sha256 under `cache/sha256/` by its real path, size and mtime, and a
file left alone is read once.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from . import data

VERSION = "step-key-v1"
CACHE = data.OUTPUT_ROOT / "cache" / "sha256"
PACKAGE = Path(__file__).resolve().parent
LOCK = PACKAGE.parents[1] / "uv.lock"


def file_sha256(path: Path, cache: Path | None = None) -> str:
    """`data.sha256(path)`, kept in `cache` by the file's real path, size and
    mtime."""
    cache = CACHE if cache is None else cache
    real = Path(path).resolve()
    stat = real.stat()
    stamp = {"path": str(real), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    name = hashlib.sha256(str(real).encode()).hexdigest()[:24] + ".json"
    try:
        found = json.loads((cache / name).read_text())
    except (OSError, ValueError):
        found = {}
    if {k: found.get(k) for k in stamp} == stamp and found.get("sha256"):
        return found["sha256"]
    digest = data.sha256(real)
    cache.mkdir(parents=True, exist_ok=True)
    tmp = cache / f".{name}.{os.getpid()}"
    tmp.write_text(json.dumps(stamp | {"sha256": digest}))
    os.replace(tmp, cache / name)
    return digest


def sources(package: Path = PACKAGE, lock: Path = LOCK) -> dict[str, str]:
    """The sha256 of each .py file under `package`, by path relative to it,
    and of the lock file when there is one."""
    found = {
        str(p.relative_to(package)): data.sha256(p)
        for p in sorted(package.rglob("*.py"))
        if "__pycache__" not in p.parts
    }
    if lock.exists():
        found[lock.name] = data.sha256(lock)
    return found


def inputs(
    step: str, run_dir: Path, summary_dir: Path | None, options: dict, cache=None
) -> dict:
    """The record `key` hashes for `step` on the run in `run_dir`."""
    summary = None
    if summary_dir is not None:
        summary = {"complete": data.sha256(summary_dir / "complete.json")}
        parts = summary_dir / "design-parts.npz"
        if parts.exists():
            summary["design_parts"] = file_sha256(parts, cache)
    return {
        "version": VERSION,
        "step": step,
        "run": {
            "result": data.sha256(run_dir / "result.json"),
            "posterior": file_sha256(run_dir / "posterior.npz", cache),
        },
        "summary": summary,
        "sources": sources(),
        "options": options,
    }


def key(record: dict) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def out_dir(root: Path, run: str, digest: str) -> Path:
    return root / f"{run}-{digest[:7]}"


def recorded(path: Path, digest: str) -> bool:
    """Whether the JSON file at `path` holds the output made for `digest`.
    A file there made for another key is refused, since the two keys share
    their first seven characters."""
    if not path.exists():
        return False
    found = json.loads(path.read_text()).get("key")
    if found != digest:
        raise SystemExit(f"{path} was made for key {found}, not {digest}")
    return True
