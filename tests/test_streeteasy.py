from apartments.streeteasy import (
    _event_datetime,
    floor_override,
    listing_is_furnished,
    parse_price_history_html,
    physical_floor,
    split_unit,
    unit_facing,
    unit_format,
    unit_is_excluded,
    unit_kind,
    unit_suffix,
)


def test_two_and_three_column_history_tables():
    html = """
    <div data-testid="priceHistoryTable"><table><tbody>
      <tr><td><p>12/18/2023</p></td><td><p><b>$8,100</b></p><p>Listed by The Blueground</p></td></tr>
      <tr><td><p>12/6/2023</p></td><td><p><b>$6,200</b></p></td><td><a href="/rental/123">Rented by Cushman &amp; Wakefield (Management)</a></td></tr>
    </tbody></table></div>
    """
    events = parse_price_history_html(html)
    assert events[0] == {
        "date": "12/18/2023", "base_rent": 8100,
        "event": "Listed by The Blueground", "listing_url": None,
    }
    assert events[1]["event"] == "Rented by Cushman & Wakefield (Management)"
    assert events[1]["listing_url"] == "/rental/123"


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


def test_building_floor_override():
    assert floor_override("the-sierra-chelsea", "PHB", "penthouse") == 15
    assert floor_override("the-sierra-chelsea", "14B", "floor-letter") is None
    assert floor_override("another-building", "PHB", "penthouse") is None
    assert physical_floor(12, False) == 12
    assert physical_floor(14, False) == 13
    assert physical_floor(15, False) == 14
    assert physical_floor(14, True) == 14
    assert physical_floor(14, None) == 14
    assert unit_facing("the-sierra-chelsea", "A") == (True, False)
    assert unit_facing("the-sierra-chelsea", "J") == (True, False)
    assert unit_facing("the-sierra-chelsea", "K") == (True, True)
    assert unit_facing("the-sierra-chelsea", "L") == (False, True)
    assert unit_facing("the-sierra-chelsea", "W") == (False, True)
    assert unit_facing("another-building", "K") == (None, None)


def test_furnished_detection():
    assert listing_is_furnished({"home_features": ["Dishwasher", "Furnished"]})
    assert not listing_is_furnished({"description": "A furnished apartment", "home_features": []})


def test_excluded_units():
    assert unit_is_excluded("the-sierra-chelsea", "7")
    assert unit_is_excluded("the-sierra-chelsea", "8")
    assert not unit_is_excluded("the-sierra-chelsea", "3B")
