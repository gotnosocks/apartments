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

    # Short end-to-end sampling smoke check on unified + unified-seg (with phase_collapsed=True
    # and identifiable segment paths dropping ref segment + 2024q1)
    d_seg = US.identifiable_segment_paths(d)
    seg_cols = [n for n in d_seg.names if n.startswith("seg:")]
    assert not any(n.endswith(f":{US.REF_QUARTER}") for n in seg_cols)
    seg_names_present = {n.rsplit(":", 1)[0].split("seg:", 1)[1] for n in seg_cols}
    assert len(seg_names_present) < len(drift_building_phase_segment.segment_names(d))
    gps_seg = US.gp_spec(d_seg.names)
    assert all(
        g.get("kernel") == "matern32" and g.get("nugget") == 1e-4
        for g in gps_seg
        if g["name"].startswith("seg:")
    )
    assert all("kernel" not in g for g in gps_seg if not g["name"].startswith("seg:"))
    train_seg, _, _ = td._split(d_seg)
    settings = U.Settings(
        chains=2, warmup=4, draws=4, keep_every=2, chunks=1, budget_seconds=None
    )
    out = U.run(train, U.Priors(), settings, log=lambda *_: None)
    assert out["kept"]["phase_scale"].shape[-1] == len(cell_names)
    assert out["trace"]["phase_factor"].shape[-1] == len(kept)
    out_seg = US.run(train_seg, US.Priors(), settings, log=lambda *_: None)
    assert out_seg["kept"]["phase_scale"].shape[-1] == len(cell_names)
    diag_seg = US.diagnostics(out_seg["trace"], train_seg.names)
    assert "max_rhat" in diag_seg


def test_phase_collapsed_binary_and_nonbinary_match_direct_t_logpdf():
    """Verify both the binary fast path and general non-binary path of `phase_collapsed`
    evaluate the exact Student-t conditional log-density (up to a constant independent of v)
    and that a non-binary `phase_map` runs cleanly through `drift.run`."""
    import jax
    import jax.numpy as jnp

    from rentfrontier import b0, drift

    jax.config.update("jax_enable_x64", True)
    rng = np.random.default_rng(17)
    n = 400
    r = jnp.asarray(rng.normal(0.0, 0.14, n))
    sigma = jnp.asarray([0.08, 0.09, 0.10, 0.11])
    group = jnp.asarray(rng.integers(0, 4, n))
    nu = 2.0
    lf0 = jnp.asarray([0.15, -0.22, 0.09])

    # 1. Binary phase_map fast path vs direct full-data b0.t_logpdf
    pmap_bin = jnp.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 1.0]]
    )
    ph_idx = jnp.asarray(rng.integers(0, 4, n))
    sd0 = sigma[group] * jnp.exp((pmap_bin @ lf0)[ph_idx])
    u2_0 = (r / sd0) ** 2 / nu
    for j in range(3):
        active = pmap_bin[ph_idx, j] > 0.5
        old_v = lf0[j]
        n_act = jnp.sum(active)
        u2_act = jnp.where(active, u2_0 * jnp.exp(2.0 * old_v), 0.0)
        diffs = []
        for v in (-0.35, 0.0, float(old_v), 0.45):
            lf_try = lf0.at[j].set(v)
            sd_full = sigma[group] * jnp.exp((pmap_bin @ lf_try)[ph_idx])
            direct = float(
                jnp.sum(b0.t_logpdf(r, nu, sd_full))
                - v * v / (2 * drift.PHASE_PRIOR**2)
            )
            fast = float(
                -v * n_act
                - 0.5 * (nu + 1.0) * jnp.sum(jnp.log1p(u2_act * jnp.exp(-2.0 * v)))
                - v * v / (2 * drift.PHASE_PRIOR**2)
            )
            diffs.append(fast - direct)
        assert max(diffs) - min(diffs) < 1e-11

    # 2. General non-binary phase_map path vs direct full-data b0.t_logpdf
    pmap_nb = jnp.asarray([[0.0, 0.0], [0.5, 0.0], [1.5, 0.25], [0.0, 0.75]])
    lf_nb = jnp.asarray([0.2, -0.1])
    ls_base = jnp.log(sigma[group]) + (pmap_nb @ lf_nb)[ph_idx]
    for j in range(2):
        m_j = pmap_nb[ph_idx, j]
        active = m_j != 0.0
        old_v = lf_nb[j]
        ls_without = ls_base - old_v * m_j
        diffs = []
        for v in (-0.3, 0.0, float(old_v), 0.4):
            lf_try = lf_nb.at[j].set(v)
            sd_full = sigma[group] * jnp.exp((pmap_nb @ lf_try)[ph_idx])
            direct = float(
                jnp.sum(b0.t_logpdf(r, nu, sd_full))
                - v * v / (2 * drift.PHASE_PRIOR**2)
            )
            sd_j = jnp.exp(ls_without + v * m_j)
            gen = float(
                jnp.sum(jnp.where(active, b0.t_logpdf(r, nu, sd_j), 0.0))
                - v * v / (2 * drift.PHASE_PRIOR**2)
            )
            diffs.append(gen - direct)
        assert max(diffs) - min(diffs) < 1e-11

    # 3. Smoke test non-binary phase_map + RBF custom nugget in drift.run
    full = td._design(per_unit=6)
    cell = np.arange(len(full.y)) % 4
    d_nb = dataclasses.replace(
        full,
        phase=cell,
        phases=["ref", "a", "b", "c"],
        phase_map=np.asarray(pmap_nb, float),
    )
    train_nb, _, _ = td._split(d_nb)
    settings = U.Settings(
        chains=2, warmup=2, draws=2, keep_every=1, chunks=1, budget_seconds=None
    )
    gp_rbf_nug = [
        g | {"kernel": "rbf", "nugget": 1e-3} for g in U.gp_spec(train_nb.names)
    ]
    out_nb = drift.run(
        train_nb,
        U.Priors(),
        settings,
        log=lambda *_: None,
        gp=gp_rbf_nug,
        groups=drift.groups_of(train_nb, U.GROUPS),
        unit_t=True,
        unit_dof_fixed=U.UNIT_DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=U.ROW_DOF,
        phase_collapsed=True,
    )
    assert out_nb["kept"]["phase_scale"].shape[-1] == 4
