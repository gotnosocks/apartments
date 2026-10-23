import numpy as np
import test_building_zones_age as tbs
import test_building_zones_floor_asof as tbfa
import test_building_zones_unit as tbu

from rentfrontier import building_zones_floor_asof as bzfa
from rentfrontier import building_zones_floor_asof2 as asof2
from rentfrontier import building_zones_floor_asof3 as asof3
from rentfrontier import splits


def test_rows_are_the_b3ddebf_build():
    assert asof3.ROWS.name == "rows-b3ddebf19af1dc1e.parquet"
    assert asof3.NAME == "building-zones-floor-asof3"


def test_design_reads_its_own_rows(tmp_path, monkeypatch):
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
    assert asof3.run is bzfa.run
    a, b = asof3.design(frame, **kw), asof2.design(frame, ads=ads, **kw)
    assert list(a.names) == list(b.names)
    np.testing.assert_array_equal(a.x, b.x)
    np.testing.assert_array_equal(a.y, b.y)
    rec = asof3.run_record(a)
    assert rec["asof"]["pipeline_rows"] == str(tmp_path / "rows.parquet")
