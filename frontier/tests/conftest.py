import hashlib
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import api_records, leaderboard


@pytest.fixture(autouse=True)
def _no_lot_registry(monkeypatch):
    """Paired SEs in tests are iid unless a test gives rows their lots: the
    real lot lookup loads the whole dataset and the NB8 registry."""
    monkeypatch.setattr(leaderboard, "_row_lots", lambda: None)


@pytest.fixture
def records_catalog(tmp_path, monkeypatch):
    """A writer of pipeline datasets under tmp_path, with `api_records` reading them.

    `write(rows, ads=None)` writes a records file of `rows` (listing_id, collected_at, an
    optional last_collected_at and response_id, and the record as a dict) and, given `ads`
    (listing_id and building), an ads file, then appends a clean build's catalog line for them
    and returns it."""
    monkeypatch.setattr(api_records, "DATASETS", tmp_path)

    def write(rows, ads=None):
        texts = [
            json.dumps(
                r["record"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            for r in rows
        ]
        table = pa.table(
            {
                "listing_id": pa.array([r["listing_id"] for r in rows], pa.int64()),
                "collected_at": [float(r["collected_at"]) for r in rows],
                "last_collected_at": [
                    float(r.get("last_collected_at", r["collected_at"])) for r in rows
                ],
                "response_id": pa.array(
                    [r.get("response_id", i) for i, r in enumerate(rows)], pa.int64()
                ),
                "listing_type": ["rental"] * len(rows),
                "record_sha256": [
                    hashlib.sha256(t.encode()).hexdigest() for t in texts
                ],
                "raw_listing_json": texts,
            }
        )
        line = {"built": "2026-10-16T00:00:00+00:00", "code": {"clean": True}}
        files = [("records", "records", table)]
        if ads is not None:
            files.append(("ads_file", "ads", pa.Table.from_pylist(ads)))
        for key, stem, data in files:
            path = tmp_path / f"{stem}-{len(rows)}.parquet"
            pq.write_table(data, path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            line[key] = {"path": path.name, "sha256": digest, "rows": data.num_rows}
        with open(tmp_path / "catalog.ndjson", "a") as f:
            f.write(json.dumps(line) + "\n")
        return line

    return write
