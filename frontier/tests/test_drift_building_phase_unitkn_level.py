"""L1TKN with L2's phase levels (`rentfrontier.drift_building_phase_unitkn_level`)."""

import hashlib

import numpy as np
import test_drift as td
import test_drift_building_phase as tp

from rentfrontier import (
    building_zones,
    drift,
    drift_building_phase_level,
    drift_building_phase_unitkn,
    drift_pool,
    run,
)
from rentfrontier import drift_building_phase_unitkn_level as m

# The sha256 of every traced and kept array of the run below on the CPU, as drawn when
# drift-building-phase-unitkn-level was added. A deliberate change to the model's draws
# changes it.
UNITKN_LEVEL_RUN_SHA256 = (
    "26bd66185b2b36cc303f12613df3365e4016198b9a0346e331d6a8a6143aff22"
)


def test_a_run_draws_what_it_drew_when_the_model_was_added():
    train, _, _ = td._split(m.phase_levels(tp._phased(n=400, per_unit=9)))
    out = m.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda s: None,
    )
    assert (np.asarray(out["kept"]["nu"]) == m.ROW_DOF).all()
    names = list(train.names)
    rows = m.diagnostics(out["trace"], names)["per_quantity"]
    assert "nu" not in rows and {"unit_sd", "drift_sd", "sigma[1]"} <= set(rows)
    # The phase coefficients are among the kept global coefficients.
    assert set(m.LEVELS) <= set(names)
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == UNITKN_LEVEL_RUN_SHA256, h.hexdigest()


def test_the_model_is_l1tkn_with_l2s_design():
    base = drift_building_phase_unitkn
    assert m.NAME == "drift-building-phase-unitkn-level"
    assert m.run is base.run and m.design is drift_building_phase_level.design
    assert m.UNIT_DOF == base.UNIT_DOF and m.ROW_DOF == base.ROW_DOF
    assert m.LEVEL_DOF == base.LEVEL_DOF and m.GROUPS == base.GROUPS
    assert m.diagnostics is base.diagnostics and m.gp_spec is base.gp_spec
    assert (
        '("drift-building-phase-unitkn-level", "drift_building_phase_unitkn_level")'
        in open(run.__file__).read()
    )
    assert (
        drift_pool.model_diagnostics({"model": {"name": m.NAME}}) is drift.diagnostics
    )
    d = m.phase_levels(tp._phased(n=300))
    rec = m.run_record(d)
    assert rec["phase"] == drift_building_phase_level.run_record(d)["phase"]
    assert rec["phase"]["levels"] == list(m.LEVELS)
    assert rec["unit_t"] == base.run_record(d)["unit_t"]
    assert rec["row_dof_fixed"] == 2.0
