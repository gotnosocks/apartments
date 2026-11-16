"""The building model with L1TKN's unit and row settings and no lease phases
(`rentfrontier.drift_building_unitkn`)."""

import hashlib

import numpy as np
import test_drift as td

from rentfrontier import (
    building_zones,
    drift,
    drift_building,
    drift_building_phase_unitkn,
    run,
)
from rentfrontier import drift_building_unitkn as m

# The sha256 of every traced and kept array of the run below on the CPU, as drawn when
# drift-building-unitkn was added. A deliberate change to the model's draws changes it.
RUN_SHA256 = "3809e6244267b9352c044bdc756b64d70dc0cfcdb04a2aa04591f20d6bc55114"


def _run():
    train, _, _ = td._split(td._design(n=400, per_unit=9))
    return m.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda s: None,
    )


def test_a_run_draws_what_it_drew_when_the_model_was_added():
    out = _run()
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == RUN_SHA256


def test_a_run_holds_nu_and_traces_no_phase_or_unit_dof():
    out = _run()
    assert not any("phase" in k for k in out["trace"])
    assert "unit_dof" not in out["trace"] and "unit_dof" not in out["kept"]
    np.testing.assert_array_equal(out["trace"]["nu"], m.ROW_DOF)


def test_the_model_is_the_building_model_with_l1tkn_settings():
    assert m.design is drift_building.design
    assert m.GROUPS == drift_building.GROUPS
    assert m.LEVEL_DOF == drift_building.LEVEL_DOF
    assert (m.UNIT_DOF, m.ROW_DOF) == (
        drift_building_phase_unitkn.UNIT_DOF,
        drift_building_phase_unitkn.ROW_DOF,
    )
    assert (
        '("drift-building-unitkn", "drift_building_unitkn")'
        in open(run.__file__).read()
    )
    rec = m.run_record(td._design(n=300))
    assert rec["row_dof_fixed"] == 2.0 and rec["unit_t"]["unit_dof"] == 3.0
    assert "phase" not in rec
