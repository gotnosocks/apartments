import ast
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0penthouse
from rentfrontier.b0data import sha256

S14 = (
    Path(__file__).resolve().parents[2]
    / "docs/notes/unusual-units-2026-11-13/u1_text.py"
)

# Descriptions offering a penthouse.
PENTHOUSES = [
    "A penthouse with a private terrace and two full baths",
    "PENTHOUSE! Two bedrooms with a wraparound terrace",
    "Penthouse apartment on the 20th floor with skyline views",
    "Duplex penthouse spanning the whole top of the building",
    # One exclusion cancels one of the two mentions.
    "A sunny penthouse in a building with a penthouse lounge and gym",
]
# Descriptions naming a penthouse amenity, plural or style, or none at all.
OTHERS = [
    "A one bedroom in a building with a penthouse lounge and gym",
    "Enjoy penthouse-level amenities including a pool and a gym",
    "A fitness center and a lounge are at the penthouse level",
    "The building has three penthouses and a full-time doorman",
    "Residents share a penthouse roof deck with grills and views",
    "A two bedroom with penthouse-style finishes and a dishwasher",
    "Ask about our penthouse residences on the upper floors",
    # A unit label in the text is no mention of the word.
    "One bedroom in unit PH2, on the top floor, with a dishwasher",
]

# (listing, collected_at, last_collected_at, description), one record each.
RECORDS = [
    # Listing 12's newer record and listing 13's older record come in the first row group.
    ("12", 4.0, 4.0, "A penthouse with a roof deck of its own and two baths"),
    ("13", 1.0, 1.0, "A floor-through one bedroom with exposed brick walls"),
    ("1", 1.0, 1.0, "A sunny penthouse with a private terrace and two baths"),
    ("2", 1.0, 1.0, "A two bedroom with access to the penthouse lounge"),
    ("3", 1.0, 1.0, "Penthouse living at its best, with a wraparound terrace"),
    ("4", 1.0, 1.0, "Top floor one bedroom in unit PH, with a skylight"),
    ("5", 1.0, 1.0, "Three penthouses left, with a shared penthouse roof deck"),
    ("6", 1.0, 1.0, "Penthouse, call now"),
    # The later record of listing 7 drops the penthouse wording, by last_collected_at.
    ("7", 3.0, 3.0, "A penthouse with two full baths and a deck up top"),
    ("7", 2.0, 5.0, "A floor-through one bedroom across from the park, heat included"),
    ("8", 1.0, 1.0, None),
    ("9", 1.0, 1.0, "A duplex penthouse spanning the whole top of the building"),
    ("11", 1.0, None, "The penthouse has a washer and dryer in the unit"),
    ("12", 2.0, 2.0, "A one bedroom with a dishwasher and good closets"),
    ("13", 3.0, 3.0, "Penthouse three bedroom, with a garden behind the kitchen"),
    # A record with neither time is no listing's latest.
    ("14", None, None, "A penthouse with two baths and a private terrace out back"),
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
            "listing_id": [1, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14],
            "latest_ask": [3000.0 + i for i in range(14)],
            "duplex": [False] * 13 + [True],
        }
    )
    d = tmp_path / "src"
    d.mkdir()
    rows.to_parquet(d / "rows.parquet")
    rows.iloc[:0].to_parquet(d / "set_aside.parquet")
    manifest = {
        "rows_sha256": "abc",
        "build": {"records": {"path": str(path), "sha256": sha256(path)}},
        "duplex": {"rows_marked": 1},
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


def test_the_patterns_are_s14s():
    found = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(S14.read_text()).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ("PEN", "PEN_EXCL")
    }
    assert b0penthouse.PEN == found["PEN"]
    assert b0penthouse.PEN_EXCL == found["PEN_EXCL"]


def test_marks_count_the_mentions_of_a_penthouse_against_the_exclusions():
    known, pen = b0penthouse.marks(PENTHOUSES + OTHERS)
    assert known.all()
    assert pen.tolist() == [True] * len(PENTHOUSES) + [False] * len(OTHERS)


def test_penthouse_marks_each_rows_listing_from_its_latest_description(src, tmp_path):
    out = tmp_path / "out"
    before = sha256(src / "rows.parquet")
    manifest = b0penthouse.penthouse(src, out)
    assert sha256(src / "rows.parquet") == before
    rows = pd.read_parquet(out / "rows.parquet")
    pd.testing.assert_frame_equal(
        rows.drop(columns="penthouse"), pd.read_parquet(src / "rows.parquet")
    )
    assert dict(zip(rows.listing_id, rows.penthouse)) == {
        1: True,
        2: False,  # a penthouse lounge
        3: True,
        4: False,  # a unit label in the text and the top floor
        5: False,  # a plural and a shared roof deck
        6: False,  # too short to count as a description
        7: False,  # the later record has no penthouse wording
        8: False,  # no description
        10: False,  # no record
        11: True,  # dated by collected_at alone
        12: True,  # its first row group holds its latest record
        13: True,  # its last row group holds its latest record
        14: False,  # its only record has no time
    }
    assert (out / "set_aside.parquet").exists()
    assert manifest["duplex"] == {"rows_marked": 1}
    entry = manifest["penthouse"]
    assert entry["source"] == str(src) and entry["source_rows_sha256"] == "abc"
    assert entry["patterns"] == {
        "pen": b0penthouse.PEN,
        "pen_excl": b0penthouse.PEN_EXCL,
    }
    assert entry["listings_read"] == 11
    assert entry["rows_described"] == 10
    assert entry["rows_marked"] == 6
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert json.loads((out / "manifest.json").read_text()) == manifest
    with pytest.raises(FileExistsError):
        b0penthouse.penthouse(src, out)
