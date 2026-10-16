import importlib.util
from pathlib import Path

import duckdb


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of test_pipeline.py load the same way.
context = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py")).context

# Releases of the case, published at midnight UTC as the archive gives them. 22v2 has no
# published date, as in the archive.
PUBLISHED = {
    "13v1": "2013-07-31 00:00:00+00",
    "16v2": "2016-11-30 00:00:00+00",
    "22v2": None,
    "26v2": "2026-08-17 00:00:00+00",
}
DEFAULTS = {"INT": 1, "DOUBLE": 1.0, "TEXT": "X", "BOOLEAN": False}


def test_lot_facts_cases(tmp_path, monkeypatch):
    """Lots of the case, with their records in the releases:

    - Lot A is in every release. Its floor count goes from 5 in 13v1 to 6, 7 and 8, and 13v1
      gives a round 1900 for the year 26v2 gives as 1905.
    - Lot B is missing from 13v1.
    - Lot C's building dates from 2015, so 13v1 describes the lot before it.
    - 13v1 leaves out the flood zone flags for every lot. 16v2 has `pfirm15_flag` for lot A and
      leaves it blank for lot C, which 26v2 places in the zone.

    Ads 1 and 2 come before and on the day 13v1 becomes usable, 7 days after it came out, and
    ads 3 and 4 the day before and the day 16v2 does, at midnight UTC. The DuckDB session runs in
    New York time, where ad 4's midnight falls on the day before. Ad 5 comes after 22v2's
    month, and ad 6 after 26v2. Ads 7 to 9 read lots B and C, and ads 10 and 11 have buildings
    without a lot."""
    ctx = context(monkeypatch, tmp_path / "state")
    model = ctx.get_model("buildings.lot_releases")
    types = {c: kind.sql("duckdb") for c, kind in model.columns_to_types.items()}
    types |= {"bbl": "TEXT", "release": "TEXT", "published": "TIMESTAMPTZ"}
    facts = [c for c in types if c not in ("bbl", "release", "published")]
    defaults = {c: DEFAULTS[types[c]] for c in facts}

    def record(lot, release, **values):
        row = {"bbl": lot, "release": release, "published": PUBLISHED[release]}
        return row | defaults | values

    no_flags = {"pfirm15_flag": None, "firm07_flag": None}
    a, b, c = "1000010001", "1000010002", "1000010003"
    records = [
        record(a, "13v1", yearbuilt=1900, numfloors=5.0, **no_flags),
        record(a, "16v2", yearbuilt=1900, numfloors=6.0),
        record(a, "22v2", yearbuilt=1905, numfloors=7.0),
        record(a, "26v2", yearbuilt=1905, numfloors=8.0, pfirm15_flag=None),
        record(b, "16v2", yearbuilt=1950, numfloors=3.0),
        record(b, "26v2", yearbuilt=1950, numfloors=4.0),
        record(c, "13v1", yearbuilt=0, numfloors=2.0, **no_flags),
        record(c, "16v2", yearbuilt=2015, numfloors=11.0, pfirm15_flag=None),
        record(c, "26v2", yearbuilt=2015, numfloors=12.0),
    ]
    lots = [("b1", a), ("b2", b), ("b3", c), ("b4", None)]
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
    ]

    db = duckdb.connect(
        str(tmp_path / "pipeline.duckdb"), config={"TimeZone": "America/New_York"}
    )
    db.execute("CREATE SCHEMA buildings")
    db.execute("CREATE SCHEMA analysis")
    columns = ", ".join(f"{c} {t}" for c, t in types.items())
    db.execute(f"CREATE TABLE buildings.lot_releases ({columns})")
    db.executemany(
        f"INSERT INTO buildings.lot_releases VALUES ({', '.join('?' * len(types))})",
        [[row[c] for c in types] for row in records],
    )
    db.execute(
        "CREATE TABLE buildings.lots (building_id TEXT, bbl TEXT, bin TEXT, link TEXT)"
    )
    db.executemany("INSERT INTO buildings.lots VALUES (?, ?, NULL, NULL)", lots)
    db.execute(
        """CREATE TABLE analysis.candidates
        (listing_id TEXT, building_id TEXT, price_at TIMESTAMPTZ)"""
    )
    db.executemany(
        "INSERT INTO analysis.candidates VALUES (?, ?, (? || ' 00:00:00+00')::TIMESTAMPTZ)",
        ads,
    )
    query = ctx.render("analysis.lot_facts").sql(dialect="duckdb")
    rows = db.execute(
        f"""SELECT listing_id, pluto_release, pluto_fallback, latest_fields, yearbuilt,
        numfloors, pfirm15_flag FROM ({query}) ORDER BY listing_id"""
    ).fetchall()
    flags = ["firm07_flag", "pfirm15_flag"]
    assert rows == [
        ("01", "13v1", None, flags, 1905, 5.0, None),
        ("02", "13v1", None, flags, 1905, 5.0, None),
        ("03", "13v1", None, flags, 1905, 5.0, None),
        ("04", "16v2", None, [], 1905, 6.0, 1),
        ("05", "16v2", None, [], 1905, 6.0, 1),
        ("06", "26v2", None, [], 1905, 8.0, None),
        ("07", "13v1", "lot_missing", None, 1950, 4.0, 1),
        ("08", "13v1", "before_built", None, 2015, 12.0, 1),
        ("09", "16v2", None, [], 2015, 11.0, None),
        ("10", None, None, None, None, None, None),
        ("11", None, None, None, None, None, None),
    ]
