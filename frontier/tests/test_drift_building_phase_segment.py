"""L1 with a path in time for each segment, bedroom group by zone
(`rentfrontier.drift_building_phase_segment`)."""

import dataclasses
import hashlib

import numpy as np
import pandas as pd
import test_drift as td
import test_drift_building_phase as tp

from rentfrontier import (
    building_zones,
    drift,
    drift_building_phase,
    drift_building_phase_segment,
    drift_pool,
    run,
)

m = drift_building_phase_segment


def _segmented(n=1200, **kw):
    """A phased design over five years with the segments' path columns."""
    return m.segment_paths(tp._phased(n=n, weeks=260, **kw))


def test_hat_weights_interpolate_between_the_knots():
    H = m.hat_weights(np.array([0.0, 0.1, 0.25, 0.4, 0.5]), np.array([0.0, 0.25, 0.5]))
    np.testing.assert_allclose(
        H,
        [[1, 0, 0], [0.6, 0.4, 0], [0, 1, 0], [0, 0.4, 0.6], [0, 0, 1]],
        atol=1e-12,
    )


def test_each_segment_gets_a_centered_column_at_every_quarter_start():
    d = tp._phased(n=1200, weeks=260)
    out = m.segment_paths(d)
    q = m.quarter_starts(d)
    assert q[0] <= d.start < q[1]
    assert (q == q.to_period("Q").start_time).all()
    last = d.start + pd.Timedelta(days=float(m.years(d).max()) * m.YEAR_DAYS)
    assert q[-2] < last <= q[-1]
    labels = m.segment_names(d)
    assert labels[0] == "manhattan:studio" and labels[-1] == "outer:3br+"
    seg = m.segment_index(d)
    zone = m.site_zone(d)[d.site]
    np.testing.assert_array_equal(seg, zone * 4 + d.group)
    assert len(np.unique(seg)) == 8
    # Every segment has rows in every quarter of the simulated frame, so no column drops.
    names = [f"seg:{s}:{t.year}q{t.quarter}" for s in labels for t in q]
    assert out.names == d.names + names
    np.testing.assert_array_equal(out.x[:, : len(d.names)], d.x)
    knots = np.asarray((q - d.start).days, float) / m.YEAR_DAYS
    H = m.hat_weights(m.years(d), knots)
    np.testing.assert_allclose(H.sum(axis=1), 1.0)
    X = out.x[:, len(d.names) :].reshape(len(d.y), 8, len(q))
    for k in range(8):
        on = seg == k
        p = H[on].sum(axis=0) / H.sum(axis=0)
        np.testing.assert_allclose(X[:, k], H * (on[:, None] - p), atol=1e-12)
    # Each column sums to 0 over the rows, and the segments' columns at a knot sum to 0 on
    # every row, so the paths move no average and leave the citywide walk its own.
    np.testing.assert_allclose(X.sum(axis=0), 0.0, atol=1e-9)
    np.testing.assert_allclose(X.sum(axis=1), 0.0, atol=1e-12)


def test_the_rows_to_predict_carry_their_path_columns():
    full = _segmented()
    train, _, held = td._split(full)
    np.testing.assert_array_equal(train.pred["x"], full.x[held])


def test_the_processes_follow_the_floor_curves_one_for_each_segment():
    out = _segmented()
    spec = m.gp_spec(out.names)
    floors = drift_building_phase.gp_spec(out.names)
    assert [s["name"] for s in spec[: len(floors)]] == [s["name"] for s in floors]
    segs = spec[len(floors) :]
    assert [s["name"] for s in segs] == [f"seg:{s}" for s in m.segment_names(out)]
    for s in segs:
        assert s["amp"] == m.SEG_AMP and s["ls"] == m.SEG_LS
        assert all(c.startswith(s["name"] + ":") for c in s["cols"])
        # The inputs are years from 2024-01-01, where the prior holds each path at 0.
        assert s["x"][s["cols"].index(s["name"] + ":2024q1")] == 0.0
        np.testing.assert_allclose(np.diff(s["x"]), 0.25, atol=0.01)
    # With no path columns, the processes are L1's.
    assert m.gp_spec(tp._phased(n=300).names) == []
    assert len(floors) == len(drift_building_phase.gp_spec(tp._phased(n=300).names))


def test_a_run_recovers_planted_segment_paths():
    full = m.segment_paths(tp._phased(n=1500, weeks=260, per_unit=6))
    cols = [i for i, c in enumerate(full.names) if c.startswith("seg:")]
    rng = np.random.default_rng(2)
    delta = np.concatenate(
        [
            0.08 * rng.standard_normal() * np.sin(np.pi * s["x"] / 2.5)
            for s in m.segment_spec(full.names)
        ]
    )
    effect = full.x[:, cols] @ delta
    full = dataclasses.replace(full, y=full.y + effect)
    train, _, held = td._split(full)
    out = m.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=100, draws=40, level_dof=4.0, seed=3),
        log=lambda s: None,
    )
    beta = out["kept"]["beta"].reshape(-1, len(full.names))
    got = train.x[:, cols] @ beta[:, cols].mean(axis=0)
    assert np.corrcoef(got, effect[~held])[0, 1] > 0.8
    assert np.sqrt(np.mean((got - effect[~held]) ** 2)) < 0.5 * effect[~held].std()
    diag = m.diagnostics(out["trace"], train.names)
    for s in m.segment_names(full):
        assert f"gp_amp[seg:{s}]" in diag["per_quantity"]
        assert f"gp_ls[seg:{s}]" in diag["per_quantity"]
    assert set(m.summarize(out["kept"], train.names)["segment_gp"]) == {
        f"{q}[seg:{s}]" for s in m.segment_names(full) for q in ("gp_amp", "gp_ls")
    }


# The sha256 of every traced and kept array of the run below on the CPU, as drawn when the
# segment paths were added. A deliberate change to the model's draws changes it.
SEGMENT_RUN_SHA256 = "1d5f0f32ec1db6502a7114d1f8e703ef8d1335ef88349e62d2042998e92b5743"


def test_a_design_with_segment_paths_draws_what_it_drew_when_they_were_added():
    full = m.segment_paths(tp._phased(n=400, weeks=260, per_unit=9))
    train, _, _ = td._split(full)
    out = m.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda s: None,
    )
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == SEGMENT_RUN_SHA256


def test_the_model_is_l1_with_its_segment_paths():
    assert m.LEVEL_DOF == drift_building_phase.LEVEL_DOF
    assert m.GROUPS == ("building",)
    assert m.NAME == "drift-building-phase-segment"
    assert (
        '("drift-building-phase-segment", "drift_building_phase_segment")'
        in open(run.__file__).read()
    )
    assert drift_pool.model_diagnostics({"model": {"name": m.NAME}}) is m.diagnostics
    assert (
        drift_pool.model_diagnostics({"model": {"name": "drift-building-phase"}})
        is drift.diagnostics
    )
    d = _segmented()
    rec = m.run_record(d)
    assert rec["segments"]["names"] == m.segment_names(d)
    assert sum(rec["segments"]["rows"]) == len(d.y)
    assert rec["segments"]["columns"] == 8 * len(m.quarter_starts(d))
    assert rec["segments"]["reference"] == "2024-01-01"
    assert rec["phase"] == drift_building_phase.run_record(d)["phase"]
