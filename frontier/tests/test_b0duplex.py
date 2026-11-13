import ast
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0duplex
from rentfrontier.b0data import sha256

S7 = (
    Path(__file__).resolve().parents[2]
    / "docs/notes/causal-screens-2026-11-13/s7_text.py"
)

# (listing, collected_at, last_collected_at, description), one record each.
RECORDS = [
    ("1", 1.0, 1.0, "A sunny duplex apartment with a private terrace and two baths"),
    ("2", 1.0, 1.0, "The top floor of a duplex in a two-family house, two bedrooms"),
    ("3", 1.0, 1.0, "Bi-level loft with soaring ceilings in a doorman building"),
    ("4", 1.0, 1.0, "A one bedroom with an internal staircase up to the roof deck"),
    ("5", 1.0, 1.0, "Duplex building, floor-through one bedroom, new kitchen"),
    ("6", 1.0, 1.0, "Duplex, call now"),
    # The later record of listing 7 drops the duplex wording, by last_collected_at.
    ("7", 3.0, 3.0, "A duplex with two full baths and a deck on the upper level"),
    ("7", 2.0, 5.0, "A floor-through one bedroom across from the park, heat included"),
    ("8", 1.0, 1.0, None),
    ("9", 1.0, 1.0, "A duplex penthouse spanning the whole top of the building"),
    ("11", 1.0, None, "Spans two floors, with a washer and dryer in the unit"),
]


@pytest.fixture
def src(tmp_path):
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": [int(r[0]) for r in RECORDS],
                "collected_at": [r[1] for r in RECORDS],
                "last_collected_at": [r[2] for r in RECORDS],
                "raw_listing_json": [
                    json.dumps({} if r[3] is None else {"description": r[3]})
                    for r in RECORDS
                ],
            }
        ),
        path,
        row_group_size=4,
    )
    rows = pd.DataFrame(
        {
            "listing_id": [1, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11],
            "latest_ask": [3000.0 + i for i in range(11)],
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


def test_the_patterns_are_s7s():
    found = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(S7.read_text()).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ("DUP", "DUP_BLD", "STRUCT")
    }
    assert b0duplex.DUP == found["DUP"]
    assert b0duplex.DUP_BUILDING == found["DUP_BLD"]
    assert b0duplex.LEVELS == found["STRUCT"]


def test_duplex_marks_each_rows_listing_from_its_latest_description(src, tmp_path):
    out = tmp_path / "out"
    manifest = b0duplex.duplex(src, out)
    rows = pd.read_parquet(out / "rows.parquet")
    before = pd.read_parquet(src / "rows.parquet")
    pd.testing.assert_frame_equal(rows.drop(columns="duplex"), before)
    assert dict(zip(rows.listing_id, rows.duplex)) == {
        1: True,
        2: False,  # a two-family house
        3: True,  # bi-level
        4: True,  # an internal staircase
        5: False,  # a duplex building
        6: False,  # too short to count as a description
        7: False,  # the later record has no duplex wording
        8: False,  # no description
        10: False,  # no record
        11: True,  # spans two floors, dated by collected_at alone
    }
    assert (out / "set_aside.parquet").exists()
    entry = manifest["duplex"]
    assert entry["source"] == str(src) and entry["source_rows_sha256"] == "abc"
    assert entry["listings_read"] == 9
    assert entry["rows_described"] == 8
    assert entry["rows_marked"] == 5
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    with pytest.raises(FileExistsError):
        b0duplex.duplex(src, out)
