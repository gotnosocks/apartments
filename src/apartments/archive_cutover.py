"""Validate a completed archive migration before activating local services."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any

DATASET_ID = "chelsea-granular-20260916"
SQLITE_RELATIVE_PATH = "crawls/chelsea-resume/archive.sqlite3"
REVIEW_LEDGER_RELATIVE_PATH = f"reviews/{DATASET_ID}/review-ledger.jsonl"


class CutoverError(ValueError):
    """Migration artifacts or destination contents failed validation."""


def _safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CutoverError("manifest path must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise CutoverError(f"unsafe manifest path: {value!r}")
    return path.as_posix()


def _safe_link_target(link_path: str, target: Any) -> str:
    if not isinstance(target, str) or not target or "\\" in target or target.startswith("/"):
        raise CutoverError(f"invalid symlink target for {link_path}")
    resolved = list(PurePosixPath(link_path).parent.parts)
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not resolved:
                raise CutoverError(f"symlink escapes archive root: {link_path}")
            resolved.pop()
        else:
            resolved.append(part)
    return target


def _read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CutoverError(f"{path.name} line {line_number}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise CutoverError(f"{path.name} line {line_number}: expected an object")
            rel = _safe_relative(record.get("path"))
            kind = record.get("type", "file")
            if kind == "file":
                size, digest = record.get("size"), record.get("sha256")
                if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                    raise CutoverError(f"{path.name} line {line_number}: invalid file size")
                if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
                    raise CutoverError(f"{path.name} line {line_number}: invalid file SHA-256")
                records.append({"path": rel, "size": size, "sha256": digest.lower()})
            elif kind == "symlink":
                target = _safe_link_target(rel, record.get("target"))
                records.append({"path": rel, "type": "symlink", "target": target})
            else:
                raise CutoverError(f"{path.name} line {line_number}: unsupported entry type {kind!r}")
    return records


def _by_path(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result = {}
    for item in records:
        path = item["path"]
        if path in result:
            raise CutoverError(f"duplicate path in {label}: {path}")
        result[path] = item
    return result


def _canonical(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    return _by_path(records, label)


def _marker_path(state: Path, group_id: int) -> Path:
    return state / "parts" / f"{group_id:05d}.complete.json"


def _load_part(state: Path, group: dict[str, Any]) -> list[dict[str, Any]]:
    marker_path = _marker_path(state, group["id"])
    if not marker_path.is_file():
        raise CutoverError(f"missing verified part marker {marker_path.name}")
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CutoverError(f"invalid verified part marker {marker_path.name}") from exc
    if not isinstance(marker, dict) or marker.get("id") != group["id"] or not isinstance(marker.get("records"), list):
        raise CutoverError(f"part marker identity/records mismatch: {marker_path.name}")
    records = marker["records"]
    normalized = []
    # Re-use manifest validation semantics without materializing another archive.
    for record in records:
        if not isinstance(record, dict):
            raise CutoverError(f"invalid record in {marker_path.name}")
        rel = _safe_relative(record.get("path"))
        if record.get("type", "file") == "symlink":
            target = _safe_link_target(rel, record.get("target"))
            normalized.append({"path": rel, "type": "symlink", "target": target})
        else:
            size, digest = record.get("size"), record.get("sha256")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise CutoverError(f"invalid size in {marker_path.name}: {rel}")
            if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
                raise CutoverError(f"invalid SHA-256 in {marker_path.name}: {rel}")
            normalized.append({"path": rel, "size": size, "sha256": digest.lower()})
    if len(normalized) != group.get("files"):
        raise CutoverError(f"part {group['id']} marker file count differs from plan")
    byte_count = sum(record.get("size", 0) for record in normalized if record.get("type", "file") == "file")
    if byte_count != group.get("bytes"):
        raise CutoverError(f"part {group['id']} marker byte count differs from plan")
    _by_path(normalized, marker_path.name)
    return normalized


def _compare_manifests(state: Path, plan: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups = plan.get("groups")
    if not isinstance(groups, list) or not groups:
        raise CutoverError("migration plan must contain non-empty groups")
    ids = set()
    expected: dict[str, dict[str, Any]] = {}
    completed_bytes = completed_files = 0
    for group in groups:
        if not isinstance(group, dict):
            raise CutoverError("migration plan group must be an object")
        group_id, files, size = group.get("id"), group.get("files"), group.get("bytes")
        if not isinstance(group_id, int) or isinstance(group_id, bool) or group_id < 0 or group_id > 99999 or group_id in ids:
            raise CutoverError("migration plan contains an invalid or duplicate group id")
        if not isinstance(files, int) or isinstance(files, bool) or files < 0:
            raise CutoverError(f"migration group {group_id} has invalid file count")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise CutoverError(f"migration group {group_id} has invalid byte count")
        ids.add(group_id)
        print(f"cutover: checking verified migration group {group_id:05d}", flush=True)
        part = _load_part(state, group)
        for record in part:
            if record["path"] in expected:
                raise CutoverError(f"path appears in multiple migration groups: {record['path']}")
            expected[record["path"]] = record
        completed_files += len(part)
        completed_bytes += sum(record.get("size", 0) for record in part if record.get("type", "file") == "file")
    for key, actual in (("total_files", completed_files), ("total_bytes", completed_bytes)):
        if plan.get(key) != actual:
            raise CutoverError(f"migration plan {key} mismatch: expected {plan.get(key)}, found {actual}")

    all_files_path = state / "all-files.jsonl"
    if not all_files_path.is_file():
        raise CutoverError("receiver has not written all-files.jsonl")
    final_records = _read_records(all_files_path)
    actual = _canonical(final_records, "all-files.jsonl")
    extras = sorted(actual.keys() - expected.keys())
    missing = sorted(expected.keys() - actual.keys())
    changed = sorted(path for path in actual.keys() & expected.keys() if actual[path] != expected[path])
    if extras or missing or changed:
        raise CutoverError(
            f"joined manifest differs from part markers (extra={extras[:3]}, missing={missing[:3]}, changed={changed[:3]})"
        )
    if len(final_records) != plan["total_files"]:
        raise CutoverError("joined manifest record count differs from migration plan")
    return final_records, {"files": completed_files, "bytes": completed_bytes, "groups": len(groups)}


def _walk_destination(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        for name in list(dirs):
            path = base / name
            if path.is_symlink():
                rel = path.relative_to(root).as_posix()
                found[rel] = "symlink"
                dirs.remove(name)
        for name in files:
            path = base / name
            rel = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                found[rel] = "symlink"
            elif stat.S_ISREG(mode):
                found[rel] = "file"
            else:
                found[rel] = "other"
    return found


def _verify_destination(root: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    found = _walk_destination(root)
    expected = _by_path(records, "all-files.jsonl")
    missing, extra = sorted(expected.keys() - found.keys()), sorted(found.keys() - expected.keys())
    wrong_types = sorted(path for path in expected.keys() & found.keys() if found[path] != expected[path].get("type", "file"))
    if missing or extra or wrong_types:
        raise CutoverError(f"destination entry set mismatch (missing={missing[:3]}, extra={extra[:3]}, wrong_type={wrong_types[:3]})")
    total_bytes = 0
    for path, record in expected.items():
        item = root.joinpath(*PurePosixPath(path).parts)
        if record.get("type", "file") == "symlink":
            if os.readlink(item) != record["target"]:
                raise CutoverError(f"destination symlink target mismatch: {path}")
            try:
                item.resolve(strict=False).relative_to(root.resolve())
            except ValueError as exc:
                raise CutoverError(f"destination symlink escapes archive root: {path}") from exc
        else:
            size = item.lstat().st_size
            if size != record["size"]:
                raise CutoverError(f"destination file size mismatch: {path}")
            total_bytes += size
    ledger = expected.get(REVIEW_LEDGER_RELATIVE_PATH)
    if ledger is not None:
        if ledger.get("type", "file") != "file":
            raise CutoverError("review ledger is not a regular manifest file")
        ledger_path = root / REVIEW_LEDGER_RELATIVE_PATH
        if not ledger_path.is_file() or ledger_path.is_symlink():
            raise CutoverError("review ledger is not a regular destination file")
        # The ledger is small; hash it specifically without rereading the archive.
        digest = hashlib.sha256()
        with ledger_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != ledger["sha256"]:
            raise CutoverError("review ledger checksum mismatch")
        ledger_state: str | None = REVIEW_LEDGER_RELATIVE_PATH
    else:
        ledger_path = root / REVIEW_LEDGER_RELATIVE_PATH
        if ledger_path.exists() or ledger_path.is_symlink():
            raise CutoverError("destination review ledger exists but is absent from migration manifest")
        ledger_state = None
    print(f"cutover: checked {len(expected)} destination entries ({total_bytes} file bytes)", flush=True)
    return {"files": len(expected), "bytes": total_bytes, "review_ledger": ledger_state}


def _quick_check_sqlite(path: Path, cache_kib: int = 8192) -> dict[str, Any]:
    if not path.is_file():
        raise CutoverError(f"canonical SQLite archive missing: {path}")
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.execute(f"PRAGMA cache_size = -{int(cache_kib)}")
            connection.execute("PRAGMA query_only = ON")
            stop_progress = threading.Event()

            def report_progress() -> None:
                while not stop_progress.wait(30):
                    print("cutover: SQLite quick_check still running", flush=True)

            progress_thread = threading.Thread(target=report_progress, daemon=True)
            progress_thread.start()
            print(f"cutover: starting SQLite quick_check ({cache_kib} KiB cache)", flush=True)
            cursor = connection.execute("PRAGMA quick_check")
            first = cursor.fetchone()
            if first != ("ok",) or cursor.fetchone() is not None:
                raise CutoverError(f"SQLite quick_check failed: {first!r}")
            stop_progress.set()
            progress_thread.join()
        finally:
            if "stop_progress" in locals():
                stop_progress.set()
                progress_thread.join()
            connection.close()
    except sqlite3.Error as exc:
        raise CutoverError(f"SQLite quick_check could not complete: {exc}") from exc
    print(f"cutover: SQLite quick_check passed (cache {cache_kib} KiB)", flush=True)
    return {"path": SQLITE_RELATIVE_PATH, "quick_check": "ok", "cache_kib": cache_kib}


def _parquet_counts(dataset_root: Path, complete: dict[str, Any], report: dict[str, Any]) -> dict[str, int]:
    import pyarrow.parquet as pq

    complete_counts = complete.get("counts")
    report_counts = report.get("tables", {}).get("counts")
    if not isinstance(complete_counts, dict) or not isinstance(report_counts, dict) or complete_counts != report_counts:
        raise CutoverError("dataset complete.json counts differ from quality-report.json")
    actual_counts = {}
    for table, expected in report_counts.items():
        if not isinstance(table, str) or not table.isidentifier():
            raise CutoverError(f"quality report has invalid table name {table!r}")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
            raise CutoverError(f"quality report has invalid row count for {table}")
        paths = sorted((dataset_root / table).rglob("*.parquet")) if (dataset_root / table).exists() else []
        count = 0
        for path in paths:
            try:
                if not stat.S_ISREG(path.lstat().st_mode):
                    raise CutoverError(f"Parquet path is not a regular file: {path.relative_to(dataset_root)}")
                count += pq.read_metadata(path).num_rows
            except CutoverError:
                raise
            except Exception as exc:
                raise CutoverError(f"cannot read Parquet footer {path.relative_to(dataset_root)}: {exc}") from exc
        if count != expected:
            raise CutoverError(f"Parquet row count mismatch for {table}: expected {expected}, found {count}")
        actual_counts[table] = count
        print(f"cutover: Parquet metadata {table}: {count} rows", flush=True)
    return actual_counts


def validate(root: Path, state: Path) -> dict[str, Any]:
    root, state = Path(root).resolve(), Path(state).resolve()
    plan_path = state / "plan.json"
    if not plan_path.is_file():
        raise CutoverError(f"migration plan missing: {plan_path}")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CutoverError("migration plan is invalid JSON") from exc
    if not isinstance(plan, dict):
        raise CutoverError("migration plan must be an object")
    records, migration = _compare_manifests(state, plan)
    destination = _verify_destination(root, records)
    if destination["files"] != migration["files"] or destination["bytes"] != migration["bytes"]:
        raise CutoverError("destination count/byte totals differ from verified migration manifests")

    dataset_root = root / "datasets" / DATASET_ID
    try:
        complete = json.loads((dataset_root / "complete.json").read_text(encoding="utf-8"))
        report = json.loads((dataset_root / "quality-report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CutoverError("granular dataset complete marker or quality report is missing/invalid") from exc
    parquet_counts = _parquet_counts(dataset_root, complete, report)
    sqlite_result = _quick_check_sqlite(root / SQLITE_RELATIVE_PATH)
    return {
        "validated_at": time.time(),
        "dataset": DATASET_ID,
        "migration": migration,
        "destination": destination,
        "sqlite": sqlite_result,
        "parquet_row_counts": parquet_counts,
        "quality_report": "datasets/" + DATASET_ID + "/quality-report.json",
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def finalize(root: Path, state: Path) -> dict[str, Any]:
    marker = Path(state) / "cutover-ready.json"
    if marker.exists() or marker.is_symlink():
        raise CutoverError("cutover-ready.json already exists; refusing to replace the authority marker")
    result = validate(root, state)
    if marker.exists() or marker.is_symlink():
        raise CutoverError("cutover-ready.json appeared during validation; refusing to replace it")
    _atomic_json(marker, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/data1/apartments/archive"))
    parser.add_argument("--state", type=Path, default=Path("/data1/apartments/migration"))
    args = parser.parse_args(argv)
    result = finalize(args.root, args.state)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    print(f"CUTOVER READY: {Path(args.state) / 'cutover-ready.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
