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


def test_unsupported_designs_are_named():
    from rentfrontier import model

    assert rentmap.unsupported_terms(model.MODELS["m5-nocurves"]) == []
    assert rentmap.unsupported_terms(model.MODELS["m0q-btrend"]) == []
    assert "no building walk or trend" in rentmap.unsupported_terms(model.MODELS["m0q"])
    # Bedroom-group market curves are modelled: each group's map adds its curve.
    assert rentmap.unsupported_terms(model.MODELS["m5-quarterly"]) == []
    assert (
        rentmap.unsupported_terms(
            model.MODELS["m7-nocurves-floorslope-bednoise-dayfourier-bedtime"]
        )
        == []
    )
    m1 = rentmap.unsupported_terms(model.MODELS["m1-btrend-walk24"])
    assert "both a walk and a trend" in m1
    assert "sum-to-zero, masked or anchored walks" in rentmap.unsupported_terms(
        model.MODELS["m1-walk36-zs"]
    )


def test_clip_ring_and_thin():
    # A 4 x 4 square centred on a 2 x 2 window clips to the window.
    square = [(-2, -2), (2, -2), (2, 2), (-2, 2)]
    clipped = rentmap._clip_ring(square, -1, 1, -1, 1)
    assert sorted(clipped) == [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    # A ring wholly outside clips to nothing.
    assert rentmap._clip_ring([(5, 5), (6, 5), (6, 6)], -1, 1, -1, 1) == []
    # Thinning keeps the ends and drops points closer than the step.
    line = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (3.0, 0.0), (3.2, 0.0)]
    assert rentmap._thin(line, step=1.5) == [(0.0, 0.0), (3.0, 0.0), (3.2, 0.0)]


def test_designs_with_building_slopes_are_mapped():
    import numpy as np
    from rentfrontier import model

    assert rentmap.unsupported_terms(model.MODELS["m7-nocurves-2slopes"]) == []
    rng = np.random.default_rng(0)
    fslope = rng.normal(size=(4, 3, 2))  # draws, buildings, slopes
    x = rng.normal(size=(3, 5))  # buildings, features
    got = rentmap.feature_slope_term(fslope, x, [1, 4])
    want = np.array([[fslope[d, b] @ x[b, [1, 4]] for b in range(3)] for d in range(4)])
    np.testing.assert_allclose(got, want)


def test_area_name_lists_the_fit_neighbourhoods():
    from rentfrontier import rentmap

    assert rentmap.area_name(["Chelsea", "Chelsea"]) == "Chelsea"
    assert rentmap.area_name(["West Village", "Chelsea"]) == "Chelsea and West Village"
    assert rentmap.area_name(["C", "A", "B"]) == "A, B and C"


def test_building_hoods_follow_the_fit_rows():
    frame = pd.DataFrame(
        {
            "building": ["a", "b", "a", "a", "c"],
            "neighbourhood": [
                "West Village",
                "West Village",
                "Chelsea",
                "Chelsea",
                "Chelsea",
            ],
        }
    )
    # a's first row is held out: its fit rows say Chelsea.
    heldout = np.array([True, False, False, False, True])
    hoods = rentmap.building_hoods(frame, heldout, ["a", "b"])
    assert list(hoods) == ["Chelsea", "West Village"]
    no_hood = rentmap.building_hoods(frame[["building"]], heldout, ["a", "b"])
    assert list(no_hood) == ["Chelsea", "Chelsea"]
