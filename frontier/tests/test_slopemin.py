from types import SimpleNamespace

import numpy as np
import pandas as pd

from rentfrontier import data, model


def test_slope_only_for_buildings_with_two_well_filled_bedroom_counts():
    # Building 0: 3 studios and 3 two-bedrooms. Building 1: 3 studios and
    # 2 two-bedrooms. Building 2: 6 one-bedrooms.
    building = np.array([0] * 6 + [1] * 5 + [2] * 6)
    beds = np.array([0, 0, 0, 2, 2, 2, 0, 0, 0, 2, 2] + [1] * 6)
    prep = SimpleNamespace(
        buildings=np.array(["a", "b", "c"]),
        train=SimpleNamespace(building=building, beds_centered=beds - 1.0),
    )
    np.testing.assert_array_equal(
        model.bedroom_slope_buildings(prep, 3), [1.0, 0.0, 0.0]
    )
    np.testing.assert_array_equal(
        model.bedroom_slope_buildings(prep, 2), [1.0, 1.0, 0.0]
    )


def test_slopecheck_subset_keeps_the_named_buildings():
    named = sorted(data.SLOPECHECK_BUILDINGS)
    frame = pd.DataFrame({"building": named + ["x-1", "x-2"]})
    out = data.tune_b35_slopecheck_v1(frame)
    assert set(named) <= set(out.building)
    assert set(out.building) - set(named) == {
        b for b in ("x-1", "x-2") if data.in_tuning_subset(b)
    }


def test_slopemin3_differs_from_c_only_in_the_minimum():
    c = model.MODELS[
        "m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope"
    ]
    m = model.MODELS[c.name + "-slopemin3"]
    assert m.bedroom_slope_min_rows == 3
    assert {k for k, v in vars(m).items() if getattr(c, k) != v} == {
        "name",
        "bedroom_slope_min_rows",
    }
