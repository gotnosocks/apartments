import numpy as np
import test_building_zones_age as tbs
import test_building_zones_floor_asof as tbfa
import test_building_zones_unit as tbu

from rentfrontier import building_zones_floor_asof2 as asof2
from rentfrontier import building_zones_floor_asof2_cap64 as cap64
from rentfrontier import splits


def test_design_splits_the_top_column():
    frame, tables, units, trucks = tbu._design()
    tables.pop("attrs")
    ads = tbfa.ads_for(frame)
    kw = dict(
        held=splits.latest_split(frame),
        ads=ads,
        amenities=tbfa.amenities_for(ads),
        lots=tbfa.lots_for(frame),
        units=units,
        trucks=trucks,
        ages=tbs.ages_for(frame),
        **tables,
    )
    a, b = cap64.design(frame, **kw), asof2.design(frame, **kw)
    top = [f"unit:elev_f{k}" for k in range(47, 65)]
    assert [n for n in a.names if n not in top] == [
        n for n in b.names if n != "unit:elev_f47"
    ]
    i = [a.names.index(n) for n in top]
    np.testing.assert_array_equal(
        a.x[:, i].sum(1), b.x[:, b.names.index("unit:elev_f47")]
    )
    keep = [a.names.index(n) for n in a.names if n not in top]
    rest = [b.names.index(n) for n in b.names if n != "unit:elev_f47"]
    np.testing.assert_array_equal(a.x[:, keep], b.x[:, rest])
    spec = {s["name"]: s for s in cap64.gp_spec(a.names)}
    assert spec["elev"]["cols"][-1] == "unit:elev_f64"
    assert len(spec["elev"]["cols"]) == 63
    np.testing.assert_allclose(spec["elev"]["x"], np.log(np.arange(2, 65)))
