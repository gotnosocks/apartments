import dataclasses

import numpy as np
import test_building_zones_age as tbs
import test_building_zones_floor_asof as tbfa
import test_building_zones_unit as tbu

from rentfrontier import building_zones_floor_asof as bzfa
from rentfrontier import building_zones_floor_asof_amp1 as amp1
from rentfrontier import splits


def test_priors_differ_only_in_amp():
    base = dataclasses.asdict(bzfa.Priors())
    new = dataclasses.asdict(amp1.Priors())
    assert base.keys() == new.keys()
    assert {k for k in base if base[k] != new[k]} == {"amp"}
    assert new["amp"] == 1.0
    assert amp1.Priors().to_dict()["amp"] == 1.0


def test_design_matches_the_base():
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
    assert amp1.NAME == "building-zones-floor-asof-amp1"
    assert amp1.run is bzfa.run
    a, b = amp1.design(frame, **kw), bzfa.design(frame, **kw)
    assert list(a.names) == list(b.names)
    np.testing.assert_array_equal(a.x, b.x)
    np.testing.assert_array_equal(a.y, b.y)
