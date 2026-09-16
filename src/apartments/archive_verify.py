"""Verify a transferred archive tree against a JSONL file manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

CHUNK_SIZE = 1024 * 1024
MAX_SQLITE_CACHE_KIB = 65536


class ManifestError(ValueError):
    pass


def _relative_path(value: Any, *, label: str = "path") -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ManifestError(f"{label} must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ManifestError(f"unsafe {label}: {value!r}")
    return path


def _load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ManifestError(f"manifest line {line_number}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ManifestError(f"manifest line {line_number}: expected an object")
            rel = str(_relative_path(record.get("path")))
            if rel in records:
                raise ManifestError(f"manifest line {line_number}: duplicate path {rel!r}")
            kind = record.get("type", "file")
            if kind == "file":
                size, digest = record.get("size"), record.get("sha256")
                if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                    raise ManifestError(f"manifest line {line_number}: file size must be a non-negative integer")
                if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
                    raise ManifestError(f"manifest line {line_number}: file sha256 must be 64 hex characters")
                records[rel] = {"type": "file", "size": size, "sha256": digest.lower()}
            elif kind == "symlink":
                target = record.get("target")
                if not isinstance(target, str) or not target:
                    raise ManifestError(f"manifest line {line_number}: symlink target must be a non-empty string")
                records[rel] = {"type": "symlink", "target": target}
            else:
                raise ManifestError(f"manifest line {line_number}: unsupported record type {kind!r}")
    return records


def _parse_prefix_maps(values: list[str]) -> list[tuple[str, str]]:
    result = []
    for value in values:
        if "=" not in value:
            raise ManifestError("prefix map must be OLD=NEW")
        old, new = value.split("=", 1)
        if not old.startswith("/") or not old.rstrip("/"):
            raise ManifestError(f"prefix map source must be an absolute path: {old!r}")
        if new.startswith("/"):
            if any(part in (".", "..") for part in new.split("/") if part):
                raise ManifestError(f"unsafe absolute prefix map destination: {new!r}")
            normalized_new = str(PurePosixPath(new))
        else:
            _relative_path(new.rstrip("/") or ".", label="prefix map destination") if new not in ("", ".") else None
            normalized_new = "" if new in ("", ".", "./") else new.strip("/")
        result.append((old.rstrip("/") or "/", normalized_new))
    return sorted(result, key=lambda pair: len(pair[0]), reverse=True)


def _mapped_target(target: str, maps: list[tuple[str, str]]) -> str:
    if target.startswith("/"):
        for old, new in maps:
            if target == old or target.startswith(old.rstrip("/") + "/"):
                suffix = target[len(old):].lstrip("/")
                if new.startswith("/"):
                    return str(PurePosixPath(new) / suffix) if suffix else new
                return "/".join(part for part in (new, suffix) if part)
        raise ManifestError(f"absolute symlink target needs an explicit prefix map: {target!r}")
    return target


def _resolve_link_inside_root(link_path: Path, target: str, root: Path) -> bool:
    candidate = Path(target) if target.startswith("/") else link_path.parent / target
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _walk_entries(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        for name in list(dirs):
            item = base / name
            if item.is_symlink():
                rel = item.relative_to(root).as_posix()
                found[rel] = "symlink"
                dirs.remove(name)
        for name in files:
            item = base / name
            rel = item.relative_to(root).as_posix()
            found[rel] = "symlink" if item.is_symlink() else ("file" if item.is_file() else "other")
    return found


def _quick_check(path: Path, cache_kib: int) -> dict[str, Any]:
    uri = f"file:{quote(path.resolve().as_posix(), safe='/')}?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True)
        try:
            db.execute(f"PRAGMA cache_size = -{cache_kib}")
            rows = [row[0] for row in db.execute("PRAGMA quick_check")]
        finally:
            db.close()
    except sqlite3.Error as exc:
        return {"path": str(path), "ok": False, "error": str(exc)}
    return {"path": str(path), "ok": rows == ["ok"], "result": rows[:20], "result_count": len(rows)}


def verify(
    root: Path,
    manifest_path: Path,
    *,
    check_unexpected: bool = False,
    prefix_maps: list[str] | None = None,
    databases: list[str] | None = None,
    sqlite_cache_kib: int = 8192,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ManifestError(f"destination root is not a directory: {root}")
    manifest_path = manifest_path.resolve(strict=True)
    records = _load_manifest(manifest_path)
    maps = _parse_prefix_maps(prefix_maps or [])
    found = _walk_entries(root)
    result: dict[str, Any] = {
        "root": str(root), "manifest": str(manifest_path), "expected_count": len(records),
        "verified_count": 0, "missing": [], "mismatches": [], "unexpected": [], "sqlite_checks": [],
    }
    for rel, record in records.items():
        item = root.joinpath(*PurePosixPath(rel).parts)
        actual_kind = found.get(rel)
        if actual_kind is None:
            result["missing"].append(rel)
            continue
        if actual_kind != record["type"]:
            result["mismatches"].append({"path": rel, "reason": "type", "expected": record["type"], "actual": actual_kind})
            continue
        if record["type"] == "file":
            size = item.stat().st_size
            digest = hashlib.sha256()
            with item.open("rb") as stream:
                while chunk := stream.read(CHUNK_SIZE):
                    digest.update(chunk)
            actual_digest = digest.hexdigest()
            if size != record["size"]:
                result["mismatches"].append({"path": rel, "reason": "size", "expected": record["size"], "actual": size})
            elif actual_digest != record["sha256"]:
                result["mismatches"].append({"path": rel, "reason": "sha256", "expected": record["sha256"], "actual": actual_digest})
            else:
                result["verified_count"] += 1
        else:
            expected_target = _mapped_target(record["target"], maps)
            actual_target = os.readlink(item)
            if not _resolve_link_inside_root(item, actual_target, root):
                result["mismatches"].append({"path": rel, "reason": "unsafe_symlink_target", "actual": actual_target})
            elif actual_target != expected_target:
                result["mismatches"].append({"path": rel, "reason": "symlink_target", "expected": expected_target, "actual": actual_target})
            else:
                result["verified_count"] += 1
    if check_unexpected:
        result["unexpected"] = sorted(set(found) - set(records))
    for database in databases or []:
        rel = _relative_path(database, label="database path")
        db_path = root.joinpath(*rel.parts)
        try:
            db_path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError):
            result["sqlite_checks"].append({"path": str(rel), "ok": False, "error": "database path is missing or outside destination root"})
            continue
        if not db_path.is_file() or db_path.is_symlink():
            result["sqlite_checks"].append({"path": str(rel), "ok": False, "error": "database path is not a regular file"})
            continue
        result["sqlite_checks"].append(_quick_check(db_path, sqlite_cache_kib))
    result["ok"] = not result["missing"] and not result["mismatches"] and not result["unexpected"] and all(x["ok"] for x in result["sqlite_checks"])
    return result


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="transferred archive directory")
    parser.add_argument("--manifest", required=True, type=Path, help="JSONL manifest")
    parser.add_argument("--summary", required=True, type=Path, help="verification JSON output, outside --root")
    parser.add_argument("--check-unexpected", action="store_true", help="report all unlisted files and symlinks")
    parser.add_argument("--symlink-prefix-map", action="append", default=[], metavar="OLD=NEW", help="map an absolute legacy target prefix to a destination-root-relative prefix")
    parser.add_argument("--database", action="append", default=[], help="relative SQLite path to check with read-only PRAGMA quick_check")
    parser.add_argument("--sqlite-cache-kib", type=int, default=8192, help="SQLite page cache limit for each requested quick_check")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        summary = args.summary.resolve(strict=False)
        if summary == root or root in summary.parents:
            raise ManifestError("summary output must be outside the destination root")
        if not 1 <= args.sqlite_cache_kib <= MAX_SQLITE_CACHE_KIB:
            raise ManifestError(f"SQLite cache limit must be between 1 and {MAX_SQLITE_CACHE_KIB} KiB")
        result = verify(root, args.manifest, check_unexpected=args.check_unexpected, prefix_maps=args.symlink_prefix_map, databases=args.database, sqlite_cache_kib=args.sqlite_cache_kib)
        _atomic_json(args.summary, result)
    except (ManifestError, OSError) as exc:
        print(f"archive verification failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": result["ok"], "verified_count": result["verified_count"], "expected_count": result["expected_count"], "summary": str(args.summary)}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
