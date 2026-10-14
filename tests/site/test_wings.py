from apartments.site import wings
from apartments.site.build import building_rows

FITTED = {"the-west-coast", "the-west-coast-west-wing"}


def test_three_digit_labels_go_to_the_west_wing():
    assert wings.wing("the-west-coast", "620", FITTED) == "the-west-coast-west-wing"
    assert (
        wings.wing("97-horatio-street-new_york", "301", FITTED)
        == "the-west-coast-west-wing"
    )


def test_letter_labels_stay_on_the_west_coast():
    for label in ("9L", "10A", "PH1"):
        assert wings.wing("the-west-coast", label, FITTED) == "the-west-coast"
    assert wings.wing("97-horatio-street-new_york", "9L", FITTED) == "the-west-coast"


def test_a_fit_without_the_wing_keeps_the_slug():
    assert wings.wing("the-west-coast", "620", {"the-west-coast"}) == "the-west-coast"
    assert wings.wing("other-building", "620", FITTED) == "other-building"
    assert wings.wing("the-west-coast", None, FITTED) == "the-west-coast"


def test_wing_names_need_both_wings():
    assert wings.names(FITTED) == {
        "the-west-coast-west-wing": "The West Coast (West Street wing)",
        "the-west-coast": "The West Coast (Washington Street wing)",
    }
    assert wings.names({"the-west-coast", "x"}) == {}


def _listing(slug):
    return {
        "building_id": slug,
        "neighbourhood": "West Village",
        "period": "2026-01-01",
        "is_current": False,
        "residual_pct": 0.0,
    }


def test_building_rows_name_both_wings():
    registry = [
        {"building": s, "bbl": 1006430001, "label": "95 Horatio Street"} for s in FITTED
    ]
    rows = building_rows([], [_listing(s) for s in FITTED], [], registry, [])
    names = {r["id"]: r["name"] for r in rows}
    assert names["the-west-coast-west-wing"] == "The West Coast (West Street wing)"
    assert names["the-west-coast"] == "The West Coast (Washington Street wing)"
