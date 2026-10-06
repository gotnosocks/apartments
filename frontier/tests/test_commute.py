from rentfrontier import commute


def test_station_trips_counts_boardings_and_takes_the_quickest():
    # A -(line 1)- B -(line 2)- C, and a slow one-seat line 3 from A to C.
    edges = {
        "A": [(("A", "1", "0"), 2.0), (("A", "3", "0"), 1.0)],
        ("A", "1", "0"): [(("B", "1", "0"), 3.0)],
        ("B", "1", "0"): [("B", 0.0)],
        "B": [(("B", "2", "0"), 2.0)],
        ("B", "2", "0"): [(("C", "2", "0"), 3.0)],
        ("C", "2", "0"): [("C", 0.0)],
        ("A", "3", "0"): [(("C", "3", "0"), 20.0)],
        ("C", "3", "0"): [("C", 0.0)],
    }
    trips = commute.station_trips(edges, {"C": 1.0})
    assert trips["C"] == (1.0, 0)
    assert trips["B"] == (6.0, 1)
    assert trips["A"] == (11.0, 2)


def test_destinations_config_names_the_office():
    places = commute.destinations()
    assert "office" in places.index
    assert {"address", "latitude", "longitude"} <= set(places.columns)
