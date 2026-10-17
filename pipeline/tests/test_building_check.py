import duckdb

# Each case is an ad in its own building on its own lot: the ad's advertised, physical and
# label floors and StreetEasy's floor count for the building; the lot's floor count, building
# count, apartments and land use as of the ad's first day; the same facts in the latest release,
# with the lot's building area and class there; the lot's building area, apartments and class in
# an earlier release; the copy of the building footprints holding a footprint on the lot; the
# count of units the ads place in the building; and the units and new-building flag of the BIN's
# certificates of occupancy.
BASE = {
    "floors": (None, None, None, None),
    "dated": (5.0, 1, 10, 2),
    "latest": (5.0, 1, 10, 2),
    "area": 1000.0,
    "class": "X1",
    "earlier": None,
    "footprint": None,
    "units": 1,
    "certificate": (None, None),
    "dropped": False,
}
NEVER = {"dated": (0.0, 0, 0, 10), "latest": (0.0, 0, 0, 10), "area": 0.0, "units": 12}
CASES = {
    # The floor rule.
    "above": {"floors": (8, None, None, None)},
    "one above": {
        "floors": (4, None, None, None),
        "dated": (3.0, 1, 10, 2),
        "latest": (3.0, 1, 10, 2),
    },
    "tall": {
        "floors": (38, None, None, None),
        "dated": (25.0, 1, 300, 2),
        "latest": (25.0, 1, 300, 2),
    },
    "tower": {
        "floors": (21, None, None, None),
        "dated": (19.0, 1, 90, 2),
        "latest": (19.0, 1, 90, 2),
    },
    "gained floors": {"floors": (8, None, None, None), "latest": (9.0, 1, 10, 2)},
    "no latest floor count": {
        "floors": (8, None, None, None),
        "latest": (0.0, 1, 10, 2),
    },
    "two buildings": {"floors": (8, None, None, None), "dated": (5.0, 2, 10, 2)},
    "now two buildings": {"floors": (8, None, None, None), "latest": (5.0, 2, 10, 2)},
    "physical": {"floors": (None, 8, None, None)},
    "listed floors": {"floors": (8, None, None, 10)},
    "label": {"floors": (None, None, 12, None), "dated": (4.0, 1, 10, 2)},
    "advertised first": {"floors": (3, None, 12, None), "dated": (4.0, 1, 10, 2)},
    "no floor count": {"floors": (8, None, None, None), "dated": (0.0, 1, 10, 2)},
    "no latest record": {"floors": (8, None, None, None), "latest": None},
    # The zero-unit rule.
    "industrial": {"dated": (2.0, 1, 0, 6), "latest": (2.0, 1, 0, 6), "units": 2},
    "mixed": {"dated": (2.0, 1, 0, 4), "latest": (2.0, 1, 0, 4)},
    "office": {"dated": (2.0, 1, 0, 5), "latest": (2.0, 1, 0, 5)},
    "now residential": {"dated": (2.0, 1, 0, 8), "latest": (2.0, 1, 12, 8)},
    "now mixed": {"dated": (2.0, 1, 0, 6), "latest": (2.0, 1, 0, 4)},
    "four units": {"dated": (2.0, 1, 0, 6), "latest": (2.0, 1, 0, 6), "units": 4},
    "certificate": {
        "dated": (2.0, 1, 0, 6),
        "latest": (2.0, 1, 0, 6),
        "certificate": (6, False),
    },
    "new building": {
        "dated": (2.0, 1, 0, 6),
        "latest": (2.0, 1, 0, 6),
        "certificate": (None, True),
    },
    # The never-built rule.
    "never built": NEVER,
    "old footprint": NEVER | {"footprint": "20250101"},
    "footprint": NEVER | {"footprint": "20261016"},
    "built before": NEVER | {"earlier": (4000.0, 0, "X1")},
    "blank area": NEVER | {"earlier": (None, 0, "X1")},
    "blank count": NEVER | {"earlier": (0.0, None, "X1")},
    "condominium": NEVER | {"class": "R0"},
    "condominium before": NEVER | {"earlier": (0.0, 0, "R4")},
    "no releases": NEVER | {"latest": None},
    "apartments": NEVER | {"certificate": (6, False)},
    "rising": NEVER | {"certificate": (None, True)},
    # Both rules.
    "parking": {
        "floors": (5, None, None, None),
        "dated": (1.0, 1, 0, 10),
        "latest": (1.0, 1, 0, 10),
    },
    # A live drop_lot of the corrections ledger leaves the ad's lot facts empty.
    "lot taken away": {
        "floors": (5, None, None, None),
        "dated": (1.0, 1, 0, 10),
        "latest": (1.0, 1, 0, 10),
        "dropped": True,
    },
}


def inputs(db):
    """Write the tables the check reads, with a row of each case."""
    for schema in ("analysis", "buildings", "ads", "city"):
        db.execute(f"CREATE SCHEMA {schema}")
    db.execute(
        """CREATE TABLE analysis.rows (listing_id TEXT, building_id TEXT,
        advertised_floor INT, physical_floor INT, label_derived_floor INT,
        building_floor_count INT)"""
    )
    db.execute(
        """CREATE TABLE analysis.lot_facts (listing_id TEXT, bbl TEXT, pluto_release TEXT,
        numfloors DOUBLE, numbldgs INT, unitsres INT, landuse INT, bldgclass TEXT)"""
    )
    db.execute(
        "CREATE TABLE buildings.lots (building_id TEXT, bbl TEXT, pluto_release TEXT)"
    )
    db.execute(
        """CREATE TABLE buildings.lot_releases (bbl TEXT, release TEXT, numfloors DOUBLE,
        numbldgs INT, unitsres INT, landuse INT, bldgarea DOUBLE, bldgclass TEXT)"""
    )
    db.execute(
        "CREATE TABLE city.footprints (release TEXT, published TEXT, mappluto_bbl TEXT)"
    )
    for release in ("20250101", "20261016"):
        db.execute(
            "INSERT INTO city.footprints VALUES (?, ?, '1999990001')",
            [release, release[:4] + "-" + release[4:6] + "-" + release[6:]],
        )
    db.execute(
        "CREATE TABLE ads.placed (listing_id TEXT, building_id TEXT, unit_id TEXT)"
    )
    db.execute(
        """CREATE TABLE analysis.building_certificates
        (listing_id TEXT, units INT, new_building BOOLEAN)"""
    )
    for n, (name, case) in enumerate(CASES.items()):
        case = BASE | case
        ad, building, lot = name, f"b{n}", f"10000100{n:02d}"
        db.execute(
            "INSERT INTO analysis.rows VALUES (?, ?, ?, ?, ?, ?)",
            [ad, building, *case["floors"]],
        )
        if case["dropped"]:
            db.execute("INSERT INTO analysis.lot_facts (listing_id) VALUES (?)", [ad])
        else:
            db.execute(
                "INSERT INTO analysis.lot_facts VALUES (?, ?, '19v1', ?, ?, ?, ?, 'X1')",
                [ad, lot, *case["dated"]],
            )
        db.execute("INSERT INTO buildings.lots VALUES (?, ?, '26v2')", [building, lot])
        if case["latest"]:
            db.execute(
                "INSERT INTO buildings.lot_releases VALUES (?, '26v2', ?, ?, ?, ?, ?, ?)",
                [lot, *case["latest"], case["area"], case["class"]],
            )
        if case["earlier"]:
            area, apartments, kind = case["earlier"]
            floors, count, _, use = case["latest"]
            db.execute(
                "INSERT INTO buildings.lot_releases VALUES (?, '11v1', ?, ?, ?, ?, ?, ?)",
                [lot, floors, count, apartments, use, area, kind],
            )
        if case["footprint"]:
            db.execute(
                "INSERT INTO city.footprints SELECT release, published, ? FROM city.footprints"
                " WHERE release = ? LIMIT 1",
                [lot, case["footprint"]],
            )
        db.execute("INSERT INTO ads.placed VALUES (?, ?, ?)", [ad, building, "u0"])
        for u in range(1, case["units"]):
            db.execute(
                "INSERT INTO ads.placed VALUES (?, ?, ?)",
                [f"{name} {u}", building, f"u{u}"],
            )
        db.execute(
            "INSERT INTO analysis.building_certificates VALUES (?, ?, ?)",
            [ad, *case["certificate"]],
        )


def test_building_check_cases(tmp_path, render_context):
    """analysis.building_check lists these made-up rows:

    - `above` is on floor 8 of a lot of 5 floors in both releases.
    - `label` reads floor 12 from its unit label, on a lot of 4 floors.
    - `physical` is on physical floor 8 of a lot of 5 floors.
    - `no latest floor count` is on floor 8 of a lot of 5 floors, and the latest release gives
      the lot a floor count of 0, so the dated count decides.
    - `no latest record` is on floor 8 of a lot of 5 floors, and the latest release has no
      record of the lot.
    - `industrial` is on a lot with no apartments and land use 06 in both releases, and the
      ads place two units in its building.
    - `parking` is on floor 5 of a one-floor lot with no apartments and land use 10, so it
      gets both reasons.
    - `tall` is on floor 38 of a lot of 25 floors, 52% above the count.
    - `never built` is in a building of 12 advertised units, on a lot with no building area and
      no apartments in its only release and no footprint. `old footprint` also has a footprint
      in an earlier copy of the footprints, and the latest copy has none.

    The check leaves out the rest:

    - `one above` is on floor 4 of 3, within the floor of slack and 33% above the count.
    - `tower` is on floor 21 of a lot of 19 floors, 11% above the count.
    - `gained floors` is on floor 8, and the lot has 9 floors in the latest release.
    - `two buildings` is on a lot of two buildings, and `now two buildings` on a lot of two
      buildings in the latest release.
    - `listed floors` is on floor 8, and StreetEasy gives the building 10 floors.
    - `advertised first` advertises floor 3, and its unit label reads floor 12.
    - `no floor count` is on a lot with a floor count of 0.
    - `mixed` and `office` are on lots with land use 04 and 05.
    - `now residential` is on a lot with 12 apartments in the latest release, and `now mixed`
      on a lot with land use 04 in the latest release.
    - `four units` is in a building where the ads place four units.
    - `certificate` has a certificate of occupancy with 6 apartments, and `new building` a
      certificate of a new building.
    - `lot taken away` would get both reasons as `parking` does, but a live drop_lot took its
      lot away, so its lot facts are empty.
    - Of the lots like `never built`'s, `footprint` has a footprint in the latest copy. `built
      before` has a building area of 4,000 square feet in release 11v1. `blank area` has a blank
      building area in release 11v1 and `blank count` a blank apartment count there.
      `condominium` has the class R0, and `condominium before` the class R4 in release 11v1
      only. `no releases` has no record in any release. `apartments` has a certificate of
      occupancy with 6 apartments, and `rising` a certificate of a new building."""
    db = duckdb.connect(str(tmp_path / "pipeline.duckdb"))
    inputs(db)
    query = render_context.render("analysis.building_check").sql(dialect="duckdb")
    listed = db.execute(
        f"SELECT listing_id, reasons FROM ({query}) ORDER BY listing_id"
    ).fetchall()
    assert listed == [
        ("above", ["floor_above_lot"]),
        ("industrial", ["zero_unit_lot"]),
        ("label", ["floor_above_lot"]),
        ("never built", ["never_built_lot"]),
        ("no latest floor count", ["floor_above_lot"]),
        ("no latest record", ["floor_above_lot"]),
        ("old footprint", ["never_built_lot"]),
        ("parking", ["floor_above_lot", "zero_unit_lot"]),
        ("physical", ["floor_above_lot"]),
        ("tall", ["floor_above_lot"]),
    ]
