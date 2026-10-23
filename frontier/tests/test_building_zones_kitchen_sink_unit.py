import numpy as np
import pandas as pd
import test_building_zones_attrs as tba

from rentfrontier import building_zones, splits
from rentfrontier import building_zones_attrs as bza
from rentfrontier import building_zones_floor_asof2_cap64 as cap64
from rentfrontier import building_zones_floor_asof2_unit as unit2
from rentfrontier import building_zones_gibbs as bzg
from rentfrontier import building_zones_kitchen_sink as ks
from rentfrontier import building_zones_kitchen_sink_unit as ksu


def _frame_and_design():
    reg = tba.registry_with_bins()
    footprints, attrs = tba.tables_of(reg)
    frame = tba._nyc_frame(600, 30, 9)
    d = bza.design(
        frame, registry=reg, nj_registry=tba.NO_NJ, attrs=attrs, footprints=footprints
    )
    frame = frame.assign(unit_id=(np.arange(len(frame)) % 7).astype(str))
    frame.loc[frame.index[::11], "unit_id"] = None
    return frame, d


def test_design_numbers_the_kitchen_sinks_units(monkeypatch):
    frame, base = _frame_and_design()
    seen = {}

    def fake(frame, start=None, held=None, **kw):
        seen["held"] = held
        return base

    monkeypatch.setattr(ks, "design", fake)
    held = splits.latest_split(frame)
    d = ksu.design(frame, held=held)
    np.testing.assert_array_equal(seen["held"], held)
    np.testing.assert_array_equal(d.x, base.x)
    assert d.names == base.names
    want, units = unit2.unit_index(frame, held)
    np.testing.assert_array_equal(d.unit, want)
    assert d.units == units
    assert (d.unit[frame.unit_id.isna().to_numpy()] == -1).all()
    t = ksu.subset(d, ~held)
    np.testing.assert_array_equal(t.unit, d.unit[~held])


def test_run_gives_the_unit_sweep_the_curves_to_floor_64(monkeypatch):
    names = [f"unit:{g}_f{k}" for g, _ in cap64.GROUPS for k in range(2, 65)]
    got, before = {}, unit2.gp_spec

    def fake(d, priors, settings, log, checkpoint):
        got["gp"] = unit2.gp_spec(names)
        return "out"

    monkeypatch.setattr(unit2, "run", fake)
    assert ksu.run(None, building_zones.Priors(), bzg.Settings()) == "out"
    caps = {g["name"]: len(g["cols"]) + 1 for g in got["gp"]}
    assert caps == dict(cap64.GROUPS)
    assert unit2.gp_spec is before


def test_run_puts_the_cap_47_curves_back_after_a_failure(monkeypatch):
    before = unit2.gp_spec

    def fake(*a):
        raise RuntimeError("boom")

    monkeypatch.setattr(unit2, "run", fake)
    try:
        ksu.run(None, building_zones.Priors(), bzg.Settings())
    except RuntimeError:
        pass
    assert unit2.gp_spec is before


def test_record_adds_the_unit_effects(monkeypatch):
    monkeypatch.setattr(ks, "run_record", lambda d: {"kitchen_sink": {}})
    d = pd.Series({"units": 12})
    rec = ksu.run_record(d)
    assert rec["unit_effect"]["units"] == 12 and "kitchen_sink" in rec
