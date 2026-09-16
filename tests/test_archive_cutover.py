import hashlib
import json
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from apartments.archive_cutover import CutoverError, DATASET_ID, finalize


def _fixture(tmp_path, *, include_ledger=True):
    root, state = tmp_path / "archive", tmp_path / "migration"
    dataset = root / "datasets" / DATASET_ID
    (root / "crawls/chelsea-resume").mkdir(parents=True)
    (dataset / "listing_observations").mkdir(parents=True)
    (dataset / "event_mentions").mkdir(parents=True)
    if include_ledger:
        ledger = root / "reviews" / DATASET_ID / "review-ledger.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text('{"action":"review"}\n', encoding="utf-8")
    with sqlite3.connect(root / "crawls/chelsea-resume/archive.sqlite3") as db:
        db.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        db.executemany("INSERT INTO sample VALUES (?)", [(1,), (2,)])
    pq.write_table(pa.table({"snapshot_id": [1, 2]}), dataset / "listing_observations/part-00000.parquet")
    pq.write_table(pa.table({"snapshot_id": [1]}), dataset / "event_mentions/part-00000.parquet")
    counts = {"listing_observations": 2, "event_mentions": 1}
    (dataset / "quality-report.json").write_text(
        json.dumps({"tables": {"counts": counts}}), encoding="utf-8"
    )
    (dataset / "complete.json").write_text(json.dumps({"counts": counts}), encoding="utf-8")

    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        data = path.read_bytes()
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    state.mkdir()
    total_bytes = sum(item["size"] for item in records)
    plan = {"total_files": len(records), "total_bytes": total_bytes, "groups": [{"id": 0, "files": len(records), "bytes": total_bytes}]}
    (state / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (state / "parts").mkdir()
    part = {"id": 0, "records": records}
    (state / "parts/00000.complete.json").write_text(json.dumps(part), encoding="utf-8")
    (state / "all-files.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )
    return root, state


def test_cutover_writes_ready_marker_after_all_checks(tmp_path):
    root, state = _fixture(tmp_path)
    result = finalize(root, state)
    marker = json.loads((state / "cutover-ready.json").read_text(encoding="utf-8"))
    assert marker["sqlite"]["quick_check"] == "ok"
    assert marker["migration"]["groups"] == 1
    assert marker["parquet_row_counts"] == {"listing_observations": 2, "event_mentions": 1}
    assert marker == result


def test_cutover_failure_does_not_write_ready_marker(tmp_path):
    root, state = _fixture(tmp_path)
    marker = state / "cutover-ready.json"
    (state / "parts/00000.complete.json").unlink()
    with pytest.raises(CutoverError, match="missing verified part marker"):
        finalize(root, state)
    assert not marker.exists()


def test_absent_review_ledger_is_accepted_and_reported(tmp_path):
    root, state = _fixture(tmp_path, include_ledger=False)
    result = finalize(root, state)
    assert result["destination"]["review_ledger"] is None


def test_existing_cutover_marker_is_never_replaced(tmp_path):
    root, state = _fixture(tmp_path)
    marker = state / "cutover-ready.json"
    marker.write_text("human-reviewed marker", encoding="utf-8")
    with pytest.raises(CutoverError, match="already exists"):
        finalize(root, state)
    assert marker.read_text(encoding="utf-8") == "human-reviewed marker"
