import hashlib
import io
import json
import sys
import tarfile
import types
from types import SimpleNamespace

import pytest

from apartments.archive_receive import LocalVolume, ReceiveError, _download, extract_bundle, verify_part


def _bundle(tmp_path, name="nested/file.txt", data=b"archive data"):
    tar_path = tmp_path / "pack.tar.zst"
    with tarfile.open(tar_path, "w:") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    manifest_path = tmp_path / "pack.manifest.jsonl"
    record = {"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return tar_path, manifest_path, {"files": 1, "uncompressed_bytes": len(data)}


def _passthrough_zstd(monkeypatch):
    class Decompressor:
        def stream_reader(self, stream):
            return stream

    monkeypatch.setitem(sys.modules, "zstandard", types.SimpleNamespace(ZstdDecompressor=Decompressor))


def test_extract_and_resume_verifies_each_file(tmp_path, monkeypatch):
    _passthrough_zstd(monkeypatch)
    archive, manifest, ready = _bundle(tmp_path)
    root = tmp_path / "archive"
    records = extract_bundle(archive, manifest, root, ready)
    assert (root / "nested/file.txt").read_bytes() == b"archive data"
    verify_part(root, records)
    # A second pass recognizes the already verified bytes and does not replace them.
    extract_bundle(archive, manifest, root, ready)
    assert (root / "nested/file.txt").read_bytes() == b"archive data"


def test_rejects_tar_path_traversal(tmp_path, monkeypatch):
    _passthrough_zstd(monkeypatch)
    archive, manifest, ready = _bundle(tmp_path, "../escape.txt")
    manifest.write_text(
        json.dumps({"path": "escape.txt", "size": 12, "sha256": hashlib.sha256(b"archive data").hexdigest()}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ReceiveError, match="unsafe tar member path"):
        extract_bundle(archive, manifest, tmp_path / "archive", ready)
    assert not (tmp_path / "escape.txt").exists()


def test_download_checksum_is_checked_before_atomic_install(tmp_path):
    class Volume:
        def read_file_into_fileobj(self, path, output, progress_cb=None):
            output.write(b"incorrect payload")

    target = tmp_path / "bundle.tar.zst"
    with pytest.raises(ReceiveError, match="download checksum mismatch"):
        _download(Volume(), "/packs/00000.tar.zst", target, expected_sha256="0" * 64, retries=1)
    assert not target.exists()
    assert not target.with_name(target.name + ".partial").exists()


def test_receive_caches_resume_verification_across_polls(tmp_path, monkeypatch):
    import apartments.archive_receive as receiver

    data = b"already there"
    record = {"path": "existing.txt", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    root, state = tmp_path / "archive", tmp_path / "state"
    root.mkdir()
    state.mkdir()
    (root / record["path"]).write_bytes(data)
    marker = state / "parts" / "00000.complete.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps({"id": 0, "records": [record]}), encoding="utf-8")
    payloads = {
        "/migration/plan.json": {"groups": [{"id": 0, "files": 1, "bytes": len(data)}]},
        "/migration/complete.json": {"files": 1, "bytes": 1, "uncompressed_bytes": len(data)},
    }

    class FakeVolume:
        prefix_calls = 0

        def listdir(self, path, recursive=False):
            if path == "/migration":
                self.prefix_calls += 1
                names = ["plan.json"]
                if self.prefix_calls >= 3:
                    names.append("complete.json")
            elif path == "/migration/packs":
                names = ["00000.ready.json"]
            else:
                names = []
            return [SimpleNamespace(path=f"{path}/{name}") for name in names]

        def read_file(self, path):
            return iter([json.dumps(payloads[path]).encode("utf-8")])

    checked = []
    original = receiver._existing_part

    def count_check(*args):
        checked.append(args[2]["id"])
        return original(*args)

    monkeypatch.setattr(receiver, "_existing_part", count_check)
    monkeypatch.setattr(receiver.time, "sleep", lambda seconds: None)
    receiver.receive(FakeVolume(), prefix="/migration", root=root, state=state, poll_seconds=0)
    assert checked == [0]
    assert (state / "all-files.jsonl").read_text(encoding="utf-8").strip() == json.dumps(record, sort_keys=True)


def test_local_volume_reads_relayed_spool_without_modal(tmp_path):
    spool = tmp_path / "incoming"
    (spool / "packs").mkdir(parents=True)
    payload = b"x" * (1024 * 1024 + 19)
    (spool / "plan.json").write_text("{}", encoding="utf-8")
    (spool / "packs" / "00000.tar.zst").write_bytes(payload)
    volume = LocalVolume(spool, prefix="/migration")

    listed = volume.listdir("/migration/packs", recursive=False)
    assert [entry.path for entry in listed] == ["/migration/packs/00000.tar.zst"]
    assert b"".join(volume.read_file("/migration/packs/00000.tar.zst")) == payload
    destination = io.BytesIO()
    copied = volume.read_file_into_fileobj("/migration/packs/00000.tar.zst", destination)
    assert copied == len(payload)
    assert destination.getvalue() == payload
    with pytest.raises(ReceiveError, match="unsafe incoming path"):
        list(volume.read_file("/migration/../outside"))


def test_local_volume_rejects_symlinked_spool_parent(tmp_path):
    spool, outside = tmp_path / "incoming", tmp_path / "outside"
    spool.mkdir()
    outside.mkdir()
    (spool / "packs").symlink_to(outside, target_is_directory=True)
    volume = LocalVolume(spool, prefix="/migration")
    with pytest.raises(ReceiveError, match="cannot be symlinks"):
        volume.listdir("/migration/packs", recursive=False)


def test_receiver_stops_after_five_sdk_failures(tmp_path, monkeypatch):
    import apartments.archive_receive as receiver

    class BrokenVolume:
        def listdir(self, path, recursive=False):
            raise RuntimeError("temporary service failure")

    monkeypatch.setattr(receiver.time, "sleep", lambda seconds: None)
    with pytest.raises(ReceiveError, match="5 consecutive SDK/network failures"):
        receiver.receive(BrokenVolume(), prefix="/migration", root=tmp_path / "archive", state=tmp_path / "state", poll_seconds=0)
