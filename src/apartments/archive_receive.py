"""Receive immutable archive bundles from a Modal Volume into local storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

CHUNK_SIZE = 1024 * 1024
DEFAULT_PREFIX = "/migrations/thelio-20260916"
DEFAULT_ROOT = "/data1/apartments/archive"
DEFAULT_STATE = "/data1/apartments/migration"


class ReceiveError(ValueError):
    """A bundle is malformed, unsafe, or does not match its manifest."""


def _relative(value: Any, label: str = "path") -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReceiveError(f"{label} must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ReceiveError(f"unsafe {label}: {value!r}")
    return path


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(CHUNK_SIZE):
            size += len(block)
            digest.update(block)
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


def _matches(path: Path, item: dict[str, Any]) -> bool:
    if item.get("type", "file") == "symlink":
        return path.is_symlink() and os.readlink(path) == item["target"]
    if not path.is_file() or path.is_symlink():
        return False
    size, digest = _hash_file(path)
    return size == item["size"] and digest == item["sha256"]


def verify_part(root: Path, records: list[dict[str, Any]]) -> None:
    for item in records:
        path = _ensure_no_symlink_parent(root, _relative(item["path"]))
        if not _matches(path, item):
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
            with tarfile.open(fileobj=reader, mode="r|") as tar:
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
                    digest = hashlib.sha256()
                    size = 0
                    try:
                        with source, partial.open("wb") as output:
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
    last_error: Exception | None = None
    for attempt in range(retries):
        partial = target.with_name(target.name + ".partial")
        partial.unlink(missing_ok=True)
        try:
            with partial.open("wb") as output:
                volume.read_file_into_fileobj(remote, output)
                output.flush()
                os.fsync(output.fileno())
            if expected_sha256:
                _, actual = _hash_file(partial)
                if actual.lower() != expected_sha256.lower():
                    raise ReceiveError(f"download checksum mismatch for {remote}")
            os.replace(partial, target)
            return
        except Exception as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt + 1 < retries:
                time.sleep(min(2 ** attempt, 30))
    raise ReceiveError(f"download failed after {retries} attempts: {remote}: {last_error}") from last_error


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
    return ready


def _load_json(volume: Any, path: str) -> Any:
    return json.loads(_read_volume(volume, path).decode("utf-8"))


def process_part(volume: Any, prefix: str, group: dict[str, Any], root: Path, state: Path) -> list[dict[str, Any]]:
    part_id = group["id"]
    stem = f"{part_id:05d}"
    ready_remote = f"{prefix}/packs/{stem}.ready.json"
    ready = _validate_ready(_load_json(volume, ready_remote))
    if "bytes" in group and group["bytes"] != ready["bytes"]:
        raise ReceiveError(f"plan byte count disagrees for bundle {stem}")
    local = state / "packs"
    archive_path, manifest_path = local / f"{stem}.tar.zst", local / f"{stem}.manifest.jsonl"
    _download(volume, f"{prefix}/packs/{stem}.manifest.jsonl", manifest_path)
    _download(volume, f"{prefix}/packs/{stem}.tar.zst", archive_path, expected_sha256=ready["sha256"])
    if archive_path.stat().st_size != ready["bytes"]:
        archive_path.unlink(missing_ok=True)
        raise ReceiveError(f"download byte count disagrees for bundle {stem}")
    records = extract_bundle(archive_path, manifest_path, root, ready)
    _atomic_json(state / "parts" / f"{stem}.complete.json", {"id": part_id, "records": records})
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


def _existing_part(root: Path, state: Path, group: dict[str, Any]) -> list[dict[str, Any]] | None:
    marker = state / "parts" / f"{group['id']:05d}.complete.json"
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        records = data["records"]
        if data["id"] != group["id"]:
            return None
        verify_part(root, records)
        return records
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ReceiveError):
        return None


def _ready_ids(volume: Any, prefix: str) -> set[str]:
    entries = volume.listdir(f"{prefix}/packs", recursive=False)
    return {Path(entry.path).name for entry in entries if Path(entry.path).name.endswith(".ready.json")}


def receive(volume: Any, *, prefix: str = DEFAULT_PREFIX, root: Path = Path(DEFAULT_ROOT), state: Path = Path(DEFAULT_STATE), poll_seconds: int = 10) -> None:
    root, state = Path(root), Path(state)
    root.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    plan: list[dict[str, Any]] | None = None
    last_log = 0.0
    while True:
        try:
            volume.reload()
            if plan is None:
                try:
                    plan = _load_plan(volume, prefix)
                except Exception:
                    plan = None
                    raise
            ready = _ready_ids(volume, prefix)
            done = 0
            all_records = []
            for group in plan:
                records = _existing_part(root, state, group)
                if records is None:
                    stem = f"{group['id']:05d}.ready.json"
                    if stem not in ready:
                        break
                    records = process_part(volume, prefix, group, root, state)
                done += 1
                all_records.extend(records)
                _atomic_json(state / "progress.json", {"completed": done, "count": len(plan), "current_group": group["id"], "updated_at": time.time()})
            if done == len(plan) and (root / "complete.json").is_file():
                all_records.sort(key=lambda item: item["path"])
                manifest = state / "all-files.jsonl"
                temporary = manifest.with_name(manifest.name + ".partial")
                with temporary.open("w", encoding="utf-8") as stream:
                    for item in all_records:
                        stream.write(json.dumps(item, sort_keys=True) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, manifest)
                return
        except Exception as exc:
            now = time.monotonic()
            if now - last_log >= 30:
                print(f"migration receive waiting after error: {exc}", file=sys.stderr, flush=True)
        now = time.monotonic()
        if now - last_log >= 30:
            completed = sum(_existing_part(root, state, group) is not None for group in plan or [])
            print(f"migration bundles complete: {completed}/{len(plan) if plan is not None else '?'}; waiting", flush=True)
            last_log = now
        time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--root", type=Path, default=Path(DEFAULT_ROOT))
    parser.add_argument("--state", type=Path, default=Path(DEFAULT_STATE))
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args(argv)
    import modal

    volume = modal.Volume.from_name("chelsea-archive")
    receive(volume, prefix=args.prefix, root=args.root, state=args.state, poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
