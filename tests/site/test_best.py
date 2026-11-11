"""Best for you: current listings ranked by a preference sheet (Ben, 2026-10-06)."""

import csv
import io
import json
import math

import pytest

from apartments.site import best

SHEET = {
    "profile": "test-v1",
    "description": "A test renter.",
    "weights": {
        "bedrooms=2": 1,
        "label:penthouse": -1,
        "quiet_street": 1,
        "text:gym": 0,
    },
    "latent": {"building level (buildings.level_pct)": 0.5, "unit effect": "later"},
    "neutral_on_purpose": ["furnished"],
}


@pytest.fixture(autouse=True)
def sheets(tmp_path, monkeypatch):
    """Preference sheets in the test's own folder, never the machine's."""
    folder = tmp_path / "preferences"
    folder.mkdir()
    (folder / "test-v1.json").write_text(json.dumps(SHEET))
    monkeypatch.setattr(best, "DIR", folder)
    monkeypatch.setattr(best, "DEFAULT_PROFILE", "test-v1")
    monkeypatch.setattr(best, "WISHES", tmp_path / "wishes")
    return folder


def test_profile_drops_zeros_and_reads_latent(sheets):
    p = best.load_profile(sheets / "test-v1.json")
    assert p["weights"] == {
        "bedrooms=2": 1.0,
        "label:penthouse": -1.0,
        "quiet_street": 1.0,
    }
    assert p["latent"] == {"level": 0.5}
    assert p["unmodelled"] == ["unit effect: later"]


def test_score_uses_the_model_size_and_the_sheet_sign():
    profile = {
        "weights": {
            "laundry=in_unit": 1.0,
            "elevator=no": -1.0,
            "log_sqft_vs_bedroom_median": 1.0,
            "log_floor": 1.0,
            "log_floor_above_6": 1.0,
        },
        "latent": {"level": 0.5},
    }
    betas = {
        "laundry=in_unit": 0.02,
        "elevator=no": 0.01,  # positive in the model, still a minus for this renter
        "log_sqft_vs_bedroom_median": 0.25,
        "log_floor": 0.01,
        "log_floor_above_6": 0.05,
    }
    inputs = {
        "laundry=in_unit": 1.0,
        "elevator=no": 1.0,
        "log_sqft_vs_bedroom_median": -0.2,
        "log_floor": 2.0,
        "log_floor_above_6": 0.5,
    }
    s = best.score(
        {"floor": 8}, inputs, {"level_pct": 10.0, "trend_pct": None}, profile, betas
    )
    expected = (
        0.02 - 0.01 - 0.05 + (0.01 * math.log(8) + 0.025) + 0.5 * math.log1p(0.10)
    )
    assert s["score"] == pytest.approx(expected)
    assert [t["label"] for t in s["pros"]] == [
        "a building that rents above similar ones",
        "the 8th floor",
        "in-unit laundry",
    ]
    assert [t["label"] for t in s["cons"]] == [
        "less space than usual for its bedrooms",
        "no elevator",
    ]
    assert s["unknown"] == []


def test_a_floor_below_the_usual_one_is_a_minus():
    profile = {"weights": {"log_floor": 1.0}, "latent": {}}
    betas = {"log_floor": 0.01}
    # The 1st floor has no log_floor input (log 1 = 0); it still counts.
    low = best.score({"floor": 1}, {}, None, profile, betas, usual_floor=4)
    assert low["score"] == pytest.approx(0.01 * math.log(1 / 4))
    assert [t["label"] for t in low["cons"]] == ["a low floor (the 1st floor)"]
    usual = best.score({"floor": 4}, {"log_floor": 1.386}, None, profile, betas, 4)
    assert usual["score"] == 0 and not usual["pros"] + usual["cons"]
    high = best.score({"floor": 9}, {"log_floor": 2.197}, None, profile, betas, 4)
    assert [t["label"] for t in high["pros"]] == ["the 9th floor"]
    # No floor stated: no floor term, named as unknown instead.
    assert best.score({"floor": None}, {}, None, profile, betas, 4)["score"] == 0


def test_unstated_details_are_named_not_counted():
    profile = {"weights": {"laundry=in_unit": 1.0, "elevator=no": -1.0}, "latent": {}}
    s = best.score(
        {"floor": None},
        {"laundry=unknown": 1.0, "elevator=unknown": 1.0},
        None,
        profile,
        {"laundry=in_unit": 0.02, "elevator=no": 0.01},
    )
    assert s["score"] == 0
    assert s["unknown"] == ["elevator", "laundry"]


def test_choose_filters_and_sorts():
    rows = [
        {"audit_id": "a", "bedrooms": 1, "ask": 4000, "income_restricted": False, "score": 0.1, "value": -8.2, "deal": 0.2},
        {"audit_id": "b", "bedrooms": 1, "ask": 6000, "income_restricted": False, "score": 0.3, "value": -8.4, "deal": 0.1},
        {"audit_id": "c", "bedrooms": 4, "ask": 3000, "income_restricted": True, "score": 0.5, "value": -7.5, "deal": 0.3},
    ]  # fmt: skip
    assert [r["audit_id"] for r in best.choose(rows)] == ["a", "b"]
    assert [r["audit_id"] for r in best.choose(rows, income=True)] == ["c", "a", "b"]
    assert [r["audit_id"] for r in best.choose(rows, sort="fit")] == ["b", "a"]
    assert [r["audit_id"] for r in best.choose(rows, max_rent=5000)] == ["a"]
    assert [r["audit_id"] for r in best.choose(rows, beds=3, income=True)] == ["c"]
    assert best.choose(rows, beds=0) == []


def test_street_view_stands_in_the_buildings_street():
    """The viewpoint moves from the lot (where the nearest panorama can be
    inside a shop) to the building's own street, facing the building."""
    from apartments.site import streetview

    assert streetview.street_key("225 West 14th Street") == "W 14 ST"
    assert streetview.street_key("1/2 Jane Street") == "JANE ST"
    assert streetview.street_key("10 West Street") == "WEST ST"
    assert streetview.street_key("100 Seventh Avenue South") == "7 AVE S"
    assert streetview.street_key("500 Avenue of the Americas") == "AVE OF THE AMERICAS"
    # A grid in metres: x east, y north; 1e-5 degrees a metre or so.
    buildings = [
        {"id": "a", "x": 0.0, "y": 30.0, "lon": -74.0, "lat": 40.0003},
        {"id": "b", "x": 100.0, "y": 0.0, "lon": -73.999, "lat": 40.0},
        {"id": "c", "x": 0.0, "y": 0.0, "lon": -74.0, "lat": 40.0},
    ]
    data = {
        "buildings": buildings,
        "_index": {"a": 0, "b": 1, "c": 2},
        "basemap": {
            "streets": [
                {"name": "W 14 ST", "points": [[-200.0, 0.0], [200.0, 0.0]]},
                {"name": "W 15 ST", "points": [[-200.0, 60.0], [200.0, 60.0]]},
            ]
        },
    }
    lat, lon, heading = streetview.viewpoint(data, "a", "225 West 14th Street")
    assert abs(lat - 40.0) < 1e-9 and abs(lon + 74.0) < 1e-9
    assert round(heading) == 0  # north, back at the building
    # Its own street is 30 m away, the other 30 m too: the address decides.
    lat, _, heading = streetview.viewpoint(data, "a", "2 West 15th Street")
    assert abs(lat - 40.0006) < 1e-9 and round(heading) == 180
    url = streetview.link(data, "a", 40.0003, -74.0, "225 West 14th Street")
    assert "viewpoint=40.000000%2C-74.000000&heading=0" in url


COMMUTE = """building,destination,address,minutes,transfers,walk_to_station_min,station
a,office,65 E 55th St,18.3,0,0.9,14 St
b,office,65 E 55th St,24.8,1,2.0,23 St
c,office,65 E 55th St,30.0,0,13.5,23 St
a,gym,1 Main St,10,0,1,14 St
"""


def test_commute_is_a_neutral_note_per_destination(tmp_path):
    (tmp_path / "commute-20261005.csv").write_text("building,destination\n")
    (tmp_path / "commute-20261006.csv").write_text(COMMUTE)
    best.WISHES = tmp_path  # undone by the autouse fixture
    commute = best.load_commute(best.commute_path())
    assert commute["office"]["median"] == 24.8
    a, b, c = (best.commute_tags(x, commute, ["office"]) for x in "abc")
    assert all("good" not in t for t in a + b + c)
    assert b[0]["label"] == "Commute to office: 25 min by subway, 1 transfer"
    assert "from 14 St, 1 min walk" in a[0]["title"]
    assert [t["destination"] for t in best.commute_tags("a", commute)] == [
        "office",
        "gym",
    ]
    assert best.load_commute(None) == {}


def test_bed_size_reads_the_newest_table(tmp_path):
    (tmp_path / "bed-size-20261005.csv").write_text("unit_id,largest\nu1,full\n")
    (tmp_path / "bed-size-20261006.csv").write_text(
        "unit_id,building,largest,listings,latest\n"
        "u1,a,king,2,queen\nu2,a,twin,1,twin\n,a,queen,1,queen\n"
    )
    best.WISHES = tmp_path  # undone by the autouse fixture
    assert best.load_bed_size(best.bed_size_path()) == {"u1": "king"}
    assert best.load_bed_size(None) == {}
    assert best.load_bed_size(tmp_path / "missing.csv") == {}
