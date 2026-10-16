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

EARLIER = [
    "release",
    "bin_number",
    "job_number",
    "item_number",
    "job_type",
    "c_o_issue_date",
    "pr_dwelling_unit",
]
LATER = [
    "release",
    "bin",
    "job_filing_name",
    "c_of_o_number",
    "job_type",
    "c_of_o_issuance_date",
    "number_of_dwelling_units",
]
LOTS = [
    ("b1", "1000001"),
    ("b2", "1000002"),
    ("b3", "1000003"),
    ("b4", None),
    ("b6", "1000000"),
]
OLD, NEW = "2025-01-01T00:00:00Z", "2026-10-15T20:30:33Z"


def inputs(db, earlier, later, ads=(), columns=(EARLIER, LATER)):
    """Write `earlier` to `city.dob_co` and `later` to `city.dob_now_co`, every value as
    text and each copy published at its release, the buildings of `LOTS` with their BINs to
    `buildings.lots`, and `ads`, each a listing, a building and a first day, to
    `analysis.candidates`."""
    for schema in ("city", "buildings", "analysis"):
        db.execute(f"CREATE SCHEMA {schema}")
    for table, rows, names in zip(("dob_co", "dob_now_co"), (earlier, later), columns):
        listed = ", ".join(f"{c} TEXT" for c in names)
        db.execute(
            f"""CREATE TABLE city.{table}
            ({listed}, published TIMESTAMPTZ, file TEXT, record BIGINT)"""
        )
        if rows:
            marks = ", ".join("?" * len(names))
            db.executemany(
                f"INSERT INTO city.{table} VALUES ({marks}, NULL, 'a.csv', 1)", rows
            )
            db.execute(f"UPDATE city.{table} SET published = release::TIMESTAMPTZ")
    db.execute(
        "CREATE TABLE buildings.lots (building_id TEXT, bbl TEXT, bin TEXT, link TEXT)"
    )
    db.executemany("INSERT INTO buildings.lots VALUES (?, NULL, ?, NULL)", LOTS)
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
    query = ctx.render("analysis.building_certificates").sql(dialect="duckdb")
    db.execute(f"CREATE TABLE analysis.building_certificates AS {query}")


def connect(tmp_path):
    return duckdb.connect(
        str(tmp_path / "pipeline.duckdb"), config={"TimeZone": "America/New_York"}
    )


def test_building_certificates_cases(tmp_path, monkeypatch):
    """BINs of the case, with their certificates in the latest copy of each set:

    - BIN 1000001 got a new building, job 121, with certificates on 2015-08-19 for 10
      apartments, on 2105-11-05, a typo for 2015, and on 2016-02-02 for 12. A major alteration,
      job 122, got a certificate on 2019-05-01 in the earlier set, and a certificate on
      2021-06-10 in each set, for 13 apartments in the earlier set and 14 in DOB NOW. The DOB
      NOW set also renews job 121 on 2021-06-30 without a count. An older copy of the earlier
      set gives the BIN a new building in 2010, which the newer copy leaves out.
    - BIN 1000002 got a new building with existing elements to remain, job B1, in DOB NOW on
      2021-04-08 with `..208` for its count, and a certificate on 2021-12-01 for 22. A
      certificate of the same job has no issue date.
    - BIN 1000003 has no certificate, building b4 has no BIN, and building b6 has BIN 1000000,
      which stands for no numbered building.

    Ads 1 to 3 read BIN 1000001 the day before its first certificate, on its day and after
    the alteration's renewals, ads 4 and 5 read BIN 1000002 on its first day and after its
    second certificate, and ads 6 to 9 read BIN 1000003, building b4, a building missing from
    `buildings.lots` and building b6. The DuckDB session runs in New York time, where an ad's
    first day at midnight UTC falls on the day before."""
    ctx = context(monkeypatch, tmp_path / "state")
    earlier = [
        (NEW, "1000001", "121", "001", "NB", "2015-08-19T00:00:00.000", "10"),
        (NEW, "1000001", "121", "002", "NB", "2105-11-05T00:00:00.000", None),
        (NEW, " 1000001", "121", "003", " NB", "2016-02-02T00:00:00.000", " 12"),
        (NEW, "1000001", "122", "001", "A1", "2019-05-01T00:00:00.000", None),
        (NEW, "1000001", "122", "002", "A1", "2021-06-10T00:00:00.000", "13"),
        (OLD, "1000001", "100", "001", "NB", "2010-01-01T00:00:00.000", "9"),
    ]
    later = [
        (
            NEW,
            "1000001",
            "122",
            "CO-1",
            "ALTERATION TYPE 1",
            "06/10/21  2:44:31 PM",
            "14",
        ),
        (NEW, "1000001", "121", "CO-2", "NEW BUILDING", "06/30/21 11:18:44 AM", None),
        (
            NEW,
            "1000002",
            "B1",
            "CO-3",
            "CO - New Building with Existing Elements to Remain",
            "04/08/21  9:32:24 AM",
            "..208",
        ),
        (NEW, "1000002", "B1", "CO-4", "New Building", "12/01/21 10:00:00 AM", "22"),
        (NEW, "1000002", "B1", "CO-5", "New Building", None, "30"),
    ]
    ads = [
        ("01", "b1", "2015-08-18"),
        ("02", "b1", "2015-08-19"),
        ("03", "b1", "2021-07-01"),
        ("04", "b2", "2021-04-08"),
        ("05", "b2", "2022-01-01"),
        ("06", "b3", "2022-01-01"),
        ("07", "b4", "2022-01-01"),
        ("08", "b5", "2022-01-01"),
        ("09", "b6", "2022-01-01"),
    ]
    db = connect(tmp_path)
    inputs(db, earlier, later, ads=ads)
    build(db, ctx)

    rows = db.execute(
        """SELECT listing_id, bin, first_day, dob_co_release, new_building, altered,
        new_building_since, new_building_job, altered_since, alteration_job, units,
        units_issued, units_source, units_certificate
        FROM analysis.building_certificates ORDER BY listing_id"""
    ).fetchall()
    day = datetime.date
    none = (None,) * 8
    assert rows == [
        ("01", "1000001", day(2015, 8, 18), NEW, False, False, *none),
        (
            "02",
            "1000001",
            day(2015, 8, 19),
            NEW,
            True,
            False,
            day(2015, 8, 19),
            "121",
            None,
            None,
            10,
            day(2015, 8, 19),
            "dob_co",
            "121 item 001",
        ),
        (
            "03",
            "1000001",
            day(2021, 7, 1),
            NEW,
            True,
            True,
            day(2015, 8, 19),
            "121",
            day(2019, 5, 1),
            "122",
            14,
            day(2021, 6, 10),
            "dob_now_co",
            "CO-1",
        ),
        (
            "04",
            "1000002",
            day(2021, 4, 8),
            NEW,
            True,
            False,
            day(2021, 4, 8),
            "B1",
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "05",
            "1000002",
            day(2022, 1, 1),
            NEW,
            True,
            False,
            day(2021, 4, 8),
            "B1",
            None,
            None,
            22,
            day(2021, 12, 1),
            "dob_now_co",
            "CO-4",
        ),
        ("06", "1000003", day(2022, 1, 1), NEW, False, False, *none),
        ("07", None, day(2022, 1, 1), NEW, None, None, *none),
        ("08", None, day(2022, 1, 1), NEW, None, None, *none),
        ("09", None, day(2022, 1, 1), NEW, None, None, *none),
    ]


@pytest.mark.parametrize(
    "earlier, later, message",
    [
        (
            ("1000001", "121", "001", "A2", "2015-08-19T00:00:00.000", "1"),
            None,
            "job type A2 of job 121 in dob_co",
        ),
        (
            ("1000001", "121", "001", "NB", " ", "1"),
            None,
            "no issue date for job 121 in dob_co",
        ),
        (("1000001", "121", "001", "NB", "2015-08-19", "1"), None, "2015-08-19"),
        (
            ("1000001", "121", "001", "NB", "15-08-19T00:00:00.000", "1"),
            None,
            "15-08-19T00:00:00.000",
        ),
        (
            None,
            ("1000001", "121", "CO-1", "ALTERATION", "06/10/21 2:44:31 PM", "1"),
            "job type ALTERATION of job 121 in dob_now_co",
        ),
        (
            None,
            ("1000001", "121", "CO-1", "NEW BUILDING", "2021-06-10T00:00:00.000", "1"),
            "2021-06-10T00:00:00.000",
        ),
        (
            None,
            ("1000001", "121", "CO-1", "NEW BUILDING", "06/10/2021 2:44:31 PM", "1"),
            "06/10/2021 2:44:31 PM",
        ),
    ],
)
def test_building_certificates_stop_on_odd_values(
    tmp_path, monkeypatch, earlier, later, message
):
    """A job type outside the two kinds, a blank issue date in the earlier set and a date in
    another form in either set, a two-digit year in the earlier set and a four-digit one in
    DOB NOW among them, stop the step."""
    ctx = context(monkeypatch, tmp_path / "state")
    db = connect(tmp_path)
    inputs(
        db,
        [(NEW, *earlier)] if earlier else [],
        [(NEW, *later)] if later else [],
    )
    with pytest.raises(duckdb.Error, match=message):
        build(db, ctx)


def test_building_certificates_without_a_copy(tmp_path, monkeypatch):
    """With no copy of the DOB NOW set in the archive, `city.dob_now_co` has only the archive's
    columns, and an ad with a BIN reads both flags as missing but keeps the earlier set's
    certificates."""
    ctx = context(monkeypatch, tmp_path / "state")
    db = connect(tmp_path)
    inputs(
        db,
        [(NEW, "1000001", "121", "001", "NB", "2015-08-19T00:00:00.000", "10")],
        [],
        ads=[("01", "b1", "2020-01-01")],
        columns=(EARLIER, ["release"]),
    )
    build(db, ctx)
    assert db.execute(
        """SELECT bin, dob_now_co_release, new_building, altered, new_building_since, units
        FROM analysis.building_certificates"""
    ).fetchall() == [("1000001", None, None, None, datetime.date(2015, 8, 19), 10)]
