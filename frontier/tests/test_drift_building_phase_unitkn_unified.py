"""Tests for `drift_building_phase_unitkn_unified` and `drift_building_phase_unitkn_unified_seg`."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import test_drift as td

from rentfrontier import drift_building_phase_segment
from rentfrontier import drift_building_phase_unitkn_unified as U
from rentfrontier import drift_building_phase_unitkn_unified_seg as US


def test_compact_phase_map_drops_empty_train_factors_and_keeps_ref_at_zero():
    names = ["f_a", "f_b", "f_empty_in_train"]
    mat = np.array(
        [
            [0, 0, 0],  # train ref
            [1, 0, 0],  # train f_a
            [1, 1, 0],  # train f_a|f_b
            [0, 1, 1],  # held-out row with f_empty_in_train=1
        ],
        dtype=float,
    )
    train = np.array([True, True, True, False])
    cell, cell_names, pmap, kept = U.compact_phase_map(names, mat, train)
    assert kept == ["f_a", "f_b"]
    assert pmap.shape == (4, 2)
    assert not pmap[0].any()
    assert cell_names[0] == "ref"
    # Verify exact multiplicative factorization on every row
    lf = np.array([0.2, -0.3])
    row_scales = np.exp(pmap[cell] @ lf)
    want = np.exp(mat[:, :2] @ lf)
    np.testing.assert_allclose(row_scales, want)
    # Recover factor names from cell names + pmap
    dummy = dataclasses.replace(
        td._design(per_unit=4), phase=cell, phases=cell_names, phase_map=pmap
    )
    assert U.free_factor_names(dummy) == ["f_a", "f_b"]


def test_prior_bld_bed_count_strictly_earlier_training_rows_only():
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 5,
            "bedrooms": [1, 1, 1, 1, 2],
            "price_at": pd.to_datetime(
                ["2022-01-01", "2022-01-01", "2022-01-02", "2022-01-03", "2022-01-03"],
                utc=True,
            ),
        }
    )
    # Row 2 is held out -> must NOT increment row 3's count!
    train = np.array([True, True, False, True, True])
    got = U.prior_bld_bed_count(frame, train)
    assert got.tolist() == [0, 0, 2, 2, 0]


def test_large_01br_and_floor_1_flags():
    d = td._design(per_unit=6)
    n = len(d.y)
    # Construct synthetic design columns to verify helpers cleanly
    names = [
        "unit:log_size_rel",
        "unit:size_unknown",
        "unit:elev_floor_unknown",
        "unit:walkup_floor_unknown",
        "unit:elev_f2",
        "unit:walkup_f3",
    ]
    x = np.zeros((n, len(names)))
    x[0, 0] = 0.8  # studio, > log(2) -> large
    x[1, 0] = 0.5  # studio, <= log(2) -> not large
    x[2, 0] = 0.4  # 1BR, > log(1.4) -> large
    x[3, 0] = 0.8  # 1BR, size_unknown=1 -> not large
    x[3, 1] = 1.0
    x[4, 0] = 0.9  # 2BR -> not 0-1BR
    # floor_1 tests: row 0 = floor 1, row 1 = elev_f2, row 2 = elev_floor_unknown, row 3 = walkup_f3
    x[1, 4] = 1.0
    x[2, 2] = 1.0
    x[3, 5] = 1.0
    d2 = dataclasses.replace(d, x=x, names=names)
    frame = pd.DataFrame({"bedrooms": [0, 0, 1, 1, 2] + [1] * (n - 5)})
    l01 = U.large_01br_flag(d2, frame)
    assert l01[:5].tolist() == [1.0, 0.0, 1.0, 0.0, 0.0]
    fl1 = U.floor_1_flag(d2)
    assert fl1[:4].tolist() == [1.0, 0.0, 0.0, 0.0]


def test_unified_scales_logp_matches_dense_and_runs_smoke():
    full = td._design(per_unit=8)
    n = len(full.y)
    rng = np.random.default_rng(11)
    # Build 4 synthetic additive binary factors with compact_phase_map
    mat = rng.integers(0, 2, size=(n, 4)).astype(float)
    mat[0] = 0.0
    train_mask = np.ones(n, bool)
    train_mask[-4:] = False
    cell, cell_names, pmap, kept = U.compact_phase_map(
        ["phase:none", "yr:2022", "mark:changed_counts", "mark:large_01br"],
        mat,
        train_mask,
    )
    assert len(kept) == 4
    d = dataclasses.replace(full, phase=cell, phases=cell_names, phase_map=pmap)
    train, _, _ = td._split(d)
    _, init, _, parts = U.make_sampler(
        train,
        U.Priors(),
        U.Settings(
            chains=2, warmup=4, draws=4, keep_every=2, chunks=1, budget_seconds=None
        ),
        unit_t=True,
        unit_dof_fixed=U.UNIT_DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=U.ROW_DOF,
    )
    assert parts["phased"]
    st = td._state(init, parts)
    assert st["phase_scale"].shape[-1] == 4
    # Fixed row nu (unitkn) => 3 hyp + 4 sigma + 4 free factors = 11 scale coords
    assert st["hyp_dirs"].shape == (7 + 4, 7 + 4)

    # Short end-to-end sampling smoke check on unified + unified-seg
    d_seg = drift_building_phase_segment.segment_paths(d)
    train_seg, _, _ = td._split(d_seg)
    settings = U.Settings(
        chains=2, warmup=4, draws=4, keep_every=2, chunks=1, budget_seconds=None
    )
    out = U.run(train, U.Priors(), settings, log=lambda *_: None)
    assert out["kept"]["phase_scale"].shape[-1] == len(cell_names)
    assert out["trace"]["phase_scale"].shape[-1] == len(cell_names)
    out_seg = US.run(train_seg, US.Priors(), settings, log=lambda *_: None)
    assert out_seg["kept"]["phase_scale"].shape[-1] == len(cell_names)
    diag_seg = US.diagnostics(out_seg["trace"], train_seg.names)
    assert "max_rhat" in diag_seg
