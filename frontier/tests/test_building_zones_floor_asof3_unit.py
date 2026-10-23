import dataclasses

import numpy as np
import pytest
import test_building_zones_age as tbs
import test_building_zones_attrs as tba
import test_building_zones_floor_asof as tbfa
import test_building_zones_unit as tbu

from rentfrontier import building_zones, splits
from rentfrontier import building_zones_attrs as bza
from rentfrontier import building_zones_floor_asof2 as asof2
from rentfrontier import building_zones_floor_asof3 as asof3
from rentfrontier import building_zones_floor_asof3_unit as bzu3
from rentfrontier import building_zones_gibbs as bzg


def test_design_numbers_the_training_units(tmp_path, monkeypatch):
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
    a, b = bzu3.design(frame, **kw), asof3.design(frame, **kw)
    assert a.names == b.names
    np.testing.assert_array_equal(a.x, b.x)
    key = (frame.building.astype(str) + "|" + frame.unit_id.astype(str)).to_numpy()
    train = sorted(set(key[~held]))
    assert a.units == len(train)
    want = np.array([train.index(k) if k in train else -1 for k in key])
    np.testing.assert_array_equal(a.unit, want)
    assert (a.unit[~held] >= 0).all()
    t = bzu3.subset(a, ~held)
    np.testing.assert_array_equal(t.unit, a.unit[~held])
    assert t.units == a.units
    rec = bzu3.run_record(a)
    assert rec["asof"]["pipeline_rows"] == str(tmp_path / "rows.parquet")
    assert rec["unit_effect"]["units"] == a.units


@pytest.mark.parametrize("joint", [False, True])
def test_recovers_a_planted_unit_sd(monkeypatch, joint):
    reg = tba.registry_with_bins()
    footprints, attrs = tba.tables_of(reg)
    frame = tba._nyc_frame(6000, 30, 9)
    d = bza.design(
        frame, registry=reg, nj_registry=tba.NO_NJ, attrs=attrs, footprints=footprints
    )
    d = bza.subset(d, np.ones(len(d.y), bool))
    d = tba._simulated(d)
    # Units of about four rows inside each building, with effects of sd 0.15.
    rng = np.random.default_rng(4)
    order = np.argsort(d.site, kind="stable")
    rank = np.empty(len(order), int)
    rank[order] = np.arange(len(order))
    first = np.r_[0, np.flatnonzero(np.diff(d.site[order])) + 1]
    start = np.repeat(first, np.diff(np.r_[first, len(order)]))
    unit_sorted = d.site[order] * 1000 + (np.arange(len(order)) - start) // 4
    _, unit = np.unique(unit_sorted[rank], return_inverse=True)
    truth = 0.15
    v = truth * rng.standard_normal(unit.max() + 1)
    d = bzu3.Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(d)},
        unit=unit,
        units=int(unit.max() + 1),
    )
    d = dataclasses.replace(d, y=d.y + v[unit])
    monkeypatch.setattr(bzu3, "gp_spec", lambda names: [])
    out = bzu3.run(
        d,
        building_zones.Priors(),
        bzg.Settings(chains=2, warmup=100, draws=300, keep_every=5, joint_amp=joint),
        log=lambda m: None,
    )
    su = out["trace"]["unit_sd"]
    assert su.shape == (2, 300) and np.ptp(su) > 0
    lo, hi = np.quantile(su, [0.001, 0.999])
    assert lo < truth < hi, (lo, hi)
    assert 0.1 < np.median(su) < 0.2
    mean = bzu3.unit_offset(d, out["kept"])
    assert np.corrcoef(mean, v[unit])[0, 1] > 0.5
    var = out["kept"]["unit_var"]
    assert var.shape == (2, d.units) and (var > 0).all()
