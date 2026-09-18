"""Corrupt or unexpected transform outputs must never become completed data."""

import json

import pyarrow.parquet as pq
import pytest

from apartments.granular_export import finish
from .test_granular_export import create_repeated_listing_export


@pytest.fixture
def export_root(tmp_path):
    _, root, _, _ = create_repeated_listing_export(tmp_path)
    return root


@pytest.mark.parametrize("table", ["snapshots", "event_mentions", "listing_exclusions"])
@pytest.mark.parametrize("empty", [False, True])
def test_unplanned_parts_are_rejected_even_when_empty(export_root, table, empty):
    source = next((export_root / table).glob("*.parquet"))
    rows = pq.read_table(source)
    extra = export_root / table / "stray" / "old.parquet"
    extra.parent.mkdir()
    pq.write_table(rows.slice(0, 0) if empty else rows, extra)
    with pytest.raises(ValueError, match="Output files mismatch.*unexpected"):
        finish(export_root)
    assert not (export_root / "complete.json").exists()


def test_missing_shard_is_rejected(export_root):
    (export_root / "event_mentions" / "part-00001.parquet").unlink()
    with pytest.raises(ValueError, match="Missing or damaged shard output 1"):
        finish(export_root)
    assert not (export_root / "complete.json").exists()


def test_mismatched_checkpoint_cannot_reuse_another_shard(export_root):
    first = export_root / "checkpoints" / "00000.json"
    second = export_root / "checkpoints" / "00001.json"
    second.write_bytes(first.read_bytes())
    with pytest.raises(ValueError, match="Checkpoint part mismatch"):
        finish(export_root)
    assert not (export_root / "complete.json").exists()


def test_missing_checkpoint_is_rejected(export_root):
    (export_root / "checkpoints" / "00001.json").unlink()
    with pytest.raises(ValueError, match="Missing shard checkpoint 1"):
        finish(export_root)
    assert not (export_root / "complete.json").exists()


def test_incomplete_checkpoint_table_set_is_rejected(export_root):
    path = export_root / "checkpoints" / "00000.json"
    checkpoint = json.loads(path.read_text())
    del checkpoint["counts"]["listing_exclusions"]
    path.write_text(json.dumps(checkpoint))
    with pytest.raises(ValueError, match="table set"):
        finish(export_root)
    assert not (export_root / "complete.json").exists()


def test_audit_disagreement_prevents_completion(export_root, monkeypatch):
    from apartments import granular_finalize

    original = granular_finalize.audit_dataset

    def changed_count(root):
        result = original(root)
        result["tables"]["counts"]["event_mentions"] += 1
        return result

    monkeypatch.setattr(granular_finalize, "audit_dataset", changed_count)
    with pytest.raises(ValueError, match="Audited count mismatch: event_mentions"):
        finish(export_root)
    assert not (export_root / "complete.json").exists()
    # A failed attempt remains resumable once the discrepancy is resolved.
    monkeypatch.setattr(granular_finalize, "audit_dataset", original)
    assert finish(export_root)["tables"]["counts"]["event_mentions"] == 4
