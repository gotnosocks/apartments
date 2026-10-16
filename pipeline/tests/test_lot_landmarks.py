import datetime
import importlib.util
from pathlib import Path

import duckdb
import pytest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of test_pipeline.py load the same way.
context = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py")).context

COLUMNS = ["release", "bbl", "lp_number", "lm_type", "desdate", "status"]
A, B, C, D, E = (f"100001000{n}" for n in range(1, 6))
LOTS = [("b1", A), ("b2", B), ("b3", C), ("b4", None), ("b6", D), ("b7", E)]


def inputs(db, designations, lots=LOTS, ads=(), columns=COLUMNS):
    """Write `designations` to `city.landmarks`, every value as text and each copy published
    at its release, `lots` to `buildings.lots`, and `ads`, each a listing, a building and a
    first day, to `analysis.candidates`."""
    for schema in ("city", "buildings", "analysis"):
        db.execute(f"CREATE SCHEMA {schema}")
    listed = ", ".join(f"{c} TEXT" for c in columns)
    db.execute(
        f"""CREATE TABLE city.landmarks
        ({listed}, published TIMESTAMPTZ, file TEXT, record BIGINT)"""
    )
    if designations:
        marks = ", ".join("?" * len(columns))
        db.executemany(
            f"INSERT INTO city.landmarks VALUES ({marks}, NULL, 'a.csv', 1)",
            designations,
        )
        db.execute("UPDATE city.landmarks SET published = release::TIMESTAMPTZ")
    db.execute(
        "CREATE TABLE buildings.lots (building_id TEXT, bbl TEXT, bin TEXT, link TEXT)"
    )
    db.executemany("INSERT INTO buildings.lots VALUES (?, ?, NULL, NULL)", lots)
    db.execute(
        """CREATE TABLE analysis.candidates
        (listing_id TEXT, building_id TEXT, price_at TIMESTAMPTZ)"""
    )
    if ads:
        db.executemany(
            "INSERT INTO analysis.candidates VALUES (?, ?, (? || ' 00:00:00+00')::TIMESTAMPTZ)",
            ads,
        )


def build(db, ctx):
    query = ctx.render("analysis.lot_landmarks").sql(dialect="duckdb")
    db.execute(f"CREATE TABLE analysis.lot_landmarks AS {query}")


def connect(tmp_path):
    return duckdb.connect(
        str(tmp_path / "pipeline.duckdb"), config={"TimeZone": "America/New_York"}
    )


def test_lot_landmarks_cases(tmp_path, monkeypatch):
    """Lots of the case, with their designations in the copy of 2026-06-18:

    - Lot A became an individual landmark twice on 1989-07-11, as LP-00150 and LP-00100, an
      interior landmark on 1995-01-05 and part of a historic district on 1990-03-01. The copy
      pads the first date with spaces and the type of the interior landmark too. An older copy
      gives it a landmark from 1900, which the newer copy leaves out.
    - Lot B joined a historic district on 2015-12-31, and the LPC calendared it as a landmark
      in 2000 without designating it.
    - Lot C has no designation, and building b4 has no lot.
    - Lot D has only a scenic landmark, and lot E only an interior landmark.

    Ads 1 to 3 read lot A the day before its landmarks, on their day and after its district,
    ads 4 and 5 read lot B the day before and the day of its district, ads 6 to 8 read lot C,
    building b4 and a building missing from `buildings.lots`, and ads 9 and 10 read lots D and
    E. The DuckDB session runs in New York time, where an ad's first day at midnight UTC falls
    on the day before."""
    ctx = context(monkeypatch, tmp_path / "state")
    new, old = "2026-06-18T14:42:53Z", "2025-01-01T00:00:00Z"
    designations = [
        (new, A, "LP-00150", "Individual Landmark", " 7/11/1989 ", "DESIGNATED"),
        (new, A, "LP-00100", "Individual Landmark", "7/11/1989", "DESIGNATED"),
        (new, A, "LP-00200", " Interior Landmark", "1/5/1995", "DESIGNATED"),
        (new, A, "LP-00300", "Historic District", "3/1/1990", "DESIGNATED"),
        (new, B, "LP-00400", "Historic District", "12/31/2015", "DESIGNATED"),
        (new, B, "LP-00500", "Individual Landmark", "1/1/2000", "CALENDARED"),
        (old, A, "LP-00001", "Individual Landmark", "1/1/1900", "DESIGNATED"),
        (new, D, "LP-00600", "Scenic Landmark", "6/1/2001", "DESIGNATED"),
        (new, E, "LP-00700", "Interior Landmark", "6/2/2001", "DESIGNATED"),
    ]
    ads = [
        ("01", "b1", "1989-07-10"),
        ("02", "b1", "1989-07-11"),
        ("03", "b1", "1996-01-01"),
        ("04", "b2", "2015-12-30"),
        ("05", "b2", "2015-12-31"),
        ("06", "b3", "2020-01-01"),
        ("07", "b4", "2020-01-01"),
        ("08", "b5", "2020-01-01"),
        ("09", "b6", "2020-01-01"),
        ("10", "b7", "2020-01-01"),
    ]
    db = connect(tmp_path)
    inputs(db, designations, ads=ads)
    build(db, ctx)

    rows = db.execute(
        """SELECT listing_id, bbl, first_day, landmarks_release, landmark, historic_district,
        landmark_since, landmark_lp, district_since, district_lp
        FROM analysis.lot_landmarks ORDER BY listing_id"""
    ).fetchall()
    day = datetime.date
    none = (None,) * 4
    assert rows == [
        ("01", A, day(1989, 7, 10), new, False, False, *none),
        (
            "02",
            A,
            day(1989, 7, 11),
            new,
            True,
            False,
            day(1989, 7, 11),
            "LP-00100",
            None,
            None,
        ),
        (
            "03",
            A,
            day(1996, 1, 1),
            new,
            True,
            True,
            day(1989, 7, 11),
            "LP-00100",
            day(1990, 3, 1),
            "LP-00300",
        ),
        ("04", B, day(2015, 12, 30), new, False, False, *none),
        (
            "05",
            B,
            day(2015, 12, 31),
            new,
            False,
            True,
            None,
            None,
            day(2015, 12, 31),
            "LP-00400",
        ),
        ("06", C, day(2020, 1, 1), new, False, False, *none),
        ("07", None, day(2020, 1, 1), new, None, None, *none),
        ("08", None, day(2020, 1, 1), new, None, None, *none),
        (
            "09",
            D,
            day(2020, 1, 1),
            new,
            True,
            False,
            day(2001, 6, 1),
            "LP-00600",
            None,
            None,
        ),
        (
            "10",
            E,
            day(2020, 1, 1),
            new,
            True,
            False,
            day(2001, 6, 2),
            "LP-00700",
            None,
            None,
        ),
    ]


@pytest.mark.parametrize(
    "row, message",
    [
        ((A, "LP-00100", "Landmark", "7/11/1989"), "lm_type Landmark of LP-00100"),
        (
            (A, "LP-00100", "Individual Landmark", " "),
            "no designation date for LP-00100",
        ),
        ((A, "LP-00100", "Individual Landmark", "1989-07-11"), "1989-07-11"),
        ((A, "LP-00100", "Individual Landmark", "7/11/89"), "7/11/89"),
    ],
)
def test_lot_landmarks_stops_on_odd_values(tmp_path, monkeypatch, row, message):
    """A type outside the four, a blank date, a date in another form and a two-digit year
    stop the step."""
    ctx = context(monkeypatch, tmp_path / "state")
    db = connect(tmp_path)
    inputs(db, [("2026-06-18T14:42:53Z", *row, "DESIGNATED")])
    with pytest.raises(duckdb.Error, match=message):
        build(db, ctx)


def test_lot_landmarks_without_a_copy(tmp_path, monkeypatch):
    """With no copy in the archive, `city.landmarks` has only the archive's columns, and an ad
    with a lot reads both flags as missing."""
    ctx = context(monkeypatch, tmp_path / "state")
    db = connect(tmp_path)
    inputs(db, [], ads=[("01", "b1", "2020-01-01")], columns=["release"])
    build(db, ctx)
    assert db.execute(
        "SELECT bbl, landmarks_release, landmark, historic_district FROM analysis.lot_landmarks"
    ).fetchall() == [(A, None, None, None)]
