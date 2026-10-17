import duckdb

# The building record of every case: its class, year, floor count and count of apartments.
RECORD = ("C1", 1920, 5.0, 10)


def lot(bbl, units, fit):
    """MapPLUTO's record of `bbl` in release 26v2, with `units` as its text for `unitsres`. The
    record shares the first `fit` of the building record's other facts and differs in the rest."""
    shared = ["C1", "1920", "5"][:fit]
    other = ["D7", "1960", "12"][fit:]
    return (bbl, "26v2", "2026-08-17 00:00:00+00", *shared, *other, units)


def test_lot_link_cases(tmp_path, render_context):
    """Each building gets a lot from its address and a different lot from its footprint:

    - b1: the address's lot has 5 apartments, the footprint's lot 0 and a better fit, so the
      step takes the address's lot.
    - b2: the address's lot has 0 and the better fit, the footprint's lot 3, so the step takes
      the footprint's lot and its BIN.
    - b3: MapPLUTO gives the address's lot no count, so the facts decide, and the address's lot
      fits better.
    - b4: the address's lot is missing from MapPLUTO, and the footprint's lot has 4 apartments
      and shares a fact, so the facts decide for the footprint's lot.
    - b5: both lots have 0, and the footprint's lot fits better.
    - b6: both lots have apartments, and they fit equally well, so the step takes the
      address's lot.
    """
    db = duckdb.connect(str(tmp_path / "pipeline.duckdb"))
    for schema in ("city", "buildings"):
        db.execute(f"CREATE SCHEMA {schema}")
    db.execute(
        """CREATE TABLE city.pluto (bbl TEXT, release TEXT, published TIMESTAMPTZ,
        bldgclass TEXT, yearbuilt TEXT, numfloors TEXT, unitsres TEXT)"""
    )
    db.executemany(
        "INSERT INTO city.pluto VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            lot("1000010001", "5", 0),
            lot("1000010002", "0", 3),
            lot("1000020001", "0", 3),
            lot("1000020002", "3", 0),
            lot("1000030001", "", 3),
            lot("1000030002", "4", 0),
            lot("1000040002", "4", 1),
            lot("1000050001", "0", 1),
            lot("1000050002", "0", 2),
            lot("1000060001", "5", 2),
            lot("1000060002", "3", 2),
        ],
    )
    buildings = [f"b{n}" for n in range(1, 7)]
    db.execute(
        """CREATE TABLE buildings.latest_record (building_id TEXT, building_class TEXT,
        year_built INT, floor_count DOUBLE, residential_units INT)"""
    )
    db.executemany(
        "INSERT INTO buildings.latest_record VALUES (?, ?, ?, ?, ?)",
        [(b, *RECORD) for b in buildings],
    )
    db.execute(
        """CREATE TABLE buildings.pad_link
        (building_id TEXT, bbl TEXT, bin TEXT, rank INT, lots BIGINT)"""
    )
    db.executemany(
        "INSERT INTO buildings.pad_link VALUES (?, ?, ?, 1, 1)",
        [(f"b{n}", f"10000{n}0001", f"100{n}001") for n in range(1, 7)],
    )
    db.execute(
        """CREATE TABLE buildings.footprint_link
        (building_id TEXT, bbl TEXT, bin TEXT, inside BOOLEAN, metres DOUBLE)"""
    )
    db.executemany(
        "INSERT INTO buildings.footprint_link VALUES (?, ?, ?, true, 0)",
        [(f"b{n}", f"10000{n}0002", f"100{n}002") for n in range(1, 7)],
    )
    query = render_context.render("buildings.lots").sql(dialect="duckdb")
    db.execute(f"CREATE TABLE buildings.lots AS {query}")
    rows = db.sql(
        """SELECT building_id, link, bbl, bin, address_fit, footprint_fit
        FROM buildings.lots ORDER BY building_id"""
    ).fetchall()
    assert rows == [
        ("b1", "address_apartments", "1000010001", "1001001", 0, 3),
        ("b2", "footprint_apartments", "1000020002", "1002002", 3, 0),
        ("b3", "address", "1000030001", "1003001", 3, 0),
        ("b4", "footprint", "1000040002", "1004002", 0, 1),
        ("b5", "footprint", "1000050002", "1005002", 1, 2),
        ("b6", "tie", "1000060001", "1006001", 2, 2),
    ]
