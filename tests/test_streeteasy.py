from apartments.streeteasy import (
    _event_datetime,
    listing_is_furnished,
    split_unit,
    unit_format,
    unit_is_excluded,
    unit_kind,
    unit_suffix,
)


def test_event_datetime():
    assert _event_datetime("8/6/2024") == "2024-08-06"
    assert _event_datetime("unknown") is None


def test_split_unit():
    assert split_unit("3B") == (3, "B")
    assert split_unit("12-A") == (12, "A")
    assert split_unit("3") == (3, None)
    assert split_unit("3658") == (3, None)
    assert split_unit("PH") == (None, None)
    assert unit_suffix("3B") == "B"
    assert unit_suffix("3658") == "658"
    assert unit_format("3B") == "floor-letter"
    assert unit_format("3658") == "numeric"
    assert unit_kind("3B") == "physical-unit"
    assert unit_kind("1bd1ba") == "generic-layout"
    assert unit_kind("1bd/1ba") == "generic-layout"
    assert unit_kind("1BD") == "generic-layout"
    assert unit_kind("2BD") == "generic-layout"
    assert split_unit("1BD") == (None, None)
    assert unit_format("1BD") == "generic-layout"
    assert unit_kind("PHB") == "physical-unit"
    assert split_unit("PHB") == (None, "B")
    assert unit_suffix("PHB") == "B"
    assert unit_format("PHB") == "penthouse"


def test_furnished_detection():
    assert listing_is_furnished({"home_features": ["Dishwasher", "Furnished"]})
    assert not listing_is_furnished({"description": "A furnished apartment", "home_features": []})


def test_excluded_units():
    assert unit_is_excluded("the-sierra-chelsea", "7")
    assert unit_is_excluded("the-sierra-chelsea", "8")
    assert not unit_is_excluded("the-sierra-chelsea", "3B")
