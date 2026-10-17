import importlib.util
from pathlib import Path

import duckdb

MODELS = Path(__file__).parent.parent / "models"
A, B = "1000010001", "1000020001"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


links = load("relist_links", MODELS / "analysis" / "relist_links.py")


class Fetcher:
    """Stands in for a SQLMesh context: it runs a Python model's queries on `db`, with each
    model's table under its own name."""

    def __init__(self, db):
        self.db = db

    def resolve_table(self, name):
        return name

    def fetchdf(self, query):
        return self.db.sql(query).df()


def test_link_overlap():
    """Pages u1 and u2 overlap by 7 days and join, and the same pair again finds them joined.
    u3 overlaps u2 by 8 days and stays apart, though u1 alone would let it join."""
    spans = {"u1": [(0, 30)], "u2": [(23, 60)], "u3": [(52, 90)]}
    outcomes, find = links.link([("u1", "u2"), ("u2", "u1"), ("u1", "u3")], spans)
    assert outcomes == ["joined", "same", "clash"]
    assert [find(u) for u in ("u1", "u2", "u3")] == ["u1", "u1", "u3"]


def test_relist_cases(tmp_path, render_context):
    """Lot A has apartments for 3 and 7 unit pages with ads in the 12 months to Oct 10, so the
    step looks for relists in it. Its ads, by unit page:

    - u1: ad 1, 2 bedrooms on the 3rd floor at $3,000, from Jan 1 to Mar 1.
    - u2: ad 2, from 4 days after ad 1 ends, at a first ask of $3,050, sharing photo k1 with
      ad 1. It pairs with ad 1.
    - u3: ad 3, a day closer than ad 2 and sharing k1, on the 4th floor.
    - u4: ad 4, sharing only k2, which an ad of lot B shows too.
    - u5: ad 5, sharing k3 but starting 10 days after ad 1 ends.
    - u6: ad 6, sharing k4 but asking $3,200.
    - u7: ad 7, 3 days after ad 2 ends and sharing k7 with it, so it pairs with ad 2. Its ad 8,
      a 3-bedroom, was on the market with ad 1 for 41 days.

    The pair of ads 2 and 7 comes first, being closer in time, and joins u2 and u7. Ad 8 then
    clashes with ad 1, so u1 stays apart. Lot B has apartments for 2, and only 2 of its unit
    pages had ads in the 12 months, so its ads 11 and 12 make no pair. Photo k8 appears on ad
    1 alone.
    """
    db = duckdb.connect(str(tmp_path / "pipeline.duckdb"))
    for schema in ("ads", "analysis", "buildings", "city"):
        db.execute(f"CREATE SCHEMA {schema}")
    # listing, unit page, lot, bedrooms, listed floor, on, off, first and latest ask
    ads = [
        ("1", "u1", A, 2, 3, "2026-01-01", "2026-03-01", 3000),
        ("2", "u2", A, 2, None, "2026-03-05", "2026-04-28", 3050),
        ("3", "u3", A, 2, 4, "2026-03-03", None, 3000),
        ("4", "u4", A, 2, None, "2026-03-02", None, 3000),
        ("5", "u5", A, 2, None, "2026-03-11", None, 3000),
        ("6", "u6", A, 2, None, "2026-03-02", None, 3200),
        ("7", "u7", A, 2, None, "2026-05-01", None, 3050),
        ("8", "u7", A, 3, None, "2026-01-10", "2026-02-20", 4000),
        ("11", "v1", B, 1, None, "2026-02-01", "2026-03-01", 2500),
        ("12", "v2", B, 1, None, "2026-03-03", None, 2500),
        ("13", "v3", B, 1, None, "2024-01-01", "2024-06-01", 2400),
    ]
    photos = {
        "k1": ["1", "2", "3"],
        "k2": ["1", "4", "11"],
        "k3": ["1", "5"],
        "k4": ["1", "6"],
        "k7": ["2", "7"],
        "k5": ["11", "12"],
        "k8": ["1"],
    }
    db.execute(
        "CREATE TABLE ads.market (listing_id TEXT, as_of DATE, on_day DATE, off_day DATE)"
    )
    db.execute("CREATE TABLE ads.placed (listing_id TEXT, unit_id TEXT, building_id TEXT)")
    db.execute("CREATE TABLE ads.photos (listing_id TEXT, key TEXT)")
    db.execute("CREATE TABLE ads.reported (listing_id TEXT, label_floor INTEGER)")
    db.execute(
        """CREATE TABLE analysis.kept (listing_id TEXT, unit_id TEXT, building_id TEXT,
        bedrooms DOUBLE, bathrooms DOUBLE, listed_floor DOUBLE, advertised_floor DOUBLE)"""
    )
    db.execute(
        "CREATE TABLE analysis.latest_ask (listing_id TEXT, first_ask DOUBLE, latest_ask DOUBLE)"
    )
    db.execute("CREATE TABLE buildings.lots (building_id TEXT, bbl TEXT, pluto_release TEXT)")
    db.execute("CREATE TABLE city.pluto (bbl TEXT, release TEXT, unitsres TEXT)")
    for listing, unit, lot, bedrooms, floor, on, off, ask in ads:
        building = f"b{lot}"
        db.execute(
            "INSERT INTO ads.market VALUES (?, DATE '2026-10-10', ?, ?)", [listing, on, off]
        )
        db.execute("INSERT INTO ads.placed VALUES (?, ?, ?)", [listing, unit, building])
        db.execute("INSERT INTO ads.reported VALUES (?, NULL)", [listing])
        db.execute(
            "INSERT INTO analysis.kept VALUES (?, ?, ?, ?, 1, ?, NULL)",
            [listing, unit, building, bedrooms, floor],
        )
        db.execute("INSERT INTO analysis.latest_ask VALUES (?, ?, ?)", [listing, ask, ask])
    db.executemany(
        "INSERT INTO ads.photos VALUES (?, ?)",
        [(listing, key) for key, ids in photos.items() for listing in ids],
    )
    db.executemany(
        "INSERT INTO buildings.lots VALUES (?, ?, '26v2')", [(f"b{A}", A), (f"b{B}", B)]
    )
    db.executemany("INSERT INTO city.pluto VALUES (?, '26v2', ?)", [(A, "3"), (B, "2")])
    query = render_context.render("analysis.relist_pairs").sql(dialect="duckdb")
    db.execute(f"CREATE TABLE analysis.relist_pairs AS {query}")
    pairs = db.sql(
        "SELECT * FROM analysis.relist_pairs ORDER BY listing_id, next_listing_id"
    ).fetchall()
    assert pairs == [(A, "1", "2", "u1", "u2", 4, 1), (A, "2", "7", "u2", "u7", 3, 1)]

    (table,) = links.execute.__wrapped__(Fetcher(db), None, None, None)
    db.register("relist_links_frame", table)
    db.execute("CREATE TABLE analysis.relist_links AS SELECT * FROM relist_links_frame")
    outcomes = db.sql(
        """SELECT listing_id, next_listing_id, outcome, relist_unit, next_relist_unit
        FROM analysis.relist_links ORDER BY listing_id"""
    ).fetchall()
    assert outcomes == [("1", "2", "clash", "u1", "u2"), ("2", "7", "joined", "u2", "u2")]
    query = render_context.render("analysis.relist_units").sql(dialect="duckdb")
    units = db.sql(f"SELECT * FROM ({query}) ORDER BY unit_id").fetchall()
    assert units == [("u2", "u2", 2), ("u7", "u2", 2)]
