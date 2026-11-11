import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0closing
from rentfrontier.b0data import sha256


def record(changes, on="2024-01-01", off="2024-02-01"):
    return json.dumps(
        {
            "status": "RENTED",
            "onMarketAt": f"{on}T00:00:00Z",
            "offMarketAt": f"{off}T00:00:00Z",
            "pricing": {
                "price": changes[-1][1],
                "priceChanges": [
                    {"changedAt": f"{d}T12:00:00Z", "price": p} for d, p in changes
                ],
            },
        }
    )


@pytest.fixture
def src(tmp_path):
    records = {
        # A raise on the off-market day: v10 keeps the ask before it.
        "1": record([("2024-01-01", 3000), ("2024-01-20", 2900), ("2024-02-01", 3400)]),
        # A cut before the off-market day: both rules keep it.
        "2": record([("2024-01-01", 3000), ("2024-01-25", 2800)]),
        # Priced net of free months, so its ask matches no change.
        "3": record([("2024-01-01", 3000), ("2024-02-01", 3300)]),
        # Changed only on its on-market day, which also is its off-market day.
        "4": record(
            [("2024-03-01", 2000), ("2024-03-01", 2100)], "2024-03-01", "2024-03-01"
        ),
    }
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": list(records),
                "listing_type": ["rental"] * 4,
                "collected_at": [1, 1, 1, 1],
                "raw_listing_json": list(records.values()),
            }
        ),
        path,
    )
    rows = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5"],
            "latest_ask": [3400.0, 2800.0, 2750.0, 2100.0, 1500.0],
            "latest_ask_how": ["latest"] * 5,
        }
    )
    d = tmp_path / "src"
    d.mkdir()
    rows.to_parquet(d / "rows.parquet")
    rows.iloc[:0].to_parquet(d / "set_aside.parquet")
    manifest = {
        "rows_sha256": "abc",
        "build": {"records": {"path": str(path), "sha256": sha256(path)}},
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


def test_closing_reprices_only_off_day_changes(src, tmp_path):
    before = (src / "rows.parquet").read_bytes()
    out = tmp_path / "out"
    manifest = b0closing.closing(src, out)
    rows = pd.read_parquet(out / "rows.parquet")
    assert rows.latest_ask.tolist() == [2900.0, 2800.0, 2750.0, 2100.0, 1500.0]
    assert rows.latest_ask_how.tolist() == [b0closing.HOW] + ["latest"] * 4
    assert manifest["closing"]["changed"] == 1
    assert manifest["closing"]["raised_share"] == 1.0
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert (src / "rows.parquet").read_bytes() == before
    with pytest.raises(FileExistsError):
        b0closing.closing(src, out)


def test_closing_refuses_a_changed_records_file(src, tmp_path):
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["records"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        b0closing.closing(src, tmp_path / "out")
