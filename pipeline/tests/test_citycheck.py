import importlib.util
import json
import shutil
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "tests" / "fixture"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of other test modules load the same way.
helpers = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py"))
identity = load("identity_tests", Path(__file__).with_name("test_identity.py"))
citycheck = load("citycheck", PROJECT.parent / "ops" / "pipeline" / "citycheck.py")


def test_citycheck_cases(tmp_path, monkeypatch):
    """ops/pipeline/citycheck.py reports these planted cases in a fixture state:

    - 900201 gives 135 West 89th Street, lot 12 of Manhattan block 1220, with a StreetEasy
      floor count of 8. MapPLUTO gives the lot 15 apartments and 5 floors. 15 units have ads
      in September 2026 and 2 more in June 2025. Unit 7a reads floor 7 from its label, above
      the lot's 5 floors and within StreetEasy's 8. Unit 9b's ad says ninth floor, above both.
      Unit 10c's label floor of 10 is above StreetEasy's count, so its row has no floor.
    - 900204 gives 137 West 89th Street, lot 10, with its map point and its facts on lot 12.
      The build takes lot 12 from the footprint, and MapPLUTO's address gives lot 10. Its unit
      2d brings lot 12 to 18 units over all time and 16 in the last 12 months.
    - 900202 gives 259 West 90th Street with no map point, lot 9 of block 1238. MapPLUTO gives
      the lot 9 apartments, and its latest certificate of occupancy, from 2016, gives 4. 7 units
      have ads.
    - 900203, The Ballet Building, has no address the city knows and no map point, so it gets
      no lot."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)
    record = identity.record
    buildings = [
        record("900201", "135 West 89th Street", identity.IN_12, ("C6", 1910, 8, 15)),
        record("900202", "259 West 90th Street"),
        record("900203", "The Ballet Building"),
        record("900204", "137 West 89th Street", identity.IN_12, identity.FACTS_12),
    ]
    helpers.append_answers(
        export,
        helpers.answers("building_id", buildings, 40, "2026-09-01T12:00Z"),
        "buildings",
    )
    september, june = "2026-09-05", "2025-06-01"
    plans = [("900201", september, f"{n}{c}") for n in range(1, 5) for c in "abc"]
    plans += [("900201", september, "7a"), ("900201", september, "10c")]
    plans += [("900201", june, "5a"), ("900201", june, "5b")]
    plans += [("900204", september, "2d"), ("900203", september, "1a")]
    plans += [("900202", september, f"{n}{c}") for n in range(1, 5) for c in "ab"][:7]
    ads = [
        (
            9002000 + i,
            helpers.row_record(9002000 + i, day, unit, unit.upper(), building),
        )
        for i, (building, day, unit) in enumerate(plans)
    ]
    ninth = helpers.row_record(
        9002099,
        september,
        "9b",
        "9B",
        "900201",
        description="This ninth-floor apartment.",
    )
    ads.append((9002099, ninth))
    helpers.append_answers(
        export, helpers.answers("listing_id", ads, 20, "2026-09-20T12:00Z")
    )
    ctx = helpers.context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    ctx.close()

    out = tmp_path / "report"
    state = tmp_path / "state" / "pipeline.duckdb"
    assert citycheck.main([str(state), "--out", str(out), "--memory", "1GB"]) == 0
    report = json.loads((out / "citycheck.json").read_text())
    assert (out / "citycheck.md").read_text().startswith("# City check")
    assert report["as_of"] == september

    lots = report["lots"]
    assert {
        r["link"]: (r["buildings"], r["ads"], r["rows"]) for r in lots["by_link"]
    } == {
        "both": (1, 17, 17),
        "address_only": (1, 7, 7),
        "footprint": (1, 1, 1),
        "none": (1, 1, 1),
    }
    assert (lots["buildings"], lots["buildings_with_lot"]) == (4, 3)
    assert (lots["rows"], lots["rows_with_lot"]) == (26, 25)
    address = lots["mappluto_address"]
    nonzero = {k: v for k, v in address["buildings"]["all"].items() if v}
    assert nonzero == {"same": 2, "other": 1, "unparsed": 1}
    assert address["rows"]["by_link"]["footprint"]["other"] == 1
    (case,) = lots["disagreements"]
    assert (case["building_id"], case["bbl"], case["pluto_lots"]) == (
        "900204",
        "1012200012",
        ["1012200010"],
    )

    units = report["units"]
    assert units["lots"] == 2
    classes = units["lots_by_class"]
    assert classes["units_all vs unitsres"]["above by 2 to 5"] == 1
    assert classes["units_12m vs unitsres"]["above by 1"] == 1
    assert classes["units_all vs co_units"]["above by 2 to 5"] == 1
    top = {c["bbl"]: c for c in units["top_above"]}
    assert [c["bbl"] for c in units["top_above"]] == ["1012200012", "1012380009"]
    assert (
        top["1012200012"]["units_all"],
        top["1012200012"]["units_12m"],
        top["1012200012"]["unitsres"],
    ) == (18, 16, 15)
    assert (
        top["1012380009"]["units_all"],
        top["1012380009"]["unitsres"],
        top["1012380009"]["co_units"],
    ) == (7, 9, 4)

    floors = report["floors"]
    assert (floors["rows"], floors["rows_with_floor"]) == (26, 25)
    lot = {k: v for k, v in floors["against_numfloors"].items() if v}
    assert lot == {"no_lot": 1, "within": 22, "above by 2": 1, "above by 3 to 5": 1}
    assert floors["against_streeteasy"]["above by 1"] == 1
    assert floors["above_both"] == 1
    assert floors["refused_labels_against_numfloors"]["above by 3 to 5"] == 1
    (case,) = floors["top_above_numfloors"]
    assert (case["bbl"], case["rows"], case["units"], case["top_floor"]) == (
        "1012200012",
        2,
        2,
        9,
    )
    assert (case["numfloors"], case["sources"]) == (5, ["advertised", "label"])
