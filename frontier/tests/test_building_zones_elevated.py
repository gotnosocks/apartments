import json

import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_elevated as bel
from rentfrontier import building_zones_elevated as bze
from rentfrontier import building_zones_location as bzl

F = bel.frontage


def _lonlat(x, y):
    return F.LON0 + np.asarray(x) / F.M_PER_LON, F.LAT0 + np.asarray(y) / F.M_PER_LAT


def _square(x0, y0, side):
    """A GeoJSON square `side` metres wide with its corner at (x0, y0) metres."""
    xs = [x0, x0 + side, x0 + side, x0, x0]
    ys = [y0, y0, y0 + side, y0 + side, y0]
    lon, lat = _lonlat(xs, ys)
    ring = [[float(a), float(b)] for a, b in zip(lon, lat)]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


def test_columns_flag_within_front_m():
    frame = pd.DataFrame({"building": ["a", "b", "c", "d"]})
    t = pd.DataFrame({"building": ["a", "b", "c"], "elevated_m": [12.0, 30.0, np.nan]})
    np.testing.assert_array_equal(bze.columns(frame, t)[:, 0], [1, 0, 0, 0])


def _feed():
    """A line along y = 0 from x = 0 to 3,000 m with stops every 1,000 m: underground, then
    three elevated stops."""
    xs = np.arange(0.0, 3001.0, 50.0)
    lon, lat = _lonlat(xs, np.zeros_like(xs))
    shapes = pd.DataFrame(
        {
            "shape_id": "s",
            "shape_pt_sequence": np.arange(len(xs)),
            "shape_pt_lat": lat,
            "shape_pt_lon": lon,
        }
    )
    slon, slat = _lonlat([0.0, 1000.0, 2000.0, 3000.0], [0.0] * 4)
    stops = pd.DataFrame(
        {
            "stop_id": ["A1N", "A2N", "A3N", "A4N"],
            "stop_lat": slat,
            "stop_lon": slon,
        }
    )
    stop_times = pd.DataFrame(
        {"trip_id": "t", "stop_id": stops.stop_id, "stop_sequence": [1, 2, 3, 4]}
    )
    trips = pd.DataFrame({"trip_id": ["t"], "shape_id": ["s"]})
    stations = pd.DataFrame(
        {
            "gtfs_stop_id": ["A1", "A2", "A3", "A4"],
            "structure": ["Subway", "Elevated", "Viaduct", "Elevated"],
        }
    )
    return stations, trips, stop_times, stops, shapes


def test_track_points_keep_elevated_stretches_only():
    pts = bel.track_points(*_feed())
    assert pts[:, 0].min() > 990.0
    assert pts[:, 0].max() < 3010.0
    assert np.abs(pts[:, 1]).max() < 1.0
    assert np.diff(np.sort(pts[:, 0])).max() <= bel.STEP_M + 1e-6


def test_table_measures_outline_to_track():
    registry = pd.DataFrame(
        {
            "building": ["under", "tunnel", "nofoot"],
            "bin": [1000001.0, 1000002.0, 1000000.0],
        }
    )
    footprints = pd.DataFrame(
        {
            "bin": [1000001, 1000002],
            "geometry": [_square(1500.0, 15.0, 20.0), _square(500.0, 15.0, 20.0)],
        }
    )
    t = bel.table(registry, footprints, bel.track_points(*_feed()))
    t = t.set_index("building").elevated_m
    assert 14.0 < t["under"] < 16.0
    assert t["tunnel"] > 450.0
    assert np.isnan(t["nofoot"])


def test_design_appends_elevated():
    frame, tables, units, trucks, floors, _ = tbf._design()
    blds = frame.building.astype(str).unique()
    n = len(blds)
    loc = dict(
        transit=pd.DataFrame(
            {
                "building": blds,
                "station_km": np.linspace(0.1, 1.2, n),
                "routes_800m": np.arange(n) % 7,
            }
        ),
        parks=pd.DataFrame(
            {
                "building": blds,
                "park_km": np.linspace(0.02, 0.9, n),
                "big_park_km": np.linspace(0.5, 3.0, n),
                "water_km": np.linspace(3.0, 0.1, n),
            }
        ),
        noise=pd.DataFrame(
            {"building": blds, "noise_per_year": np.linspace(0, 300, n)}
        ),
    )
    kw = dict(
        units=units,
        trucks=trucks,
        gyms=tbf.tby.gyms_for(frame),
        ages=tbf.tbs.ages_for(frame),
        floors=floors,
        **tables,
    )
    t = pd.DataFrame(
        {"building": blds, "elevated_m": np.where(np.arange(n) % 4 == 0, 15.0, 300.0)}
    )
    m = bzl.design(frame, **loc, **kw)
    d = bze.design(frame, elevated=t, **loc, **kw)
    assert d.names == list(m.names) + list(bze.COLUMNS)
    np.testing.assert_array_equal(d.x[:, : len(m.names)], m.x)
    np.testing.assert_array_equal(d.x[:, -1:], bze.columns(frame, t))
    assert 0 < d.x[:, -1].sum() < len(frame)
    for s in np.unique(d.site):
        assert np.ptp(d.x[d.site == s, -1]) == 0
