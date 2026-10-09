import importlib
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _screen():
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("quarantine_v12_screen")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_far_part_of_a_local_name_needs_the_whole_name():
    q = _screen()
    centre = (40.7330, -73.9780)
    areas = [
        {
            "ntaname": "Stuyvesant Town-Peter Cooper Village",
            "lat": 40.7320,
            "lon": -73.9770,
        },
        {"ntaname": "Bedford-Stuyvesant (West)", "lat": 40.6870, "lon": -73.9420},
        {"ntaname": "Harlem (South)", "lat": 40.8040, "lon": -73.9510},
    ]
    names = q.far_places(areas, centre)
    assert "stuyvesant" not in names
    assert {"bedford-stuyvesant", "bedford stuyvesant", "bed-stuy"} <= set(names)
    assert "stuyvesant east" in names and "stuyvesant town" not in names
    # A far part in no local name still matches alone, as in v10.
    assert {"bedford", "harlem"} <= set(names)
    # Local names are never far places.
    assert "peter cooper village" not in names
    assert "brooklyn" in names


def test_far_place_terms_skip_stuyvesant_town_but_hit_bed_stuy_and_harlem(tmp_path):
    import json
    import re

    q = _screen()
    nta = tmp_path / "nta.json"
    nta.write_text(
        json.dumps(
            [
                {
                    "ntaname": "Stuyvesant Town-Peter Cooper Village",
                    "lat": 40.7320,
                    "lon": -73.9770,
                },
                {
                    "ntaname": "Bedford-Stuyvesant (East)",
                    "lat": 40.6830,
                    "lon": -73.9290,
                },
                {"ntaname": "Harlem (South)", "lat": 40.8040, "lon": -73.9510},
            ]
        )
    )
    terms = q.terms(nta, q.CENTRES["Stuyvesant Town/PCV"])["far_place"]
    rx = re.compile("|".join(f"(?:{t})" for t in terms))
    assert not rx.search("located in stuyvesant town, steps from first ave")
    assert rx.search("a sunny unit in bed-stuy")
    assert rx.search("apartment located in harlem")
    # v10's street guard still applies to a far name.
    assert not rx.search("in harlem ave")


def test_part_with_a_direction_that_is_not_local_is_still_far():
    q = _screen()
    areas = [
        {
            "ntaname": "Midtown South-Flatiron-Union Square",
            "lat": 40.7420,
            "lon": -73.9900,
        },
        {"ntaname": "Midtown-Times Square", "lat": 40.7600, "lon": -73.9840},
    ]
    names = set(q.far_places(areas, q.CENTRES["Chelsea"]))
    assert "midtown" not in names and "midtown south" not in names
    assert {"midtown east", "midtown west", "midtown-times square"} <= names
