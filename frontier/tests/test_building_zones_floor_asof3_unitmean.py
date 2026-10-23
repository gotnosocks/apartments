import numpy as np
import pandas as pd
import test_building_zones_age as tbs
import test_building_zones_floor_asof as tbfa
import test_building_zones_unit as tbu

from rentfrontier import building_zones_floor_asof2 as asof2
from rentfrontier import building_zones_floor_asof3 as asof3
from rentfrontier import building_zones_floor_asof3_unit as bzu3
from rentfrontier import building_zones_floor_asof3_unitmean as bzm
from rentfrontier import splits


def test_unit_means_average_training_rows_and_fall_back_to_the_row():
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "a", "a", "b", "b"],
            "unit_id": ["1", "1", "1", "2", None, "3"],
        }
    )
    x = np.array([[1.0], [0.0], [5.0], [2.0], [7.0], [4.0]])
    train = np.array([True, True, False, False, True, False])
    g = bzm.unit_groups(frame)
    assert g[0] == g[1] == g[2] and len(set(g)) == 4
    m = bzm.unit_means(x, g, train)
    # Unit a|1 averages its two training rows, the held-out row included; a|2 and b|3 have
    # no training row and the row with no unit_id stands alone, so each keeps its own value.
    np.testing.assert_allclose(m[:, 0], [0.5, 0.5, 0.5, 2.0, 7.0, 4.0])


def test_design_appends_the_training_unit_means(tmp_path, monkeypatch):
    frame, tables, units, trucks = tbu._design()
    tables.pop("attrs")
    ads = tbfa.ads_for(frame)
    ads.to_parquet(tmp_path / "rows.parquet")
    monkeypatch.setattr(asof3, "ROWS", tmp_path / "rows.parquet")
    monkeypatch.setattr(asof2, "ROWS", tmp_path / "missing.parquet")
    held = splits.latest_split(frame)
    kw = dict(
        held=held,
        amenities=tbfa.amenities_for(ads),
        lots=tbfa.lots_for(frame),
        units=units,
        trucks=trucks,
        ages=tbs.ages_for(frame),
        **tables,
    )
    a, b = bzm.design(frame, **kw), bzu3.design(frame, **kw)
    k = len(b.names)
    assert a.names[:k] == b.names
    np.testing.assert_array_equal(a.x[:, :k], b.x)
    np.testing.assert_array_equal(a.unit, b.unit)
    added = a.names[k:]
    assert added and all(n.startswith(bzm.PREFIX) for n in added)
    key = (frame.building.astype(str) + "|" + frame.unit_id.astype(str)).to_numpy()
    for j, n in enumerate(added):
        col = b.x[:, b.names.index(n[len(bzm.PREFIX) :])]
        for u in np.unique(key):
            rows = key == u
            tr = rows & ~held
            want = col[tr].mean() if tr.any() else col[rows]
            np.testing.assert_allclose(a.x[rows, k + j], want)
    rec = bzm.run_record(a)
    um = rec["unit_means"]
    assert set(um["columns"]) == set(added)
    assert set(um["rows_off_unit_mean"]) == {n[len(bzm.PREFIX) :] for n in added}
    assert rec["unit_effect"]["units"] == a.units
