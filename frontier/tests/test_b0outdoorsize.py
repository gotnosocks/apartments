import json
import math

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rentfrontier import b0outdoorsize
from rentfrontier.b0data import sha256

# Paraphrases of the forms in the reads of docs/notes/outdoor-size-2026-11-14.md, with the
# area and code each one gets.
POSITIVE = [
    (
        "Bright one bedroom with a 500 sq ft private terrace and great light.",
        500,
        "number_first",
    ),
    (
        "Enjoy 800 sq. ft. of private outdoor space on the top floor.",
        800,
        "number_first",
    ),
    (
        "Spacious two bedroom with a 300 sf balcony off the living room.",
        300,
        "number_first",
    ),
    (
        "Huge 2,500 square foot private backyard with a grill and plantings.",
        2500,
        "number_first",
    ),
    ("Top floor unit with a 450 sq/ft terrace and city views.", 450, "number_first"),
    (
        "Two bedroom with a 1,200 square-foot wrap-around terrace, washer dryer.",
        1200,
        "number_first",
    ),
    (
        "Corner unit with 95sqft balcony, open kitchen and great closets.",
        95,
        "number_first",
    ),
    (
        "The apartment has a wraparound terrace of approximately 1,200 square feet.",
        1200,
        "noun_first",
    ),
    (
        "Renovated loft with private garden (900 sf) in the back of the house.",
        900,
        "noun_first",
    ),
    (
        "Two bedroom with a private patio measuring 250 sqft, washer dryer in unit.",
        250,
        "noun_first",
    ),
    (
        "Terrace 450 sq ft and interior 930 sq ft, renovated throughout.",
        450,
        "noun_first",
    ),
    (
        "Penthouse with a private 600 sq ft roof deck and skyline views.",
        600,
        "number_first",
    ),
    (
        "Your own roof deck: about 700 sq ft, reached by a staircase inside.",
        700,
        "noun_first",
    ),
    (
        "A private terrace-nearly 800 square feet of open-air living off the den.",
        800,
        "noun_first",
    ),
]
SHARED = [
    "Building amenities include a gym, a lounge and a 3,000 sq ft roof deck.",
    "Enjoy the shared 1,500 sq ft garden behind the building with the others.",
    "The 2,000 sq ft backyard is shared by all tenants of the house.",
    "A common roof deck of 4,000 square feet with grills and seating.",
    "Building features include: | 24-hour concierge | 4,000 sq ft landscaped terrace | gym",
    "Residents enjoy a 5,000 sq ft rooftop with views of the river.",
    "Studio in an elevator building with a 1,000 sq ft roof deck and laundry.",
    "Two bedroom near the park, with access to a large 2,000 sq ft backyard.",
    "Some apartments with 440 to 600 sq ft terraces, ask for details on availability.",
    "Join the club: the building's private restaurant with a 4,000 sqft terrace.",
    "The building’s 2,000 sq ft garden is open to all, steps from the train.",
    "Building features: bike room, 750 sf landscaped yard for meeting your neighbors.",
]
NOT_OUTDOOR = [
    "This 900 sq ft apartment has a balcony and an open kitchen.",
    "Terrace apartment of 1,100 sq ft with lots of light in every room.",
    "Balcony unit, 750 square feet of living space, renovated kitchen.",
    "Private terrace. The lot is 2,500 sq ft and the house has four units.",
    "The garden level apartment of 900 sq ft opens onto the street.",
    "Garden duplex of 1,700 sq ft with two bedrooms and a home office.",
    "Located in Carroll Gardens, this 1,000 sq ft home has three bedrooms.",
    "Large corner condo with balcony boasts over 800 sqft of living space.",
    "Sunny 650 square feet one bedroom with terrace access from the hall.",
    "There is no 300 sq ft balcony here, but the apartment is bright.",
]


@pytest.mark.parametrize("text,sqft,src", POSITIVE)
def test_outdoor_area_reads_private_outdoor_areas(text, sqft, src):
    assert b0outdoorsize.outdoor_area(text) == (sqft, src, 0)


@pytest.mark.parametrize("text", SHARED)
def test_outdoor_area_leaves_shared_and_building_spaces(text):
    sqft, src, _ = b0outdoorsize.outdoor_area(text)
    assert math.isnan(sqft) and src == ""


@pytest.mark.parametrize("text", NOT_OUTDOOR)
def test_outdoor_area_leaves_interior_lot_and_negated_sizes(text):
    sqft, src, _ = b0outdoorsize.outdoor_area(text)
    assert math.isnan(sqft) and src == ""


@pytest.mark.parametrize(
    "text,sqft,src",
    [
        ("Private terrace of 300-400 sq ft with a view of the park.", 350, "range"),
        ("A 400 to 550 sf private roof deck paved in bluestone.", 475, "range"),
        (
            "A 300 sq ft terrace off the living room and a 200 sq ft balcony off the "
            "bedroom.",
            500,
            "sum",
        ),
        (
            "Two terraces, a 500 sq ft terrace and a 400 sq ft terrace, totaling 900 sq "
            "ft of outdoor space.",
            900,
            "total",
        ),
        (
            "1,000 sq ft of private outdoor space, with a 600 sq ft terrace and a garden.",
            1000,
            "total",
        ),
        (
            "Huge 500 sq ft terrace! Bright and quiet. The 500 sq ft terrace faces south.",
            500,
            "number_first",
        ),
    ],
)
def test_outdoor_area_reads_ranges_and_several_areas(text, sqft, src):
    assert b0outdoorsize.outdoor_area(text) == (sqft, src, 0)


@pytest.mark.parametrize(
    "text,dropped",
    [
        ("Private garden of 10,000 sq ft behind the townhouse, with fruit trees.", 1),
        ("A tiny 15 sq ft balcony off the kitchen, room for a few plants.", 1),
        ("A 3,000 sq ft private garden and a 2,500 sq ft private roof terrace.", 0),
    ],
)
def test_outdoor_area_codes_implausible_sizes(text, dropped):
    sqft, src, n = b0outdoorsize.outdoor_area(text)
    assert math.isnan(sqft) and src == "implausible" and n == dropped


@pytest.mark.parametrize("text", [None, "", "Terrace 500sf", 3.0])
def test_outdoor_area_needs_a_description(text):
    sqft, src, n = b0outdoorsize.outdoor_area(text)
    assert math.isnan(sqft) and (src, n) == ("", 0)


def test_areas_gives_the_check_that_drops_each_area():
    low = b0outdoorsize.plain(
        "A 5,000 sq ft rooftop has grills and a lawn. Your apartment has a 300 sq ft "
        "private terrace. The building has a shared 2,000 sq ft garden."
    )
    got = [(a["value"], a["kind"], a["drop"]) for a in b0outdoorsize.areas(low)]
    assert got == [
        (5000, "roof", "roof"),
        (300, "terrace", None),
        (2000, "garden", "shared"),
    ]
    assert {a["drop"] for a in b0outdoorsize.areas(low)} <= {None, *b0outdoorsize.DROPS}


TERRACE = "Bright one bedroom with a 500 sq ft private terrace and great light."
NO_AREA = "Bright one bedroom with a terrace, no fee, steps to the train."
SHARED_ROOF = "Residents enjoy a 5,000 sq ft rooftop with views of the river."
RANGE = "Private terrace of 300-400 sq ft with a view of the park."
HUGE = "Private garden of 10,000 sq ft behind the townhouse, with fruit trees."
SUM = "A 300 sq ft terrace off the living room and a 200 sq ft balcony off the bedroom."

# (listing_id, collected_at, last_collected_at, description), four records per row group.
RECORDS = [
    ("10", 5.0, 5.0, SUM),
    ("1", 1.0, 2.0, TERRACE),
    ("2", 1.0, 1.0, SHARED_ROOF),
    ("3", 1.0, 1.0, "Terrace 500sf"),
    ("4", 1.0, 1.0, TERRACE),
    ("4", 2.0, 3.0, NO_AREA),
    # A record with neither time is no listing's latest.
    ("6", None, None, TERRACE),
    ("5", 1.0, None, RANGE),
    ("7", 1.0, 1.0, HUGE),
    ("8", 1.0, 1.0, None),
    ("10", 1.0, 1.0, TERRACE),
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
    ids = [1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    rows = pd.DataFrame(
        {
            "listing_id": ids,
            "latest_ask": [3000.0 + i for i in range(len(ids))],
            "bedrooms": [1] * len(ids),
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


def test_outdoorsize_adds_both_columns_from_each_listings_latest_description(
    src, tmp_path
):
    out = tmp_path / "out"
    manifest = b0outdoorsize.outdoorsize(src, out)
    rows = pd.read_parquet(out / "rows.parquet")
    before = pd.read_parquet(src / "rows.parquet")
    new = ["outdoor_sqft", "outdoor_sqft_src"]
    pd.testing.assert_frame_equal(rows.drop(columns=new), before)
    got = {
        i: (None if math.isnan(a) else a, b)
        for i, a, b in zip(rows.listing_id, rows.outdoor_sqft, rows.outdoor_sqft_src)
    }
    assert got == {
        1: (500, "number_first"),
        2: (None, ""),  # the building's roof
        3: (None, ""),  # too short to count as a description
        4: (None, ""),  # the later record states no area
        5: (350, "range"),  # dated by collected_at alone
        6: (None, ""),  # its only record has no time
        7: (None, "implausible"),
        8: (None, ""),  # no description
        9: (None, ""),  # no record
        10: (500, "sum"),  # its first row group holds its latest record
    }
    assert rows.outdoor_sqft.dtype == "float64"
    assert (out / "set_aside.parquet").exists()
    entry = manifest["outdoorsize"]
    assert entry["source"] == str(src) and entry["source_rows_sha256"] == "abc"
    assert entry["listings_read"] == 8
    assert entry["rows_described"] == 7
    assert entry["rows_with_area"] == 4
    assert entry["rows_by_code"] == {
        "number_first": 2,
        "noun_first": 0,
        "range": 1,
        "total": 0,
        "sum": 1,
        "implausible": 1,
    }
    assert entry["rows_with_an_area_dropped_as_implausible"] == 1
    assert entry["patterns"]["area"] == b0outdoorsize.AREA.pattern
    assert entry["plausible"] == [20.0, 5000.0]
    assert manifest["rows_sha256"] == sha256(out / "rows.parquet")
    with pytest.raises(FileExistsError):
        b0outdoorsize.outdoorsize(src, out)


def test_outdoorsize_refuses_records_that_do_not_match_the_manifest(src, tmp_path):
    manifest = json.loads((src / "manifest.json").read_text())
    manifest["build"]["records"]["sha256"] = "0" * 64
    (src / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SystemExit):
        b0outdoorsize.outdoorsize(src, tmp_path / "out")
    assert not (tmp_path / "out").exists()
