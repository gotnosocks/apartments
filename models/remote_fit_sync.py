"""Content-addressed transfer of fit inputs to a scratch worker and verified return of outputs.

The local checkout is authoritative. Inputs travel as immutable SHA-256 blobs, so a
refit uploads only files whose bytes changed since any earlier run. The worker rebuilds
the code tree and the dataset at its original absolute path (fit protocols record that
path), runs an unchanged fit runner in scratch space and copies back only selected
products. Downloads land in ``<destination>.partial`` and are renamed only after every
file matches both the worker's inventory and each bundle's own ``complete.json``.

Only the standard library is imported so the same file runs locally and on the worker.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

REQUEST_VERSION = "remote-fit-request-v1"
RESULT_VERSION = "remote-fit-result-v1"
CODE_ROOT = "/work/repo"
CODE_PATHS = ("src", "models", "config", "pyproject.toml", "uv.lock")
# Offline analysis needs the complete fit/protocol bundles; raw Zarr trace and the
# report cache are large and are never opened by the local readers.
RETURNED = ("fit", "protocol", "reporting-protocol", "progress.json")
AUXILIARY = ("trace", "report-cache")
CHUNK = 8 * 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")


def safe_id(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("IDs may contain letters, digits, dash and underscore only")
    return value


def new_run_id(label=""):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return safe_id(f"{stamp}-{label}" if label else stamp)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            value.update(block)
    return value.hexdigest()


def copy_hashed(chunks, target):
    """Write an iterable of byte chunks to ``target``; return (sha256, bytes)."""
    value, size = hashlib.sha256(), 0
    with Path(target).open("wb") as stream:
        for block in chunks:
            value.update(block)
            size += len(block)
            stream.write(block)
    return value.hexdigest(), size


def file_chunks(path):
    with Path(path).open("rb") as stream:
        yield from iter(lambda: stream.read(CHUNK), b"")


def relative_posix(value):
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(p in ("", ".", "..") for p in path.parts)
    ):
        raise ValueError(f"Unsafe relative path: {value}")
    return str(path)


def tree_files(root):
    """Regular files below ``root``; symlinks fail closed so no outside bytes are sent."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Input must be a real directory: {root}")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlinked input is not transferred: {path}")
        if path.is_file() and path.name not in (".run.lock", ".build.lock"):
            result[relative_posix(path.relative_to(root).as_posix())] = path
    return result


def code_files(repo):
    """Tracked plus untracked, non-ignored source files, including uncommitted edits."""
    repo = Path(repo)
    listed = (
        subprocess.run(
            ["git", "ls-files", "-z", "-co", "--exclude-standard", "--", *CODE_PATHS],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .split("\0")
    )
    result = {}
    for name in filter(None, listed):
        path = repo / name
        if "__pycache__" in path.parts or path.suffix == ".pyc" or not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError(f"Symlinked source is not transferred: {path}")
        result[relative_posix(name)] = path
    return result


def git_state(repo):
    def run(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    return {
        "head": run("rev-parse", "HEAD"),
        "dirty_paths": [
            line[3:]
            for line in run("status", "--porcelain", "--", *CODE_PATHS).splitlines()
        ],
    }


def build_request(
    *,
    repo,
    dataset,
    runner,
    runner_args,
    run_id,
    inputs=(),
    returned=RETURNED,
    keep_auxiliary=False,
    resources=None,
    extra_code=(),
):
    """Describe every file the worker needs; returns (request, {sha256: local path}).

    ``extra_code`` maps new repo-relative names to local files, e.g. a probe that exists
    only in another checkout; it may not replace a file the code root already has.
    """
    if not re.fullmatch(r"models\.[A-Za-z0-9_]+", runner):
        raise ValueError(
            "Runner must be a module under models, e.g. models.bayesian_floor_spline_experiment"
        )
    if any(
        a in ("--dataset", "--output") or a.startswith(("--dataset=", "--output="))
        for a in runner_args
    ):
        raise ValueError("The remote wrapper supplies --dataset and --output")
    repo, dataset = Path(repo).resolve(), Path(dataset).resolve()
    code = code_files(repo)
    extra = {
        relative_posix(name): Path(path) for name, path in dict(extra_code).items()
    }
    if replaced := sorted(code.keys() & extra.keys()):
        raise ValueError(f"Extra code would replace checkout files: {replaced}")
    code.update(extra)
    if f"{runner.replace('.', '/')}.py" not in code:
        raise ValueError(f"Runner source not found: {runner}")
    files, sources = [], {}

    def add(destination, path):
        sha = digest(path)
        files.append({"path": destination, "sha256": sha, "size": path.stat().st_size})
        sources[sha] = path

    for name, path in code.items():
        add(f"{CODE_ROOT}/{name}", path)
    for root in dict.fromkeys([dataset, *(Path(p).resolve() for p in inputs)]):
        if (
            not root.is_absolute()
            or root == Path("/")
            or Path(CODE_ROOT) in (root, *root.parents)
        ):
            raise ValueError(f"Unsupported input location: {root}")
        for name, path in tree_files(root).items():
            add(f"{root.as_posix()}/{name}", path)
    destinations = [item["path"] for item in files]
    if len(destinations) != len(set(destinations)):
        raise ValueError("Two inputs map to the same worker path")
    for name in returned:
        relative_posix(name)
    request = {
        "version": REQUEST_VERSION,
        "run_id": safe_id(run_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runner": runner,
        "runner_args": list(runner_args),
        "dataset": dataset.as_posix(),
        "code_root": CODE_ROOT,
        "git": git_state(repo),
        "extra_code": sorted(extra),
        "returned": list(returned),
        "keep_auxiliary": bool(keep_auxiliary),
        "resources": resources or {},
        "files": files,
    }
    return request, sources


def missing_blobs(request, present):
    needed = {item["sha256"]: item["size"] for item in request["files"]}
    return {sha: size for sha, size in needed.items() if sha not in present}


def materialize(request, blob_root, filesystem_root="/"):
    """Rebuild every requested file from verified blobs; existing files must already match."""
    blob_root, filesystem_root = Path(blob_root), Path(filesystem_root)
    written = 0
    for item in request["files"]:
        if not SHA256.fullmatch(item["sha256"]):
            raise ValueError("Invalid blob hash in request")
        destination = PurePosixPath(item["path"])
        if not destination.is_absolute() or ".." in destination.parts:
            raise ValueError(f"Unsafe worker path: {destination}")
        target = filesystem_root / destination.relative_to("/")
        if target.exists():
            if digest(target) != item["sha256"]:
                raise ValueError(
                    f"Worker path already holds different bytes: {destination}"
                )
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".partial")
        sha, size = copy_hashed(file_chunks(blob_root / item["sha256"]), partial)
        if sha != item["sha256"] or size != item["size"]:
            partial.unlink()
            raise ValueError(f"Blob integrity failure for {destination}")
        partial.rename(target)
        written += size
    return written


def collect_outputs(output, destination, names):
    """Copy selected run products, hashing each byte once; return the inventory."""
    output, destination = Path(output), Path(destination)
    inventory = []
    for name in names:
        source = output / relative_posix(name)
        if not source.exists():
            continue
        entries = tree_files(source).items() if source.is_dir() else [("", source)]
        for relative, path in entries:
            name_out = f"{name}/{relative}" if relative else name
            target = destination / name_out
            target.parent.mkdir(parents=True, exist_ok=True)
            sha, size = copy_hashed(file_chunks(path), target)
            inventory.append({"path": name_out, "sha256": sha, "size": size})
    return inventory


def run_logged(command, *, cwd, env, log_path):
    """Run the fit runner, mirroring its output to the worker log and a file."""
    with Path(log_path).open("w") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
            log.flush()
        return process.wait()


def execute(
    request,
    *,
    blob_root,
    run_root,
    scratch,
    filesystem_root="/",
    python=None,
    commit=None,
):
    """Worker body: materialize, run the unchanged runner, persist selected products."""
    if request.get("version") != REQUEST_VERSION:
        raise ValueError("Unsupported remote fit request")
    run_root, scratch = Path(run_root), Path(scratch)
    output_root = run_root / "output"
    if output_root.exists():
        raise ValueError(
            "Remote run output already exists; outputs are never overwritten"
        )
    commit = commit or (lambda: None)
    timings = {}
    started = time.monotonic()
    written = materialize(request, blob_root, filesystem_root)
    timings["materialize_seconds"] = time.monotonic() - started

    def local(path):
        return Path(filesystem_root) / PurePosixPath(path).relative_to("/")

    fit_output = scratch / "run"
    command = [
        python or sys.executable,
        "-m",
        request["runner"],
        "--dataset",
        str(local(request["dataset"])),
        "--output",
        str(fit_output),
        *request["runner_args"],
    ]
    code = local(request["code_root"])
    # Frozen designs are reproduced bit-for-bit only with single-threaded BLAS; the
    # in-process threadpool limit alone does not suffice, so set it before startup.
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(code / "src"), str(code)]),
        "PYTHONUNBUFFERED": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    step = time.monotonic()
    returncode = run_logged(command, cwd=code, env=env, log_path=scratch / "runner.log")
    timings["runner_seconds"] = time.monotonic() - step
    # Peak resident memory of the runner and its children (Linux reports KiB); sizes --memory.
    peak_rss_mib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024

    step = time.monotonic()
    names = [*request["returned"], *(AUXILIARY if request["keep_auxiliary"] else ())]
    output_root.mkdir(parents=True)
    inventory = collect_outputs(fit_output, output_root, names)
    shutil.copyfile(scratch / "runner.log", run_root / "runner.log")
    timings["persist_seconds"] = time.monotonic() - step
    timings["worker_seconds"] = time.monotonic() - started
    result = {
        "version": RESULT_VERSION,
        "run_id": request["run_id"],
        "returncode": returncode,
        "succeeded": returncode == 0 and bool(inventory),
        "command": command[1:],
        "materialized_bytes": written,
        "timings": timings,
        "runner_peak_rss_mib": peak_rss_mib,
        "returned_bytes": sum(item["size"] for item in inventory),
        "files": inventory,
        "scratch_bytes": sum(
            p.stat().st_size for p in fit_output.rglob("*") if p.is_file()
        )
        if fit_output.exists()
        else 0,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    commit()
    return result


# Posterior draws stay remote by default; summaries answer screening and convergence
# questions. Promotion, the main page and source review need `complete` first.
OMITTED = ("fit/posterior.nc", "fit/prior.nc")
OMITTED_MARKER = "remote-omitted.json"


def download(result, read, destination, include=None, omit=()):
    """Fetch inventory files into ``destination`` via ``<destination>.partial``; resumable.

    ``read(relative_path)`` yields the bytes of ``output/<relative_path>`` on the store.
    ``include`` restricts to top-level names (default: everything returned). Files in
    ``omit`` stay remote and are listed in ``remote-omitted.json`` so bundle readers
    refuse the directory until ``complete`` fetches them.
    """
    destination = Path(destination)
    if destination.exists():
        raise ValueError(
            f"Destination exists; downloads never overwrite: {destination}"
        )
    partial = destination.with_name(destination.name + ".partial")
    partial.mkdir(parents=True, exist_ok=True)
    returned = [
        item
        for item in result["files"]
        if include is None or PurePosixPath(item["path"]).parts[0] in include
    ]
    selected = [item for item in returned if item["path"] not in omit]
    omitted = [item for item in returned if item["path"] in omit]
    stats = fetch_items(selected, read, partial)
    verify_bundles(partial, selected, returned)
    if omitted:
        (partial / OMITTED_MARKER).write_text(
            json.dumps({"run_id": result["run_id"], "files": omitted}, indent=2) + "\n"
        )
    partial.rename(destination)
    return {
        **stats,
        "files": len(selected),
        "omitted_files": len(omitted),
        "omitted_bytes": sum(item["size"] for item in omitted),
    }


def complete(destination, read):
    """Fetch the files a summary-only download left remote, verify them, drop the marker."""
    destination = Path(destination)
    marker = destination / OMITTED_MARKER
    omitted = json.loads(marker.read_text())["files"]
    stats = fetch_items(omitted, read, destination, suffix=".partial")
    marker.unlink()
    return {**stats, "files": len(omitted)}


def fetch_items(items, read, root, suffix=""):
    """Download and hash-check each item; with a suffix, write aside and rename into place."""
    fetched = reused = 0
    for item in items:
        target = root / relative_posix(item["path"])
        if (
            target.is_file()
            and target.stat().st_size == item["size"]
            and digest(target) == item["sha256"]
        ):
            reused += item["size"]
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(target.name + suffix)
        sha, size = copy_hashed(read(item["path"]), staging)
        if sha != item["sha256"] or size != item["size"]:
            staging.unlink()
            raise ValueError(
                f"Downloaded bytes differ from worker inventory: {item['path']}"
            )
        if suffix:
            staging.rename(target)
        fetched += size
    return {"downloaded_bytes": fetched, "reused_partial_bytes": reused}


def verify_bundles(root, downloaded, inventory=None):
    """Each downloaded ``complete.json`` must list only returned files with matching hashes."""
    hashes = {item["path"]: item["sha256"] for item in inventory or downloaded}
    for marker in sorted(
        item["path"]
        for item in downloaded
        if PurePosixPath(item["path"]).name == "complete.json"
    ):
        folder = PurePosixPath(marker).parent
        manifest = json.loads((Path(root) / marker).read_text())
        for name, expected in manifest.get("files", {}).items():
            path = str(folder / relative_posix(name))
            if path not in hashes:
                raise ValueError(
                    f"Bundle {folder} lists a file that was not returned: {name}"
                )
            if hashes[path] != expected:
                raise ValueError(f"Bundle {folder} hash mismatch: {name}")


VOLUME_MOUNT = "/fitwork"
WORKER_PYTHON = "/.uv/.venv/bin/python"


def modal_worker(run_id, volume_name):
    """Modal entry point; registered by ``models.modal_remote_fit`` with per-run resources."""
    import tempfile
    import modal

    volume = modal.Volume.from_name(volume_name)
    volume.reload()
    root = Path(VOLUME_MOUNT)
    run_root = root / "runs" / safe_id(run_id)
    request = json.loads((run_root / "request.json").read_text())
    if request.get("run_id") != run_id:
        raise ValueError("Remote request does not belong to this run")
    python = WORKER_PYTHON if Path(WORKER_PYTHON).exists() else sys.executable
    with tempfile.TemporaryDirectory(prefix="fit-") as scratch:
        return execute(
            request,
            blob_root=root / "blobs",
            run_root=run_root,
            scratch=Path(scratch),
            python=python,
            commit=volume.commit,
        )
