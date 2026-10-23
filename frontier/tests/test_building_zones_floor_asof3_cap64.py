import numpy as np
import test_building_zones_age as tbs
import test_building_zones_floor_asof as tbfa
import test_building_zones_unit as tbu

from rentfrontier import building_zones_floor_asof2 as asof2
from rentfrontier import building_zones_floor_asof2_cap64 as cap64
from rentfrontier import building_zones_floor_asof3 as asof3
from rentfrontier import building_zones_floor_asof3_cap64 as asof3_cap64
from rentfrontier import splits


def test_design_reads_asof3_rows_with_the_cap(tmp_path, monkeypatch):
    frame, tables, units, trucks = tbu._design()
    tables.pop("attrs")
    ads = tbfa.ads_for(frame)
    ads.to_parquet(tmp_path / "rows.parquet")
    monkeypatch.setattr(asof3, "ROWS", tmp_path / "rows.parquet")
    monkeypatch.setattr(asof2, "ROWS", tmp_path / "missing.parquet")
    kw = dict(
        held=splits.latest_split(frame),
        amenities=tbfa.amenities_for(ads),
        lots=tbfa.lots_for(frame),
        units=units,
        trucks=trucks,
        ages=tbs.ages_for(frame),
        **tables,
    )
    assert asof3_cap64.NAME == "building-zones-floor-asof3-cap64"
    assert asof3_cap64.run is cap64.run
    a, b = asof3_cap64.design(frame, **kw), cap64.design(frame, ads=ads, **kw)
    assert list(a.names) == list(b.names)
    assert "unit:elev_f64" in a.names
    np.testing.assert_array_equal(a.x, b.x)
    np.testing.assert_array_equal(a.y, b.y)
    rec = asof3_cap64.run_record(a)
    assert rec["asof"]["pipeline_rows"] == str(tmp_path / "rows.parquet")
    assert rec["floor_gp"]["caps"] == {"elev": 64, "walkup": 6}
