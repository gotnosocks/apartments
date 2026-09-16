"""Receive immutable archive bundles from a Modal Volume into local storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, BinaryIO

CHUNK_SIZE = 1024 * 1024
DEFAULT_PREFIX = "/migrations/thelio-20260916"
DEFAULT_ROOT = "/data1/apartments/archive"
DEFAULT_STATE = "/data1/apartments/migration"


class ReceiveError(ValueError):
    """A bundle is malformed, unsafe, or does not match its manifest."""


class TransientDownloadError(RuntimeError):
    """A bounded download retry run ended on a transport/SDK failure."""


class _WaitForPublication(Exception):
    pass


def _relative(value: Any, label: str = "path") -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReceiveError(f"{label} must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ReceiveError(f"unsafe {label}: {value!r}")
    return path


def _hash_file(path: Path, *, progress_label: str | None = None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    last_log = time.monotonic()
    with path.open("rb") as stream:
        while block := stream.read(CHUNK_SIZE):
            size += len(block)
            digest.update(block)
            now = time.monotonic()
            if progress_label and now - last_log >= 30:
                print(f"migration verify {progress_label}: {size} bytes", flush=True)
                last_log = now
    return size, digest.hexdigest()


def _manifest(stream: BinaryIO, expected_count: int) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for line_number, line in enumerate(stream, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReceiveError(f"manifest line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(item, dict):
            raise ReceiveError(f"manifest line {line_number}: expected an object")
        rel = str(_relative(item.get("path")))
        if rel in seen:
            raise ReceiveError(f"manifest line {line_number}: duplicate path {rel!r}")
        seen.add(rel)
        kind = item.get("type", "file")
        if kind == "file":
            size, sha = item.get("size"), item.get("sha256")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ReceiveError(f"manifest line {line_number}: invalid file size")
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
                raise ReceiveError(f"manifest line {line_number}: invalid SHA-256")
            item = {"path": rel, "size": size, "sha256": sha.lower()}
        elif kind == "symlink":
            target = item.get("target")
            if not isinstance(target, str) or not target or "\\" in target or target.startswith("/"):
                raise ReceiveError(f"manifest line {line_number}: unsafe symlink target")
            resolved = list(PurePosixPath(rel).parent.parts)
            for part in target.split("/"):
                if part in ("", "."):
                    continue
                if part == "..":
                    if not resolved:
                        raise ReceiveError(f"manifest line {line_number}: symlink escapes archive")
                    resolved.pop()
                else:
                    resolved.append(part)
            item = {"path": rel, "type": "symlink", "target": target}
        else:
            raise ReceiveError(f"manifest line {line_number}: unsupported type {kind!r}")
        result.append(item)
    if len(result) != expected_count:
        raise ReceiveError(f"manifest has {len(result)} entries; ready record expects {expected_count}")
    return result


def _ensure_no_symlink_parent(root: Path, rel: PurePosixPath) -> Path:
    root = root.resolve()
    target = root.joinpath(*rel.parts)
    try:
        target.parent.resolve().relative_to(root)
    except ValueError as exc:
        raise ReceiveError(f"path escapes archive root: {rel}") from exc
    current = root
    for part in rel.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ReceiveError(f"refusing to write through symlink parent: {current}")
        if current.exists() and not current.is_dir():
            raise ReceiveError(f"parent is not a directory: {current}")
    return target


def _matches(path: Path, item: dict[str, Any], *, progress_label: str | None = None) -> bool:
    if item.get("type", "file") == "symlink":
        return path.is_symlink() and os.readlink(path) == item["target"]
    if not path.is_file() or path.is_symlink():
        return False
    size, digest = _hash_file(path, progress_label=progress_label)
    return size == item["size"] and digest == item["sha256"]


class _ProgressReader:
    def __init__(self, stream: Any, label: str):
        self.stream = stream
        self.label = label
        self.bytes_read = 0
        self.last_log = time.monotonic()

    def read(self, size: int = -1) -> bytes:
        data = self.stream.read(size)
        self.bytes_read += len(data)
        now = time.monotonic()
        if now - self.last_log >= 30:
            print(f"migration unpack {self.label}: {self.bytes_read} bytes", flush=True)
            self.last_log = now
        return data


def verify_part(root: Path, records: list[dict[str, Any]], *, label: str = "part") -> None:
    for item in records:
        path = _ensure_no_symlink_parent(root, _relative(item["path"]))
        if not _matches(path, item, progress_label=f"{label} {item['path']}"):
            raise ReceiveError(f"existing destination does not match manifest: {item['path']}")


def extract_bundle(archive_path: Path, manifest_path: Path, root: Path, ready: dict[str, Any]) -> list[dict[str, Any]]:
    """Stream one compressed tar into root, checking every entry against its manifest."""
    with manifest_path.open("rb") as manifest_stream:
        records = _manifest(manifest_stream, ready["files"])
    by_path = {item["path"]: item for item in records}
    root.mkdir(parents=True, exist_ok=True)
    seen = set()
    uncompressed = 0
    import zstandard

    try:
        with archive_path.open("rb") as compressed:
            reader = zstandard.ZstdDecompressor().stream_reader(compressed)
            progress_reader = _ProgressReader(reader, archive_path.stem)
            with tarfile.open(fileobj=progress_reader, mode="r|") as tar:
                for member in tar:
                    if member.name in ("", ".") and member.isdir():
                        continue
                    rel = _relative(member.name, "tar member path")
                    name = str(rel)
                    if name in seen:
                        raise ReceiveError(f"duplicate tar entry: {name}")
                    seen.add(name)
                    item = by_path.get(name)
                    destination = _ensure_no_symlink_parent(root, rel)
                    if member.isdir():
                        if item is not None:
                            raise ReceiveError(f"directory must not appear in file manifest: {name}")
                        if destination.exists() and (destination.is_symlink() or not destination.is_dir()):
                            raise ReceiveError(f"destination conflict: {name}")
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    if item is None:
                        raise ReceiveError(f"tar entry is absent from manifest: {name}")
                    if item.get("type", "file") == "symlink":
                        if not member.issym() or member.linkname != item["target"]:
                            raise ReceiveError(f"symlink differs from manifest: {name}")
                        try:
                            (destination.parent / item["target"]).resolve(strict=False).relative_to(root.resolve())
                        except ValueError as exc:
                            raise ReceiveError(f"symlink target escapes archive: {name}") from exc
                        if destination.exists() or destination.is_symlink():
                            if not _matches(destination, item):
                                raise ReceiveError(f"refusing to overwrite existing path: {name}")
                            continue
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        os.symlink(item["target"], destination)
                        continue
                    if not member.isfile():
                        raise ReceiveError(f"unsupported tar entry type: {name}")
                    if member.size != item["size"]:
                        raise ReceiveError(f"tar size differs from manifest: {name}")
                    if destination.exists() or destination.is_symlink():
                        if not _matches(destination, item):
                            raise ReceiveError(f"refusing to overwrite existing path: {name}")
                        seen.add(name)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source = tar.extractfile(member)
                    if source is None:
                        raise ReceiveError(f"tar entry has no content: {name}")
                    partial = destination.with_name(destination.name + ".partial")
                    if partial.is_symlink():
                        raise ReceiveError(f"refusing to write through partial symlink: {partial}")
                    partial.unlink(missing_ok=True)
                    digest = hashlib.sha256()
                    size = 0
                    try:
                        with source, partial.open("xb") as output:
                            while block := source.read(CHUNK_SIZE):
                                size += len(block)
                                uncompressed += len(block)
                                digest.update(block)
                                output.write(block)
                            output.flush()
                            os.fsync(output.fileno())
                        if size != item["size"] or digest.hexdigest() != item["sha256"]:
                            raise ReceiveError(f"extracted file does not match manifest: {name}")
                        os.replace(partial, destination)
                    except BaseException:
                        partial.unlink(missing_ok=True)
                        raise
                    os.chmod(destination, member.mode & 0o777)
        if seen.intersection(by_path) != set(by_path):
            missing = sorted(set(by_path) - seen)
            raise ReceiveError(f"tar bundle omitted manifest paths: {missing[:5]}")
        # Include matching files already present from an interrupted extraction.
        uncompressed = sum(item.get("size", 0) for item in records if item.get("type", "file") == "file")
        if uncompressed != ready["uncompressed_bytes"]:
            raise ReceiveError("uncompressed byte count differs from ready record")
        verify_part(root, records)
        return records
    finally:
        if "reader" in locals():
            reader.close()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_volume(volume: Any, remote: str) -> bytes:
    return b"".join(volume.read_file(remote))


def _download(volume: Any, remote: str, target: Path, *, expected_sha256: str | None = None, retries: int = 5) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        partial = target.with_name(target.name + ".partial")
        partial.unlink(missing_ok=True)
        try:
            started = time.monotonic()
            last_log = [started]
            transferred = [0]
            progress_lock = threading.Lock()

            def progress(*, advance: int = 0, **_: Any) -> None:
                with progress_lock:
                    transferred[0] += advance
                    now = time.monotonic()
                    if now - last_log[0] >= 30:
                        print(f"migration download {target.name}: {transferred[0]} bytes", flush=True)
                        last_log[0] = now

            with partial.open("wb") as output:
                volume.read_file_into_fileobj(remote, output, progress_cb=progress)
                output.flush()
                os.fsync(output.fileno())
            if expected_sha256:
                _, actual = _hash_file(partial, progress_label=target.name)
                if actual.lower() != expected_sha256.lower():
                    raise ReceiveError(f"download checksum mismatch for {remote}")
            os.replace(partial, target)
            print(f"migration downloaded {target.name}: {target.stat().st_size} bytes", flush=True)
            return
        except ReceiveError:
            partial.unlink(missing_ok=True)
            raise
        except Exception:
            partial.unlink(missing_ok=True)
            if attempt + 1 < retries:
                time.sleep(min(2 ** attempt, 30))
    raise TransientDownloadError(f"download failed after {retries} attempts for {target.name}") from None


def _validate_ready(ready: Any) -> dict[str, Any]:
    if not isinstance(ready, dict):
        raise ReceiveError("ready record must be a JSON object")
    for key in ("bytes", "files", "uncompressed_bytes"):
        value = ready.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ReceiveError(f"ready record has invalid {key}")
    sha = ready.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha):
        raise ReceiveError("ready record has invalid sha256")
    manifest_sha = ready.get("manifest_sha256")
    if manifest_sha is not None and (
        not isinstance(manifest_sha, str)
        or len(manifest_sha) != 64
        or any(c not in "0123456789abcdefABCDEF" for c in manifest_sha)
    ):
        raise ReceiveError("ready record has invalid manifest_sha256")
    return ready


def _load_json(volume: Any, path: str) -> Any:
    try:
        return json.loads(_read_volume(volume, path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiveError(f"invalid JSON in volume file {path}: {exc}") from exc


def process_part(volume: Any, prefix: str, group: dict[str, Any], root: Path, state: Path) -> list[dict[str, Any]]:
    part_id = group["id"]
    stem = f"{part_id:05d}"
    ready_remote = f"{prefix}/packs/{stem}.ready.json"
    ready = _validate_ready(_load_json(volume, ready_remote))
    if "bytes" in group and group["bytes"] != ready["uncompressed_bytes"]:
        raise ReceiveError(f"plan uncompressed byte count disagrees for bundle {stem}")
    if "files" in group and group["files"] != ready["files"]:
        raise ReceiveError(f"plan file count disagrees for bundle {stem}")
    local = state / "packs"
    archive_path, manifest_path = local / f"{stem}.tar.zst", local / f"{stem}.manifest.jsonl"
    manifest_sha = ready.get("manifest_sha256")
    if not manifest_sha or not _cached_file_matches(manifest_path, sha256=manifest_sha):
        _download(volume, f"{prefix}/packs/{stem}.manifest.jsonl", manifest_path, expected_sha256=manifest_sha)
    if not _cached_file_matches(archive_path, size=ready["bytes"], sha256=ready["sha256"]):
        archive_path.unlink(missing_ok=True)
        _download(volume, f"{prefix}/packs/{stem}.tar.zst", archive_path, expected_sha256=ready["sha256"])
    else:
        print(f"migration reusing cached {archive_path.name}: {archive_path.stat().st_size} bytes", flush=True)
    if archive_path.stat().st_size != ready["bytes"]:
        archive_path.unlink(missing_ok=True)
        raise ReceiveError(f"download byte count disagrees for bundle {stem}")
    try:
        print(f"migration extracting bundle {stem}", flush=True)
        records = extract_bundle(archive_path, manifest_path, root, ready)
    except ReceiveError:
        raise
    except Exception as exc:
        raise ReceiveError(f"cannot extract verified bundle {stem}: {exc}") from exc
    _atomic_json(state / "parts" / f"{stem}.complete.json", {"id": part_id, "records": records})
    print(f"migration verified bundle {stem}: {len(records)} entries", flush=True)
    return records


def _load_plan(volume: Any, prefix: str) -> list[dict[str, Any]]:
    payload = _load_json(volume, f"{prefix}/plan.json")
    groups = payload.get("groups") if isinstance(payload, dict) else None
    if not isinstance(groups, list):
        raise ReceiveError("plan.json must contain a groups list")
    seen = set()
    for group in groups:
        if not isinstance(group, dict):
            raise ReceiveError("each plan group must be an object")
        part_id, size = group.get("id"), group.get("bytes")
        if not isinstance(part_id, int) or isinstance(part_id, bool) or part_id < 0 or part_id > 99999:
            raise ReceiveError("group id must be an integer from 0 to 99999")
        if part_id in seen:
            raise ReceiveError(f"duplicate group id: {part_id}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ReceiveError(f"group {part_id} has invalid bytes")
        seen.add(part_id)
    return sorted(groups, key=lambda group: group["id"])


def _cached_file_matches(path: Path, *, sha256: str, size: int | None = None) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    actual_size, digest = _hash_file(path, progress_label=f"cached {path.name}")
    return digest.lower() == sha256.lower() and (size is None or actual_size == size)


def _is_not_found(exc: Exception) -> bool:
    return isinstance(exc, FileNotFoundError) or type(exc).__name__ == "NotFoundError"


def _load_plan_if_available(volume: Any, prefix: str) -> list[dict[str, Any]] | None:
    try:
        names = {Path(entry.path).name for entry in volume.listdir(prefix, recursive=False)}
    except Exception as exc:
        if _is_not_found(exc):
            return None
        raise
    if "plan.json" not in names:
        return None
    return _load_plan(volume, prefix)


def _existing_part(root: Path, state: Path, group: dict[str, Any]) -> list[dict[str, Any]] | None:
    marker = state / "parts" / f"{group['id']:05d}.complete.json"
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        records = data["records"]
        if data["id"] != group["id"]:
            return None
        verify_part(root, records, label=f"resume group {group['id']:05d}")
        print(f"migration resumed verified group {group['id']:05d}", flush=True)
        return records
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ReceiveError):
        return None


def _ready_ids(volume: Any, prefix: str) -> set[str]:
    try:
        entries = volume.listdir(f"{prefix}/packs", recursive=False)
    except Exception as exc:
        if _is_not_found(exc):
            return set()
        raise
    return {Path(entry.path).name for entry in entries if Path(entry.path).name.endswith(".ready.json")}


def _migration_complete(volume: Any, prefix: str) -> dict[str, Any] | None:
    try:
        names = {Path(entry.path).name for entry in volume.listdir(prefix, recursive=False)}
    except Exception as exc:
        if _is_not_found(exc):
            return None
        raise
    if "complete.json" not in names:
        return None
    value = _load_json(volume, f"{prefix}/complete.json")
    if not isinstance(value, dict):
        raise ReceiveError("migration complete.json must be an object")
    return value


class LocalVolume:
    """File-backed adapter for bundles relayed into a local spool directory."""

    def __init__(self, incoming_directory: Path, prefix: str = DEFAULT_PREFIX):
        self.root = Path(incoming_directory).resolve()
        self.prefix = "/" + str(_relative(prefix.lstrip("/"), "volume prefix"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _local_path(self, remote_path: str) -> Path:
        if not isinstance(remote_path, str) or "\\" in remote_path:
            raise ReceiveError("invalid incoming volume path")
        remote = remote_path.lstrip("/")
        prefix = self.prefix.lstrip("/")
        if remote == prefix:
            rel = ""
        elif remote.startswith(prefix + "/"):
            rel = remote[len(prefix) + 1 :]
        else:
            raise ReceiveError("incoming path is outside the configured migration prefix")
        if rel:
            rel_path = _relative(rel, "incoming path")
            candidate = self.root.joinpath(*rel_path.parts)
            current = self.root
            for part in rel_path.parts:
                current = current / part
                if current.is_symlink():
                    raise ReceiveError("incoming spool entries cannot be symlinks")
        else:
            candidate = self.root
        try:
            candidate.resolve(strict=False).relative_to(self.root)
        except ValueError as exc:
            raise ReceiveError("incoming path escapes the spool directory") from exc
        if candidate.is_symlink():
            raise ReceiveError("incoming spool entries cannot be symlinks")
        return candidate

    def listdir(self, path: str, *, recursive: bool = False) -> list[Any]:
        if recursive:
            raise ValueError("recursive local spool listings are not supported")
        directory = self._local_path(path)
        if not directory.exists():
            raise FileNotFoundError(path)
        if not directory.is_dir():
            raise NotADirectoryError(path)
        remote_directory = "/" + path.lstrip("/").rstrip("/")
        entries = sorted(directory.iterdir())
        if any(item.is_symlink() for item in entries):
            raise ReceiveError("incoming spool entries cannot be symlinks")
        return [SimpleNamespace(path=f"{remote_directory}/{item.name}") for item in entries if item.is_file()]

    def read_file(self, path: str):
        local = self._local_path(path)
        if not local.is_file():
            raise FileNotFoundError(path)

        def chunks():
            with local.open("rb") as stream:
                while block := stream.read(CHUNK_SIZE):
                    yield block

        return chunks()

    def read_file_into_fileobj(self, path: str, fileobj: BinaryIO, progress_cb=None) -> int:
        total = 0
        for block in self.read_file(path):
            written = fileobj.write(block)
            if written != len(block):
                raise OSError("short write while copying incoming bundle")
            total += written
            if progress_cb is not None:
                progress_cb(advance=written)
        return total


def receive(volume: Any, *, prefix: str = DEFAULT_PREFIX, root: Path = Path(DEFAULT_ROOT), state: Path = Path(DEFAULT_STATE), poll_seconds: int = 10) -> None:
    root, state = Path(root), Path(state)
    root.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    plan: list[dict[str, Any]] | None = None
    completed_parts: dict[int, list[dict[str, Any]]] = {}
    resume_checked = False
    last_log = 0.0
    last_completed = 0
    failed_iterations = 0
    while True:
        try:
            if plan is None:
                plan = _load_plan_if_available(volume, prefix)
                if plan is None:
                    failed_iterations = 0
                    raise _WaitForPublication("plan.json is not published yet")
            if not resume_checked:
                completed_parts = {
                    group["id"]: records
                    for group in plan
                    if (records := _existing_part(root, state, group)) is not None
                }
                resume_checked = True
                last_completed = len(completed_parts)

            ready = _ready_ids(volume, prefix)
            done = 0
            for group in plan:
                records = completed_parts.get(group["id"])
                if records is None:
                    stem = f"{group['id']:05d}.ready.json"
                    if stem not in ready:
                        break
                    records = process_part(volume, prefix, group, root, state)
                    completed_parts[group["id"]] = records
                done += 1
                last_completed = done
                _atomic_json(state / "progress.json", {"completed": done, "count": len(plan), "current_group": group["id"], "updated_at": time.time()})
            complete = _migration_complete(volume, prefix) if done == len(plan) else None
            if complete is not None:
                expected_files = sum(group.get("files", 0) for group in plan)
                expected_bytes = sum(group["bytes"] for group in plan)
                if complete.get("files") != expected_files or complete.get("uncompressed_bytes") != expected_bytes:
                    raise ReceiveError("migration complete totals disagree with plan")
                manifest = state / "all-files.jsonl"
                temporary = manifest.with_name(manifest.name + ".partial")
                with temporary.open("w", encoding="utf-8") as stream:
                    for group in plan:
                        for item in completed_parts[group["id"]]:
                            stream.write(json.dumps(item, sort_keys=True) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, manifest)
                return
            failed_iterations = 0
        except _WaitForPublication:
            failed_iterations = 0
        except Exception as exc:
            if isinstance(exc, ReceiveError):
                raise
            failed_iterations += 1
            if failed_iterations >= 5:
                raise ReceiveError(
                    f"receiver stopped after {failed_iterations} consecutive SDK/network failures ({type(exc).__name__})"
                ) from None
            now = time.monotonic()
            if now - last_log >= 30:
                print(f"migration receive waiting after SDK/network error ({type(exc).__name__})", file=sys.stderr, flush=True)
                last_log = now
        now = time.monotonic()
        if now - last_log >= 30:
            print(f"migration bundles complete: {last_completed}/{len(plan) if plan is not None else '?'}; waiting", flush=True)
            last_log = now
        time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--root", type=Path, default=Path(DEFAULT_ROOT))
    parser.add_argument("--state", type=Path, default=Path(DEFAULT_STATE))
    parser.add_argument(
        "--incoming-directory",
        type=Path,
        help="read a local SSH-relayed spool instead of connecting to Modal",
    )
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args(argv)
    if args.incoming_directory is not None:
        volume = LocalVolume(args.incoming_directory, prefix=args.prefix)
    else:
        import modal

        volume = modal.Volume.from_name("chelsea-archive")
    receive(volume, prefix=args.prefix, root=args.root, state=args.state, poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
