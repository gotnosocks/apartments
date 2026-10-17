import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import duckdb
import pytest

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
      no lot.
    - 900205 gives 210 West 91st Street with no map point, and PAD gives condominium lot 7502
      of block 1238. MapPLUTO gives the address to lot 7502 and lot 9037. The building's one
      ad asks $600, so no candidate ad reads the lot, and its unitsres of 0 comes from the
      latest release. The ad's building has no candidate ad for its BIN, so the lot has no
      co_units.
    - 900206 gives 622 Amsterdam Avenue with no map point, and PAD gives lot 7503. MapPLUTO
      lists that lot under 203 West 90th Street and no lot under the address. Unit 8a's ad of
      June 2025 reads release 16v2, with 6 floors, and the latest release gives 11.
    - 900207 gives 84-70 257th Street in Queens, which the fixture's PAD lacks, so it gets no
      lot. MapPLUTO gives the address to lot 40 of Queens block 8786.

    The script refuses the state the build writes, and runs on a renamed copy without changing
    it. A second copy gives 900204 the BIN of lot 13's building, which has no certificate, and
    gives the BIN of 900201 a certificate of 20 apartments. Lot 12 then counts a building with
    no certificate, so it gets no co_units."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "cases" / "export", export)
    record = identity.record
    buildings = [
        record("900201", "135 West 89th Street", identity.IN_12, ("C6", 1910, 8, 15)),
        record("900202", "259 West 90th Street"),
        record("900203", "The Ballet Building"),
        record("900204", "137 West 89th Street", identity.IN_12, identity.FACTS_12),
        record("900205", "210 West 91st Street"),
        record("900206", "622 Amsterdam Avenue"),
        record(
            "900207", "84-70 257th Street", zip="11001", city="Queens", district="413"
        ),
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
    plans += [("900206", june, "8a"), ("900207", september, "3a")]
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
    ads.append(
        (9002098, helpers.row_record(9002098, september, "5c", "5C", "900205", ask=600))
    )
    helpers.append_answers(
        export, helpers.answers("listing_id", ads, 20, "2026-09-20T12:00Z")
    )
    ctx = helpers.context(monkeypatch, tmp_path / "state", export)
    ctx.plan(auto_apply=True, no_prompts=True)
    ctx.close()

    out = tmp_path / "report"
    copy = tmp_path / "copy" / "renamed.duckdb"
    copy.parent.mkdir()
    shutil.copy2(tmp_path / "state" / "pipeline.duckdb", copy)
    before = hashlib.sha256(copy.read_bytes()).hexdigest()
    monkeypatch.setattr(citycheck, "LIVE", tmp_path / "state" / "pipeline.duckdb")
    with pytest.raises(SystemExit, match="live state"):
        citycheck.main([str(citycheck.LIVE), "--out", str(out)])
    assert citycheck.main([str(copy), "--out", str(out), "--memory", "1GB"]) == 0
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == before
    assert [p.name for p in copy.parent.iterdir()] == ["renamed.duckdb"]
    report = json.loads((out / "citycheck.json").read_text())
    assert (out / "citycheck.md").read_text().startswith("# City check")
    assert report["as_of"] == september

    lots = report["lots"]
    assert {
        r["link"]: (r["buildings"], r["ads"], r["rows"]) for r in lots["by_link"]
    } == {
        "both": (1, 17, 17),
        "address_only": (3, 9, 8),
        "footprint": (1, 1, 1),
        "none": (2, 2, 2),
    }
    assert (lots["buildings"], lots["buildings_with_lot"]) == (7, 5)
    assert (lots["rows"], lots["rows_with_lot"]) == (28, 26)
    address = lots["mappluto_address"]
    assert address["buildings"]["all"] == {
        "same": 2,
        "among_several": 1,
        "other": 1,
        "only_mappluto": 1,
        "no_match": 1,
        "unparsed": 1,
    }
    assert address["rows"]["by_link"]["footprint"]["other"] == 1
    assert address["buildings"]["by_link"]["address_only"]["among_several"] == 1
    assert [
        (c["building_id"], c["bbl"], c["pluto_lots"]) for c in lots["disagreements"]
    ] == [
        ("900204", "1012200012", ["1012200010"]),
        ("900207", None, ["4087860040"]),
    ]

    units = report["units"]
    assert units["lots"] == 4
    assert units["lots_by_link"] == {"address_or_footprint": 1, "other_links": 3}
    classes = units["lots_by_class"]
    nonzero = {k: v for k, v in classes["units_all vs unitsres"].items() if v}
    assert nonzero == {"zero_count": 1, "within": 2, "above by 2 to 5": 1}
    assert classes["units_12m vs unitsres"]["above by 1"] == 1
    nonzero = {k: v for k, v in classes["units_all vs co_units"].items() if v}
    assert nonzero == {"no_count": 2, "within": 1, "above by 2 to 5": 1}
    split = units["lots_by_class_by_link"]
    assert (
        split["address_or_footprint"]["units_all vs unitsres"]["above by 2 to 5"] == 1
    )
    assert split["other_links"]["units_all vs unitsres"]["zero_count"] == 1
    (zero,) = units["top_zero_unitsres"]
    assert (zero["bbl"], zero["unitsres_from"], zero["unitsres_release"]) == (
        "1012387502",
        "latest_release",
        "26v2",
    )
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
    assert (floors["rows"], floors["rows_with_floor"]) == (28, 27)
    lot = {k: v for k, v in floors["against_numfloors"].items() if v}
    assert lot == {
        "no_lot": 2,
        "within": 22,
        "within_latest": 1,
        "above by 2": 1,
        "above by 3 to 5": 1,
    }
    split = floors["against_numfloors_by_link"]
    assert {k: v for k, v in split["address_or_footprint"].items() if v} == {
        "within": 1
    }
    assert split["other_links"]["within_latest"] == 1
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
    assert (case["numfloors"], case["latest_numfloors"], case["sources"]) == (
        5,
        5,
        ["advertised", "label"],
    )

    planted = tmp_path / "planted" / "pipeline.duckdb"
    planted.parent.mkdir()
    shutil.copy2(copy, planted)
    db = duckdb.connect(str(planted))
    db.execute("CREATE SCHEMA planted")
    for view, change in (
        (
            "buildings.lots",
            "CASE WHEN building_id = '900204' THEN '1032437' ELSE bin END AS bin",
        ),
        (
            "analysis.building_certificates",
            "CASE WHEN bin = '1032436' THEN 20 ELSE units END AS units",
        ),
    ):
        table = "pipeline.planted." + view.replace(".", "_")
        db.execute(f"CREATE TABLE {table} AS FROM {view}")
        db.execute(
            f"CREATE OR REPLACE VIEW {view} AS SELECT * REPLACE ({change}) FROM {table}"
        )
    db.close()
    out = tmp_path / "planted-report"
    assert citycheck.main([str(planted), "--out", str(out), "--memory", "1GB"]) == 0
    units = json.loads((out / "citycheck.json").read_text())["units"]
    top = {c["bbl"]: c for c in units["top_above"]}
    assert top["1012200012"]["bins"] == ["1032436", "1032437"]
    assert top["1012200012"]["co_units"] is None
    nonzero = {
        k: v for k, v in units["lots_by_class"]["units_all vs co_units"].items() if v
    }
    assert nonzero == {"no_count": 2, "within": 1, "above by 2 to 5": 1}
