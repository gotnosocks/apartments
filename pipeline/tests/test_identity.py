import importlib.util
import json
import shutil
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "tests" / "fixture"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of test_pipeline.py load the same way.
helpers = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py"))
context, append_answers, answers = (
    helpers.context,
    helpers.append_answers,
    helpers.answers,
)

# Points in the fixture's footprints: in 135, 133 and 137 West 89th Street and 601 Amsterdam
# Avenue, lots 12, 13, 10 and 1 of Manhattan block 1220, and in 61 Adelphi Street, lot 38 of
# Brooklyn block 2045. NEAR_12 lies in the street a few metres from the front of 135 West 89th
# Street, and AWAY a block from any footprint of the fixture.
IN_12 = (40.789342, -73.972422)
IN_13 = (40.789310, -73.972341)
IN_10 = (40.78939, -73.97248)
IN_1 = (40.78981, -73.972987)
IN_ADELPHI = (40.695784, -73.972057)
NEAR_12 = (40.789218, -73.972512)
AWAY = (40.7880, -73.9740)
# MapPLUTO 26v2's facts of lots 12 and 13, which agree, of lot 10, which has no apartments,
# and of lot 1.
FACTS_12 = ("C6", 1910, 5, 15)
FACTS_10 = ("G1", 1910, 5, 0)
FACTS_1 = ("D6", 1997, 18, 265)


def record(building_id, street, point=None, facts=(None, None, None, None), **address):
    """A building record with `street`, the map point `point` and the city facts `facts`: the
    class, the year, the floor count and the count of apartments. `address` sets the zip, city
    and community district, a Manhattan address on the Upper West Side unless given."""
    place = {"zip": "10024", "city": "New York", "district": "107", **address}
    data = {
        "id": building_id,
        "slug": f"{building_id}-case",
        "address": {"street": street, "zipCode": place["zip"], "city": place["city"]},
        "nyc": {"communityDistrict": place["district"], "buildingClass": facts[0]},
        "yearBuilt": facts[1],
        "floorCount": facts[2],
        "residentialUnitCount": facts[3],
    }
    if point:
        data["geoCenter"] = {"latitude": point[0], "longitude": point[1]}
    return building_id, json.dumps(data)


def test_identity_cases(tmp_path, monkeypatch):
    """Buildings of the case fixture, each with a record of its own:

    - 900101 and 900102 write 135 West 89th Street as `135 W. 89th St.` and by its other name
      `135 Ballet Hispanico Way`, with the map point in its footprint. The address and the point
      give lot 12.
    - 900103 and 900104 give 137 West 89th Street, lot 10, with the map point in lot 12's
      footprint. Lot 10 has no apartments and lot 12 has some, so the footprint's lot stands
      whatever the facts. 900116 gives 135 West 89th Street with the map point in lot 10's
      footprint and the facts of lot 10, and the address's lot stands.
    - 900117 and 900118 give 135 West 89th Street with the map point in lot 1's footprint. Both
      lots have apartments. The facts of lot 1 decide for the footprint, and those of lot 12
      for the address.
    - 900105 gives 135 West 89th Street with the map point in lot 13's footprint. Lots 12 and 13
      have the same facts, so the address's lot stands.
    - 900106 has its map point far from any footprint, and 900107 has it in the street 4 m from
      lot 12's footprint.
    - 900108's address has no house number, and 900109 has neither a house number nor a map
      point.
    - 900110 gives 61 Adelphi Street, whose range in PAD has the BIN 3000000, and its footprint
      gives the numbered BIN.
    - 900111 to 900114 give Broadway addresses with a letter and with a hyphen, without map
      points. 2449A matches its own range. 2449, and 2449 B with its letter after a space, match
      the range 2441-2449 and the range of 2449A, but no better than by their first nine
      characters.
    - 900115 has no community district, so its borough comes from the city."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)
    adelphi = {"zip": "11205", "city": "Brooklyn", "district": "302"}
    buildings = [
        record("900101", "135 W. 89th St.", IN_12, FACTS_12),
        record("900102", "135 Ballet Hispanico Way", IN_12, FACTS_12),
        record("900103", "137 West 89th Street", IN_12, FACTS_12),
        record("900104", "137 West 89th Street", IN_12, FACTS_10),
        record("900105", "135 West 89th Street", IN_13, FACTS_12),
        record("900106", "135 West 89th Street", AWAY, FACTS_12),
        record("900107", "135 West 89th Street", NEAR_12, FACTS_12),
        record("900108", "The Ballet Building", IN_12, FACTS_12),
        record("900109", "The Ballet Building"),
        record(
            "900110", "61 Adelphi Street", IN_ADELPHI, ("K1", 1952, 1, 0), **adelphi
        ),
        record("900111", "2449A Broadway"),
        record("900112", "2449 Broadway"),
        record("900113", "2449 B Broadway"),
        record("900114", "2440-2446 Broadway"),
        record(
            "900115", "258A 15th Street", zip="11215", city="Brooklyn", district=None
        ),
        record("900116", "135 West 89th Street", IN_10, FACTS_10),
        record("900117", "135 West 89th Street", IN_1, FACTS_1),
        record("900118", "135 West 89th Street", IN_1, FACTS_12),
    ]
    append_answers(
        export, answers("building_id", buildings, 40, "2026-09-01T12:00Z"), "buildings"
    )
    ctx = context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    lots = ctx.fetchdf(
        """SELECT building_id, link, bbl, bin, address_rank, footprint_inside
        FROM buildings.lots WHERE building_id LIKE '9001%' ORDER BY building_id"""
    )
    rows = [
        tuple(None if pd.isna(v) else v for v in row)
        for row in lots.itertuples(index=False)
    ]
    assert rows == [
        ("900101", "both", "1012200012", "1032436", 0, True),
        ("900102", "both", "1012200012", "1032436", 0, True),
        ("900103", "footprint_apartments", "1012200012", "1032436", 0, True),
        ("900104", "footprint_apartments", "1012200012", "1032436", 0, True),
        ("900105", "tie", "1012200012", "1032436", 0, True),
        ("900106", "address_only", "1012200012", "1032436", 0, None),
        ("900107", "both", "1012200012", "1032436", 0, False),
        ("900108", "footprint_only", "1012200012", "1032436", None, True),
        ("900109", None, None, None, None, None),
        ("900110", "both", "3020450038", "3058101", 2, True),
        ("900111", "address_only", "1012380010", "1033555", 0, None),
        ("900112", "address_only", "1012380010", "1033555", 4, None),
        ("900113", "address_only", "1012380010", "1033555", 12, None),
        ("900114", "address_only", "1012387501", "1033556", 0, None),
        ("900115", "address_only", "3010480026", "3023960", 0, None),
        ("900116", "address_apartments", "1012200012", "1032436", 0, True),
        ("900117", "footprint", "1012200001", "1085485", 0, True),
        ("900118", "address", "1012200012", "1032436", 0, True),
    ]
    fits = ctx.fetchdf(
        """SELECT building_id, address_fit, footprint_fit, round(footprint_metres) AS metres
        FROM buildings.lots
        WHERE building_id IN ('900103', '900104', '900107', '900117', '900118')
        ORDER BY building_id"""
    )
    assert fits.values.tolist() == [
        ["900103", 2, 4, 3],
        ["900104", 4, 2, 3],
        ["900107", 4, 4, 4],
        ["900117", 0, 4, 3],
        ["900118", 4, 0, 3],
    ]
