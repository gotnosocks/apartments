import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0income
from rentfrontier.b0data import sha256


@pytest.fixture
def src(tmp_path):
    records = [
        # An HPD lottery the old list misses.
        ("1", 1, "Rent stabilized. HPD income requirements apply: max income $141k."),
        # A fee schedule, flagged by the old list.
        ("2", 1, "Application fee $20, optional for income restricted units."),
        # An older capture flags, the latest does not.
        ("3", 1, "Affordable housing unit through Housing Connect."),
        ("3", 2, "Sunny one bedroom with a dishwasher and laundry."),
        # A market ad's 40x rule and sales copy.
        (
            "5",
            1,
            "Income requirement: 40x rent. This affordable unit is in move-in condition.",
        ),
        # The row has no known description, so it keeps its flag.
        ("4", 1, ""),
    ]
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": [r[0] for r in records],
                "listing_type": ["rental"] * len(records),
                "last_collected_at": [r[1] for r in records],
                "raw_listing_json": [
                    json.dumps({"description": r[2]}) for r in records
                ],
            }
        ),
        path,
    )
    rows = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5"],
            "income_restricted": [False, True, False, True, False],
            "description_known": [True, True, True, False, True],
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


def test_income_uses_the_model_pattern(src, tmp_path):
    before = (src / "rows.parquet").read_bytes()
    out = tmp_path / "out"
    manifest = b0income.income(src, out)
    rows = pd.read_parquet(out / "rows.parquet")
    assert rows.income_restricted.tolist() == [True, False, False, True, False]
    assert manifest["income"] | {"pattern": None} == {
        "source": str(src),
        "source_rows_sha256": "abc",
        "pattern": None,
        "flagged_before": 2,
        "flagged": 2,
        "gained": 1,
        "lost": 1,
    }
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert (src / "rows.parquet").read_bytes() == before
    with pytest.raises(FileExistsError):
        b0income.income(src, out)


def test_income_refuses_a_changed_records_file(src, tmp_path):
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["records"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        b0income.income(src, tmp_path / "out")
