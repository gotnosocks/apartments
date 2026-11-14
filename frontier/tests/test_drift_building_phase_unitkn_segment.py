"""L1TKN with the segments' paths (`rentfrontier.drift_building_phase_unitkn_segment`)."""

import hashlib

import numpy as np
import test_drift as td
import test_drift_building_phase as tp

from rentfrontier import (
    building_zones,
    drift,
    drift_building_phase_segment,
    drift_building_phase_unitkn,
    drift_pool,
    run,
)
from rentfrontier import drift_building_phase_unitkn_segment as m

SETTINGS = drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3)


def _train():
    full = m.segment_paths(tp._phased(n=400, weeks=260, per_unit=9))
    return td._split(full)[0]


def _sha256(out):
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    return h.hexdigest()


# The sha256 of every traced and kept array of the run below on the CPU, as drawn when
# drift-building-phase-unitkn-segment was added. A deliberate change to the model's draws
# changes it.
UNITKN_SEGMENT_RUN_SHA256 = (
    "101484a7fa396718cf4921d3d3b95a859df0926b12ef81c5f61cb568062ea0be"
)


def test_a_run_draws_what_it_drew_when_the_model_was_added():
    train = _train()
    out = m.run(train, building_zones.Priors(), SETTINGS, log=lambda s: None)
    assert (np.asarray(out["kept"]["nu"]) == m.ROW_DOF).all()
    names = list(train.names)
    rows = m.diagnostics(out["trace"], names)["per_quantity"]
    assert "nu" not in rows and {"unit_sd", "drift_sd", "sigma[1]"} <= set(rows)
    segments = m.segment_names(train)
    assert {f"gp_amp[seg:{s}]" for s in segments} <= set(rows)
    assert {f"gp_ls[seg:{s}]" for s in segments} <= set(rows)
    assert len(m.summarize(out["kept"], names)["segment_gp"]) == 2 * len(segments)
    assert _sha256(out) == UNITKN_SEGMENT_RUN_SHA256, _sha256(out)


def test_the_model_is_l1tkn_with_the_segment_models_design_and_processes():
    base = drift_building_phase_unitkn
    seg = drift_building_phase_segment
    assert m.NAME == "drift-building-phase-unitkn-segment"
    assert m.design is seg.design and m.gp_spec is seg.gp_spec
    assert m.diagnostics is seg.diagnostics and m.summarize is seg.summarize
    assert m.UNIT_DOF == base.UNIT_DOF and m.ROW_DOF == base.ROW_DOF
    assert m.LEVEL_DOF == base.LEVEL_DOF and m.GROUPS == base.GROUPS
    assert "drift_building_phase_unitkn_segment" in open(run.__file__).read()
    assert drift_pool.model_diagnostics({"model": {"name": m.NAME}}) is seg.diagnostics
    d = m.segment_paths(tp._phased(n=1200, weeks=260))
    rec = m.run_record(d)
    assert rec["segments"] == seg.run_record(d)["segments"]
    assert rec["unit_t"] == base.run_record(d)["unit_t"]
    assert rec["row_dof_fixed"] == 2.0
