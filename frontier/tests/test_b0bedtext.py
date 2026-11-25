import json
import math

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0bedtext
from rentfrontier.b0data import sha256

# Paraphrases of forms in the reads of docs/notes/bed-text-2026-11-16.md. Each has the coded
# bedroom count of its row and the flag it gets, or None for no flag.
FLEX_AT = [
    ("Massive flex 2 bedroom with a king-sized living room and great closets.", 2),
    ("Sunny junior 1 bedroom on a quiet block, steps from the train.", 1),
    ("This convertible 3 has a renovated kitchen and two full baths.", 3),
    ("Large one bedroom, easily converted to a 2 bedroom with a pressurized wall.", 2),
    ("Junior 4 with a dining alcove and a doorman, laundry in the building.", 2),
    ("Alcove studio with a separate kitchen and a wall of closets.", 1),
]
FEWER = [
    ("Spacious studio duplex with a sleeping loft and a private garden.", 1, 0),
    ("Renovated studio apartment with high ceilings and an open kitchen.", 1, 0),
    ("Bright 1 bed + home office in a doorman building near the park.", 2, 1),
    ("Spacious one-bedroom apartment with a king-sized bed and a home office.", 2, 1),
]
NO_FLAG = [
    # The text agrees with the coded count.
    ("Bright true 2 bedroom in an elevator building with laundry.", 2),
    # Flex wording for a count above the coded one.
    ("Flex 3 bedroom with two baths and a dishwasher, near the subway.", 2),
    ("Junior 4 with a dining alcove and a doorman, laundry in the building.", 1),
    # A studio among the amenities, or a firm.
    ("The building has a wellbeats studio, a roof deck and a doorman.", 1),
    ("Amenities include a yoga studio, a gym and a children's playroom.", 1),
    # A room of the unit.
    (
        "Two bedroom apartment. One bedroom has a king bed, the second bedroom fits a queen.",
        2,
    ),
    # Sizes of several units.
    ("Studios, 1 and 2 bedrooms are available in this new building.", 1),
    ("1, 2 and 3 bedroom homes with condo finishes and river views.", 2),
    ("Beautiful two bedroom. We also have 1 bedroom apartments available here.", 2),
]


def _code(text, bedrooms):
    return b0bedtext.code(*b0bedtext.read(text), bedrooms)


@pytest.mark.parametrize("text,bedrooms", FLEX_AT)
def test_flex_wording_at_the_coded_count(text, bedrooms):
    got = _code(text, bedrooms)
    assert got["bed_flex_at"]
    assert not got["bed_text_fewer"] and not got["bed_text_more"]


@pytest.mark.parametrize("text,bedrooms,stated", FEWER)
def test_text_states_fewer_bedrooms_than_coded(text, bedrooms, stated):
    got = _code(text, bedrooms)
    assert got["bed_text_fewer"] and got["bed_text"] == stated
    assert not got["bed_flex_at"] and not got["bed_text_more"]


@pytest.mark.parametrize("text,bedrooms", NO_FLAG)
def test_no_flag(text, bedrooms):
    got = _code(text, bedrooms)
    assert not (got["bed_flex_at"] or got["bed_text_fewer"] or got["bed_text_more"])


def test_text_states_more_bedrooms_than_coded():
    got = _code("Stunning three bedroom, two bath home with a washer and dryer.", 2)
    assert got["bed_text_more"] and got["bed_text"] == 3
    # With flex wording the larger count is no plain statement of size.
    got = _code("Stunning three bedroom home, or use the flex wall for a den.", 2)
    assert not got["bed_text_more"]


@pytest.mark.parametrize("text", [None, "", "Studio, 1 bath", 3.0])
def test_read_needs_a_description(text):
    assert b0bedtext.read(text) == ([], [], False)


def test_code_gives_no_stated_size_without_a_coded_count():
    got = _code("A real one bedroom with a renovated kitchen and bath.", math.nan)
    assert math.isnan(got["bed_text"]) and not any(
        got[c] for c in b0bedtext.COLUMNS[1:]
    )


def test_code_keeps_the_stated_size_nearest_the_coded_count():
    assert b0bedtext.code([0, 1], [], False, 3)["bed_text"] == 1
    assert b0bedtext.code([3, 4], [], False, 2)["bed_text"] == 3
    assert math.isnan(b0bedtext.code([1, 3], [], False, 2)["bed_text"])


# listing_id, collected_at, last_collected_at, description
RECORDS = [
    (1, "2026-01-01", None, "Renovated studio apartment with high ceilings and light."),
    (1, "2026-03-01", None, "Massive flex 2 bedroom with a king-sized living room."),
    (
        2,
        "2026-01-01",
        "2026-04-01",
        "Spacious studio duplex with a sleeping loft upstairs.",
    ),
    (2, "2026-02-01", None, "Bright true 2 bedroom in an elevator building."),
    (3, "2026-01-01", None, "Stunning three bedroom, two bath home with a washer."),
    (4, "2026-01-01", None, None),
    (5, "2026-01-01", None, "Bright true 2 bedroom in an elevator building."),
]


@pytest.fixture
def src(tmp_path):
    path = tmp_path / "records.parquet"
    pq.write_table(
        pa.table(
            {
                "listing_id": [r[0] for r in RECORDS],
                "collected_at": [r[1] for r in RECORDS],
                "last_collected_at": [r[2] for r in RECORDS],
                "raw_listing_json": [
                    json.dumps({} if r[3] is None else {"description": r[3]})
                    for r in RECORDS
                ],
            }
        ),
        path,
        row_group_size=3,
    )
    ids = [1, 1, 2, 3, 4, 5, 6]
    rows = pd.DataFrame(
        {
            "listing_id": ids,
            "latest_ask": [3000.0 + i for i in range(len(ids))],
            "bedrooms": [2, 2, 2, 2, 2, 2, 2],
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


def test_bedtext_adds_the_columns_from_each_listings_latest_description(src, tmp_path):
    out = tmp_path / "out"
    manifest = b0bedtext.bedtext(src, out)
    before = pd.read_parquet(src / "rows.parquet")
    after = pd.read_parquet(out / "rows.parquet")
    pd.testing.assert_frame_equal(after[before.columns], before)
    assert list(after.columns) == [*before.columns, *b0bedtext.COLUMNS]
    # Listing 1's later record is the flex 2; listing 2's later time is on its first record.
    assert after.bed_flex_at.tolist() == [True, True, False, False, False, False, False]
    assert after.bed_text_fewer.tolist() == [
        False,
        False,
        True,
        False,
        False,
        False,
        False,
    ]
    assert after.bed_text_more.tolist() == [
        False,
        False,
        False,
        True,
        False,
        False,
        False,
    ]
    stated = after.bed_text.tolist()
    assert stated[2:4] == [0.0, 3.0] and stated[5] == 2.0
    assert all(math.isnan(stated[i]) for i in (0, 1, 4, 6))
    assert (out / "set_aside.parquet").exists()
    note = manifest["bedtext"]
    assert note["source_rows_sha256"] == "abc"
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    assert note["listings_read"] == 5
    assert note["rows_flex_or_fewer"] == 3
    assert note["rows_by_flag"] == {
        "bed_text_fewer": 1,
        "bed_text_more": 1,
        "bed_flex_at": 2,
    }


def test_bedtext_refuses_records_that_do_not_match_the_manifest(src, tmp_path):
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["records"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        b0bedtext.bedtext(src, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_flex_wording_for_two_counts_flags_either():
    got = _code("Flex 2 bedroom now, and the layout works as a convertible 3 too.", 2)
    assert got["bed_flex_at"]


@pytest.mark.parametrize(
    "text",
    [
        "Converted 2 family townhouse with 3 bedrooms and a private yard.",
        "Newly converted 6 unit building with a virtual doorman and laundry.",
    ],
)
def test_a_converted_building_is_no_flex_wording(text):
    assert b0bedtext.read(text)[1] == []


def test_b0bedtext_fixes_2026_11_24():
    # 1. Ordinal flex wording ("flexible 5th bedroom", "flex 2nd bedroom").
    got = _code("5 Bedrooms (flexible 5th bedroom) with terrace and laundry.", 5)
    assert got["bed_flex_at"]
    got2 = _code("Spacious layout with convertible 3rd bedroom and two baths.", 3)
    assert got2["bed_flex_at"]

    # 2. "the size of a ... studio" must not be misread as a studio unit.
    got3 = _code(
        "Living room is the size of a large studio apartment with skyline views.", 2
    )
    assert not got3["bed_text_fewer"] and math.isnan(got3["bed_text"])

    # 3. "wellbeats studio" amenity must not trigger studio even with STUDIO_AFTER words.
    got4 = _code("Enjoy the wellbeats studio available on the amenity floor.", 1)
    assert not got4["bed_text_fewer"] and math.isnan(got4["bed_text"])

    # 4. Opening line unit size stands when a later sentence lists building inventory.
    got5 = _code(
        "Gorgeous 1 Bed + Home office with private terrace.\n"
        "The building offers studio, one-, two-, and three-bedroom residences.",
        2,
    )
    assert got5["bed_text_fewer"] and got5["bed_text"] == 1.0
