import numpy as np
import pandas as pd
from rentfrontier import rentmap


def test_year_weights_average_the_interpolated_walk():
    periods = pd.date_range("2010-01-01", "2011-03-01", freq="MS")  # 15 months
    years, by_year, walk_year = rentmap.year_weights(periods, spacing=6)
    assert list(years) == [2010, 2011]
    np.testing.assert_allclose(by_year.sum(1), 1.0)
    rng = np.random.default_rng(0)
    w = rng.normal(size=(3, walk_year.shape[0]))  # (buildings, knots)
    months = np.arange(len(periods))
    knot, frac = months // 6, (months % 6) / 6
    monthly = (1 - frac) * w[:, knot] + frac * w[:, knot + 1]  # (buildings, months)
    np.testing.assert_allclose(w @ walk_year, monthly @ by_year.T)


def test_grid_layout_puts_streets_up_and_avenues_across():
    # Two buildings on each of W 14 St and W 23 St, and two on each of 8th and
    # 9th Avenue, placed on a grid rotated 29 degrees east of north.
    phi = np.radians(rentmap.GRID_BEARING_DEG)
    lat0, lon0, m = 40.745, -74.0, 111_320.0

    def place(across, up, label):
        east = across * np.cos(phi) + up * np.sin(phi)
        north = -across * np.sin(phi) + up * np.cos(phi)
        lat = lat0 + north / m
        lon = lon0 + east / (m * np.cos(np.radians(lat0)))
        return {"label": label, "lat": float(lat), "lon": float(lon)}

    buildings = [
        place(0, -500, "100 West 14 Street"),
        place(100, -500, "120 West 14 Street"),
        place(0, 300, "100 West 23 Street"),
        place(100, 300, "120 West 23 Street"),
        place(-50, -200, "200 8 Avenue"),
        place(-50, 100, "300 8 Avenue"),
        place(-300, -200, "200 9 Avenue"),
        place(-300, 100, "300 9 Avenue"),
    ]
    grid = rentmap.grid_layout(buildings)
    streets = {s["label"]: s["y"] for s in grid["streets"]}
    avenues = {a["label"]: a["x"] for a in grid["avenues"]}
    assert streets["W 23 St"] - streets["W 14 St"] > 700
    assert avenues["8th Av"] - avenues["9th Av"] > 200
    ys = [b["y"] for b in buildings[:2]]
    assert abs(ys[0] - ys[1]) < 1.0  # same street, same height
