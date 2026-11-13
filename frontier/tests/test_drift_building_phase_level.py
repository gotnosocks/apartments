"""L1 with a level in the mean for each lease phase
(`rentfrontier.drift_building_phase_level`)."""

import dataclasses
import hashlib

import numpy as np
import test_drift as td
import test_drift_building_phase as tp

from rentfrontier import (
    building_zones,
    drift,
    drift_building,
    drift_building_phase,
    drift_building_phase_level,
    run,
)

P = drift_building_phase.PHASES
LEVELS = drift_building_phase_level.LEVELS


def test_each_phase_after_the_reference_gets_a_column_set_on_its_rows():
    d = tp._phased(n=300)
    out = drift_building_phase_level.phase_levels(d)
    assert LEVELS == tuple(f"phase:{p}" for p in P[1:])
    assert out.names == d.names + list(LEVELS)
    np.testing.assert_array_equal(out.x[:, : len(d.names)], d.x)
    cols = out.x[:, len(d.names) :]
    np.testing.assert_array_equal(cols.sum(axis=1), d.phase != 0)
    for j, n in enumerate(LEVELS):
        np.testing.assert_array_equal(cols[:, j], d.phase == j + 1)
        assert out.count[n] == int((d.phase == j + 1).sum())
    # The levels are global coefficients, drawn outside the slow block.
    assert not any(n.startswith(drift.Settings().slow_columns) for n in LEVELS)
    # A phase with no rows adds no column.
    none = dataclasses.replace(d, phase=np.where(d.phase == 2, 0, d.phase))
    assert "phase:0-2" not in drift_building_phase_level.phase_levels(none).names


def test_the_rows_to_predict_carry_their_phase_columns():
    full = drift_building_phase_level.phase_levels(tp._phased(n=300))
    train, _, held = td._split(full)
    np.testing.assert_array_equal(train.pred["x"], full.x[held])
    np.testing.assert_array_equal(train.pred["phase"], full.phase[held])


def _planted_run(levels, seed=3):
    """A short run of L2 on a phased design with `levels` added to the asks of each phase
    after the reference, one value for each column of `LEVELS`."""
    full = drift_building_phase_level.phase_levels(tp._phased(n=1200, per_unit=6))
    shift = np.r_[0.0, levels][full.phase]
    full = dataclasses.replace(full, y=full.y + shift)
    train, _, _ = td._split(full)
    out = drift_building_phase_level.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=150, draws=60, level_dof=4.0, seed=seed),
        log=lambda m: None,
    )
    return full, out


def test_a_run_recovers_planted_phase_levels():
    planted = np.array([0.0, -0.15, -0.05, 0.05, 0.1, 0.2])
    full, out = _planted_run(planted)
    beta = out["kept"]["beta"].reshape(-1, len(full.names))
    got = beta[:, [full.names.index(n) for n in LEVELS]].mean(axis=0)
    np.testing.assert_allclose(got, planted, atol=0.06)
    # L1's noise factors are still drawn, beside the levels.
    assert out["kept"]["phase_scale"].shape[-1] == len(P)


# The sha256 of every traced and kept array of the run below on the CPU, as drawn when the
# phase levels were added. A deliberate change to L2's draws changes it.
LEVEL_RUN_SHA256 = "b25bde6e3f5c76907f435030a439404036b108ae7e904faa5b8c327df712f148"


def test_a_design_with_phase_levels_draws_what_it_drew_when_they_were_added():
    full = drift_building_phase_level.phase_levels(tp._phased(n=400, per_unit=9))
    train, _, _ = td._split(full)
    out = drift_building_phase_level.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == LEVEL_RUN_SHA256


def test_the_model_is_l1_with_its_phase_levels():
    assert drift_building_phase_level.LEVEL_DOF == drift_building.LEVEL_DOF
    assert drift_building_phase_level.GROUPS == ("building",)
    assert drift_building_phase_level.NAME == "drift-building-phase-level"
    assert drift_building_phase_level.run is drift_building_phase.run
    assert (
        '("drift-building-phase-level", "drift_building_phase_level")'
        in open(run.__file__).read()
    )
    d = drift_building_phase_level.phase_levels(tp._phased(n=300))
    rec = drift_building_phase_level.run_record(d)
    assert rec["phase"]["levels"] == list(LEVELS)
    assert rec["phase"]["reference"] == "10-13"
    assert rec["phase"]["rows"] == drift_building_phase.run_record(d)["phase"]["rows"]
