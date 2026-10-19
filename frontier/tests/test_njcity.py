import io
import zipfile

import pytest

from rentfrontier import njcity


def _feed():
    files = {
        "routes.txt": "route_id,route_short_name,route_long_name,route_type\n"
        "R1,HBLR,Hudson-Bergen Light Rail,0\nR2,,Hoboken Ferry,4\n",
        "trips.txt": "route_id,service_id,trip_id\nR1,S,T1\nR2,S,T2\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n"
        "A,Newport,40.7268,-74.0362\nB,Far Away,40.10,-74.50\nC,Unserved,40.73,-74.03\n",
        "stop_times.txt": "trip_id,stop_id,stop_sequence\nT1,A,1\nT2,A,1\nT1,B,2\n",
    }
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return blob.getvalue()


def test_stops_keep_served_stops_in_the_box_with_their_routes():
    table = njcity.stops("test", _feed())
    assert table.stop_id.tolist() == ["A"]
    assert table.routes.iloc[0] == "HBLR,Hoboken Ferry"
    assert table["mode"].iloc[0] == "light rail"


def test_stitch_joins_open_ways_into_a_ring():
    a, b, c, d = [0, 0], [1, 0], [1, 1], [0, 1]
    rings = njcity.stitch([[a, b], [c, b], [c, d, a]])
    assert len(rings) == 1 and rings[0][0] == rings[0][-1] and len(rings[0]) == 5
    assert njcity.stitch([[a, b], [c, d]]) == []


def test_outline_of_a_relation_puts_the_hole_in_its_outer_ring():
    def way(role, points):
        return {
            "type": "way",
            "role": role,
            "geometry": [{"lon": x, "lat": y} for x, y in points],
        }

    side = 0.001
    outer = [(0, 40), (side, 40), (side, 40 + side), (0, 40 + side), (0, 40)]
    q = side / 4
    inner = [(q, 40 + q), (3 * q, 40 + q), (3 * q, 40 + 3 * q), (q, 40 + q)]
    relation = {
        "type": "relation",
        "members": [way("outer", outer), way("inner", inner)],
    }
    g = njcity.outline(relation)
    assert g["type"] == "MultiPolygon" and len(g["coordinates"][0]) == 2
    full = njcity.acres({"type": "Polygon", "coordinates": [[list(p) for p in outer]]})
    # 0.001 degrees square at 40 N: about 111 m by 85 m.
    assert full == pytest.approx(111.32 * 85.28 / 4046.86, rel=0.01)
    assert njcity.acres(g) == pytest.approx(full * (1 - 1 / 8), rel=0.01)
