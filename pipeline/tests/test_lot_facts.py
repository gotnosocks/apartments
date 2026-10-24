import datetime

import duckdb
import pytest

# Releases of the case, published at midnight UTC as the archive gives them. 22v2 has no
# published date, as in the archive.
PUBLISHED = {
    "13v1": "2013-07-31 00:00:00+00",
    "16v2": "2016-11-30 00:00:00+00",
    "19v1": "2019-01-01 00:00:00+00",
    "22v2": None,
    "26v2": "2026-08-17 00:00:00+00",
}
# The text of a fact of each type, for a record giving no other.
DEFAULTS = {"INT": "1", "DOUBLE": "1.0", "TEXT": "X", "BOOLEAN": "N"}
# Columns of `city.pluto` the lot steps leave alone.
OTHERS = ["file", "member", "record", "encoding", "geom"]
A, B, C, D, E = (f"100001000{n}" for n in range(1, 6))


def facts(ctx):
    """The facts `buildings.lot_releases` reads from `city.pluto`, with the type it gives each."""
    model = ctx.get_model("buildings.lot_releases")
    return {
        c: kind.sql("duckdb")
        for c, kind in model.columns_to_types.items()
        if c not in ("bbl", "release", "published")
    }


def inputs(db, ctx, records, lots, ads=(), entries=()):
    """Write `records` to `city.pluto`, every value as text, `lots` to `buildings.lots`, `ads`,
    each a listing, a building and a first day, to `analysis.candidates`, and `entries`, each
    an entry, a listing, a change and a status, to `ledger.status`."""
    kinds = facts(ctx)
    columns = {"bbl": "TEXT", "release": "TEXT", "published": "TIMESTAMPTZ"}
    columns |= {c: "TEXT" for c in [*OTHERS, *kinds]}
    rows = []
    for lot, release, values in records:
        row = {c: DEFAULTS[kind] for c, kind in kinds.items()} | values
        row |= {"bbl": lot, "release": release, "published": PUBLISHED[release]}
        rows.append([row.get(c) for c in columns])
    for schema in ("city", "buildings", "analysis", "ledger"):
        db.execute(f"CREATE SCHEMA {schema}")
    listed = ", ".join(f"{c} {kind}" for c, kind in columns.items())
    db.execute(f"CREATE TABLE city.pluto ({listed})")
    marks = ", ".join("?" * len(columns))
    db.executemany(f"INSERT INTO city.pluto VALUES ({marks})", rows)
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
    db.execute(
        "CREATE TABLE ledger.status (entry TEXT, listing_id TEXT, change TEXT, status TEXT)"
    )
    if entries:
        db.executemany("INSERT INTO ledger.status VALUES (?, ?, ?, ?)", entries)


def build(db, ctx, *names):
    for name in names:
        query = ctx.render(name).sql(dialect="duckdb")
        db.execute(f"CREATE TABLE {name} AS {query}")


def test_lot_facts_cases(tmp_path, render_context):
    """Lots of the case, with their records in the releases:

    - Lot A is in every release. Its floor count goes from 5 in 13v1 to 6, 6.5, 7 and 8, and
      13v1 and 16v2 give a round 1900 for the year 26v2 gives as 1905, with 16v2 writing it as
      1900.00. 13v1 writes its lot number with decimals, its land use code as `01`, its floor
      area ratio as ` 2.50` and its `irrlotcode` as `y`.
    - Lot B is missing from 13v1, and 16v2 leaves its `irrlotcode` blank.
    - Lot C's building dates from 2015, so 13v1 describes the lot before it.
    - Lot D's building dates from 2019, the year 19v1 came out on Jan 1 at midnight UTC.
    - Lot E has no building, so the steps leave it out, but it is the one lot with a
      `firm07_flag` in 19v1.
    - 13v1 leaves out the flood zone flags for every lot. 16v2 has `pfirm15_flag` for lot A and
      leaves it blank for lot C, which 26v2 places in the zone.

    Ads 1 and 2 come before and on the day 13v1 becomes usable, 7 days after it came out, and
    ads 3 and 4 the day before and the day 16v2 does, at midnight UTC. The DuckDB session runs in
    New York time, where ad 4's midnight and 19v1's falls on the day before. Ad 5 comes after
    22v2's month, ad 6 after 26v2, and ad 12 after 19v1. Ads 7 to 9 read lots B and C, and ads
    10 and 11 have buildings without a lot. Ad 13 reads lot B in 16v2. Ad 14 at lot A has a live
    drop_lot in the corrections ledger, so it gets no lot. Ad 15 at lot A has a stale drop_lot
    and a live exclude, so it keeps its lot."""
    ctx = render_context
    no_flags = {"pfirm15_flag": "", "firm07_flag": ""}
    records = [
        (
            "1000010001.00000000",
            "13v1",
            {"yearbuilt": "1900", "numfloors": "5", "landuse": "01"}
            | {"builtfar": " 2.50", "irrlotcode": "y"}
            | no_flags,
        ),
        (A, "16v2", {"yearbuilt": "1900.00", "numfloors": "6", "bldgclass": ""}),
        (A, "19v1", {"yearbuilt": "1905", "numfloors": "6.5", "firm07_flag": ""}),
        (A, "22v2", {"yearbuilt": "1905", "numfloors": "7"}),
        (A, "26v2", {"yearbuilt": "1905", "numfloors": "8", "pfirm15_flag": ""}),
        (B, "16v2", {"yearbuilt": "1950", "numfloors": "3", "irrlotcode": ""}),
        (B, "26v2", {"yearbuilt": "1950", "numfloors": "4", "irrlotcode": " N"}),
        (C, "13v1", {"yearbuilt": "0", "numfloors": "2"} | no_flags),
        (C, "16v2", {"yearbuilt": "2015", "numfloors": "11", "pfirm15_flag": ""}),
        (C, "26v2", {"yearbuilt": "2015", "numfloors": "12"}),
        (D, "19v1", {"yearbuilt": "2019", "numfloors": "3", "firm07_flag": ""}),
        (D, "26v2", {"yearbuilt": "2019", "numfloors": "4"}),
        (E, "19v1", {"firm07_flag": "1"}),
    ]
    lots = [("b1", A), ("b2", B), ("b3", C), ("b4", None), ("b6", D)]
    ads = [
        ("01", "b1", "2013-08-06"),
        ("02", "b1", "2013-08-07"),
        ("03", "b1", "2016-12-06"),
        ("04", "b1", "2016-12-07"),
        ("05", "b1", "2023-01-01"),
        ("06", "b1", "2026-09-01"),
        ("07", "b2", "2014-01-01"),
        ("08", "b3", "2014-01-01"),
        ("09", "b3", "2017-01-01"),
        ("10", "b4", "2017-01-01"),
        ("11", "b5", "2017-01-01"),
        ("12", "b6", "2019-02-01"),
        ("13", "b2", "2017-01-01"),
        ("14", "b1", "2026-09-01"),
        ("15", "b1", "2026-09-01"),
    ]
    entries = [
        ("e1", "14", "drop_lot", "live"),
        ("e2", "15", "drop_lot", "stale"),
        ("e3", "15", "exclude", "live"),
    ]
    db = duckdb.connect(
        str(tmp_path / "pipeline.duckdb"), config={"TimeZone": "America/New_York"}
    )
    inputs(db, ctx, records, lots, ads, entries)
    build(
        db, ctx, "city.pluto_releases", "buildings.lot_releases", "analysis.lot_facts"
    )

    assert db.execute(
        """SELECT release, usable_from, pfirm15_flag, firm07_flag
        FROM city.pluto_releases ORDER BY release"""
    ).fetchall() == [
        ("13v1", datetime.date(2013, 8, 7), False, False),
        ("16v2", datetime.date(2016, 12, 7), True, True),
        ("19v1", datetime.date(2019, 1, 8), True, True),
        ("22v2", None, True, True),
        ("26v2", datetime.date(2026, 8, 24), True, True),
    ]
    assert db.execute(
        """SELECT release, yearbuilt, landuse, builtfar, irrlotcode, bldgclass
        FROM buildings.lot_releases WHERE bbl = ? ORDER BY release""",
        [A],
    ).fetchall() == [
        ("13v1", 1900, 1, 2.5, True, "X"),
        ("16v2", 1900, 1, 1.0, False, None),
        ("19v1", 1905, 1, 1.0, False, "X"),
        ("22v2", 1905, 1, 1.0, False, "X"),
        ("26v2", 1905, 1, 1.0, False, "X"),
    ]
    assert db.execute(
        "SELECT DISTINCT bbl FROM buildings.lot_releases ORDER BY bbl"
    ).fetchall() == [(A,), (B,), (C,), (D,)]

    rows = db.execute(
        """SELECT listing_id, pluto_release, pluto_fallback, latest_fields, yearbuilt,
        numfloors, pfirm15_flag, firm07_flag FROM analysis.lot_facts ORDER BY listing_id"""
    ).fetchall()
    flags = ["firm07_flag", "pfirm15_flag"]
    none = (None,) * 7
    assert rows == [
        ("01", "13v1", None, flags, 1905, 5.0, None, 1),
        ("02", "13v1", None, flags, 1905, 5.0, None, 1),
        ("03", "13v1", None, flags, 1905, 5.0, None, 1),
        ("04", "16v2", None, [], 1905, 6.0, 1, 1),
        ("05", "19v1", None, [], 1905, 6.5, 1, None),
        ("06", "26v2", None, [], 1905, 8.0, None, 1),
        ("07", "13v1", "lot_missing", None, 1950, 4.0, 1, 1),
        ("08", "13v1", "before_built", None, 2015, 12.0, 1, 1),
        ("09", "16v2", None, [], 2015, 11.0, None, 1),
        ("10", *none),
        ("11", *none),
        ("12", "19v1", None, [], 2019, 3.0, 1, None),
        ("13", "16v2", None, [], 1950, 3.0, 1, 1),
        ("14", *none),
        ("15", "26v2", None, [], 1905, 8.0, None, 1),
    ]
    assert db.execute(
        """SELECT listing_id, bbl, lot_entry FROM analysis.lot_facts
        WHERE listing_id IN ('06', '14', '15') ORDER BY listing_id"""
    ).fetchall() == [("06", A, None), ("14", None, "e1"), ("15", A, None)]
    # A blank `irrlotcode` in a release carrying the field stays missing.
    assert db.execute(
        """SELECT listing_id, irrlotcode FROM analysis.lot_facts
        WHERE building_id = 'b2' ORDER BY listing_id"""
    ).fetchall() == [("07", False), ("13", None)]


@pytest.mark.parametrize(
    "field, text, message",
    [
        ("numfloors", "5 floors", "5 floors"),
        ("yearbuilt", "1900.5", "fraction 1900.5 on lot 1000010001 in 13v1"),
        ("irrlotcode", "X", "irrlotcode X on lot 1000010001 in 13v1"),
    ],
)
def test_lot_releases_stops_on_odd_values(
    tmp_path, render_context, field, text, message
):
    """A record with a value `buildings.lot_releases` can't read stops the build."""
    ctx = render_context
    db = duckdb.connect(str(tmp_path / "pipeline.duckdb"))
    inputs(db, ctx, [(A, "13v1", {field: text})], [("b1", A)])
    with pytest.raises(duckdb.Error, match=message):
        build(db, ctx, "buildings.lot_releases")
