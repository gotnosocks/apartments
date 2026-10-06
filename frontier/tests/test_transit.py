import zipfile

import numpy as np
import pandas as pd
import pytest
from rentfrontier import features, transit


def _gtfs(path):
    """A line A - B - 127 (Times Sq) every 6 min, 2 min a hop, and a transfer
    from C to B of 3 min."""
    stops = (
        "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
        + "".join(
            f"{s},{s} St,40.7{i},-73.99,1,\n{s}N,{s} St,40.7{i},-73.99,,{s}\n"
            for i, s in enumerate(("A", "B", "127", "C"))
        )
    )
    trips = "route_id,trip_id,service_id,direction_id\n" + "".join(
        f"1,t{k},WKD,0\n" for k in range(4)
    )
    times = "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n" + "".join(
        f"t{k},{s}N,08:{6 * k + 2 * j:02d}:00,08:{6 * k + 2 * j:02d}:00,{j}\n"
        for k in range(4)
        for j, s in enumerate(("A", "B", "127"))
    )
    files = {
        "stops.txt": stops,
        "trips.txt": trips,
        "stop_times.txt": times,
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,"
        "sunday,start_date,end_date\nWKD,1,1,1,1,1,0,0,20260101,20261231\n",
        "transfers.txt": "from_stop_id,to_stop_id,transfer_type,min_transfer_time\n"
        "C,B,2,180\n",
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return str(path)


def test_station_minutes_waits_rides_and_transfers(tmp_path):
    edges, stations = transit.network(_gtfs(tmp_path / "g.zip"))
    assert set(stations.index) == {"A", "B", "127", "C"}
    minutes = transit.station_minutes(edges, ["127"])
    # Half the 6-minute headway to board, then 2 minutes a hop.
    assert minutes["127"] == 0
    assert minutes["B"] == pytest.approx(3 + 2)
    assert minutes["A"] == pytest.approx(3 + 4)
    assert minutes["C"] == pytest.approx(3 + minutes["B"])


def test_midtown_minutes_as_of_the_month(monkeypatch):
    tables = {
        frozenset(): pd.DataFrame({"midtown_min": [5.0, 9.0]}, index=["x", "y"]),
        frozenset({"726"}): pd.DataFrame(
            {"midtown_min": [5.0, 14.0]}, index=["x", "y"]
        ),
    }
    monkeypatch.setattr(transit, "building_transit", lambda exclude: tables[exclude])
    frame = pd.DataFrame(
        {"building": ["x", "y", "y"], "period": ["2015-08", "2015-08", "2015-10"]}
    )
    np.testing.assert_allclose(transit.midtown_minutes(frame), [5.0, 14.0, 9.0])
    assert features.stops_not_open("2015-08") == frozenset({"726"})


def test_every_parent_of_a_complex_is_midtown():
    assert {"127", "725", "902", "R16", "631", "723", "901", "D17", "R17"} <= set(
        transit.MIDTOWN
    )
    edges = {"X": [("R16", 4.0)], "Y": [("127", 6.0)]}
    minutes = transit.station_minutes(edges, list(transit.MIDTOWN))
    assert minutes["X"] == 4.0 and minutes["Y"] == 6.0
