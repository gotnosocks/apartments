import pytest

from models.publish_floor_increment_audit import _publish
from apartments.research_pipeline import _verified_bundle, digest


def test_binary_design_publication_replay_and_immutability(tmp_path):
    files = {
        "time-design.npz": b"\x00\x01\xffbinary-design",
        "audit.json": b'{"status":"design_only"}\n',
    }
    metadata = {
        "version": "test-floor-audit",
        "status": "design_only_no_fit_no_posterior",
    }
    first = _publish(tmp_path, files, metadata)
    before = digest(tmp_path / "complete.json")
    assert _publish(tmp_path, files, metadata) == first
    assert digest(tmp_path / "complete.json") == before
    assert _verified_bundle(tmp_path)[0] == first
    with pytest.raises(ValueError, match="Immutable audit differs"):
        _publish(tmp_path, {**files, "time-design.npz": b"changed"}, metadata)
    assert (tmp_path / "time-design.npz").read_bytes() == files["time-design.npz"]


def test_tampered_saved_design_blocks_replay(tmp_path):
    files = {"time-design.npz": b"original"}
    _publish(tmp_path, files, {"version": "test"})
    (tmp_path / "time-design.npz").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        _publish(tmp_path, files, {"version": "test"})
