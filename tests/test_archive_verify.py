import hashlib
import json
import os
from pathlib import Path

import pytest

from apartments.archive_verify import ManifestError, main, verify


def _record(path: str, data: bytes) -> dict:
    return {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _manifest(path: Path, *records: dict) -> None:
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")


def test_verify_streamed_files_reports_missing_mismatch_and_unexpected(tmp_path: Path):
    root = tmp_path / "archive"
    root.mkdir()
    (root / "good.bin").write_bytes(b"good")
    (root / "changed.bin").write_bytes(b"changed")
    (root / "extra").write_text("extra")
    manifest = tmp_path / "manifest.jsonl"
    _manifest(manifest, _record("good.bin", b"good"), _record("changed.bin", b"original"), _record("missing.bin", b"absent"))

    result = verify(root, manifest, check_unexpected=True)

    assert result["verified_count"] == 1
    assert result["missing"] == ["missing.bin"]
    assert result["mismatches"][0]["path"] == "changed.bin"
    assert result["unexpected"] == ["extra"]
    assert result["ok"] is False


def test_verify_symlink_with_explicit_absolute_prefix_map(tmp_path: Path):
    root = tmp_path / "archive"
    (root / "bodies").mkdir(parents=True)
    os.symlink("bodies", root / "current")
    manifest = tmp_path / "manifest.jsonl"
    _manifest(manifest, {"path": "current", "type": "symlink", "target": "/archive/bodies"})

    result = verify(root, manifest, prefix_maps=["/archive=."])

    assert result["ok"] is True


def test_manifest_rejects_traversal_and_missing_checksum(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"path": "../outside", "size": 0, "sha256": "0" * 64}) + "\n")
    with pytest.raises(ManifestError, match="unsafe path"):
        verify(tmp_path, manifest)
    manifest.write_text(json.dumps({"path": "file", "size": 0}) + "\n")
    with pytest.raises(ManifestError, match="sha256"):
        verify(tmp_path, manifest)


def test_cli_writes_atomic_summary_outside_source_and_returns_failure_status(tmp_path: Path):
    root = tmp_path / "archive"
    root.mkdir()
    (root / "file").write_bytes(b"content")
    manifest = tmp_path / "manifest.jsonl"
    _manifest(manifest, _record("file", b"content"))
    summary = tmp_path / "reports" / "verify.json"

    status = main(["--root", str(root), "--manifest", str(manifest), "--summary", str(summary)])

    assert status == 0
    assert json.loads(summary.read_text())["ok"] is True
    assert not list(summary.parent.glob("*.tmp"))


def test_cli_rejects_summary_inside_destination(tmp_path: Path):
    root = tmp_path / "archive"
    root.mkdir()
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("")

    assert main(["--root", str(root), "--manifest", str(manifest), "--summary", str(root / "summary.json")]) == 2

