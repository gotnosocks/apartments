"""The building model with noise phases and the first-ad phase split in two
(`rentfrontier.drift_building_phase_first`)."""

import dataclasses

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import (
    building_zones,
    drift,
    drift_building,
    drift_building_phase,
    drift_building_phase_first,
    run,
)

M = drift_building_phase_first
P = M.PHASES


def test_a_first_ad_is_only_for_a_unit_with_one_ad_and_first_otherwise():
    day = pd.Timestamp("2024-01-01", tz="UTC")
    month = pd.Timedelta(days=365.25 / 12)
    rows = [
        # building, unit_id, months from `day`, audit_id, the phase
        ("a", "1", 0.0, "1", "first"),
        ("a", "1", 2.9, "2", "0-2"),
        ("a", "1", 16.2, "3", "10-13"),
        # The same unit_id in another building is another unit, with one ad.
        ("b", "1", 31.0, "4", "only"),
        ("c", "7", 5.0, "6", "3-9"),
        ("c", "7", 0.0, "5", "first"),
        # A row with no unit_id is its own unit with one ad, even beside others.
        ("c", None, 1.0, "7", "only"),
        ("c", None, 2.0, "8", "only"),
        ("d", "2", 40.0, "9", "only"),
    ]
    frame = pd.DataFrame(
        {
            "building": [r[0] for r in rows],
            "unit_id": [r[1] for r in rows],
            "price_at": [day + r[2] * month for r in rows],
            "audit_id": [r[3] for r in rows],
        }
    )
    got = [P[i] for i in M.phase_index(frame)]
    assert got == [r[4] for r in rows]
    np.testing.assert_array_equal(M.ads_of_unit(frame), [3, 3, 3, 1, 2, 2, 1, 1, 1])
    # Every other row keeps the phase model's phase.
    old = np.asarray(drift_building_phase.PHASES)[
        drift_building_phase.phase_index(frame)
    ]
    new = np.asarray(got)
    keep = old != "none"
    np.testing.assert_array_equal(new[keep], old[keep])
    assert set(new[~keep]) == {"first", "only"}


def _phased(seed=4, **kw):
    """`td._design` with random noise phases of this model."""
    full = td._design(**kw)
    rng = np.random.default_rng(seed)
    return dataclasses.replace(
        full, phase=rng.integers(0, len(P), len(full.y)), phases=P
    )


@pytest.fixture(scope="module")
def first_run():
    full = _phased(n=400, per_unit=9)
    train, _, held = td._split(full)
    out = drift_building.run(
        train,
        building_zones.Priors(),
        drift.Settings(
            chains=2, warmup=60, draws=8, keep_every=2, level_dof=4.0, seed=3
        ),
        log=lambda m: None,
    )
    return full, held, out


def test_a_run_traces_and_keeps_all_eight_phases_factors(first_run):
    full, held, out = first_run
    trace, kept = out["trace"], out["kept"]
    assert trace["phase_scale"].shape == (2, 8, len(P))
    assert (trace["phase_scale"][..., 0] == 1).all()
    assert np.ptp(trace["phase_scale"][..., 1:], axis=1).min() > 0
    np.testing.assert_array_equal(kept["pred_phase"], full.phase[held])
    assert len(out["result"]["gibbs"]["hyp_dirs"]) == 8 + len(P) - 1
    rows = drift.diagnostics(trace, full.names)["per_quantity"]
    assert {f"phase_scale[{j}]" for j in range(1, len(P))} <= set(rows)


def test_the_model_is_the_phase_model_with_its_first_ads_split():
    assert M.LEVEL_DOF == drift_building.LEVEL_DOF
    assert M.GROUPS == ("building",)
    assert M.NAME == "drift-building-phase-first"
    assert P[0] == "10-13" and len(set(P)) == 8
    assert set(P) == set(drift_building_phase.PHASES) - {"none"} | {"first", "only"}
    assert (
        '("drift-building-phase-first", "drift_building_phase_first")'
        in open(run.__file__).read()
    )
    d = _phased(n=300)
    rec = M.run_record(d)["phase"]
    assert rec["reference"] == "10-13" and sum(rec["rows"].values()) == len(d.y)
    assert rec["phases"] == list(P)
