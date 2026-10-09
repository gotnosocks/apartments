import importlib
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _screen():
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("quarantine_v13_screen")
    finally:
        sys.path.remove(str(SCRIPTS))


AREAS = [
    {
        "ntaname": "Midtown South-Flatiron-Union Square",
        "boroname": "Manhattan",
        "lat": 40.7420,
        "lon": -73.9900,
    },
    {"ntaname": "Madison", "boroname": "Brooklyn", "lat": 40.6056, "lon": -73.9464},
    {
        "ntaname": "Clinton Hill",
        "boroname": "Brooklyn",
        "lat": 40.6880,
        "lon": -73.9660,
    },
]


def test_far_part_naming_a_local_building_needs_its_borough():
    q = _screen()
    centre = q.CENTRES["NoMad"]
    names = set(q.far_places(AREAS, centre, ["madison-parq", "76-madison"]))
    assert "madison" not in names
    assert {"madison, brooklyn", "madison brooklyn", "clinton hill"} <= names
    # Without such a building, v12's far places are unchanged.
    v12 = importlib.import_module("quarantine_v12_screen")
    assert q.far_places(AREAS, centre) == v12.far_places(AREAS, centre)


def test_madison_parq_ads_are_not_far_but_clinton_hill_is(tmp_path):
    q = _screen()
    nta = tmp_path / "nta.json"
    nta.write_text(json.dumps(AREAS))
    terms = q.terms(nta, q.CENTRES["NoMad"], ["madison-parq"])["far_place"]
    rx = re.compile("|".join(f"(?:{t})" for t in terms))
    assert not rx.search("situated in the madison parq, an elegant building")
    assert not rx.search("a quiet studio in madison house")
    assert rx.search("a sunny unit in madison, brooklyn")
    assert rx.search("apartment located in clinton hill")
