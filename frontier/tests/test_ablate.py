"""Tests for `rentfrontier.drift_building_phase_unitkn_ablate`."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import building_attrs, drift
from rentfrontier import drift_building_phase_unitkn_ablate as ablate
from rentfrontier import drift_building_phase_unitkn_unified_seg as unified_seg


def test_parse_and_extract_variant():
    assert ablate.parse_variant(None) == ()
    assert ablate.parse_variant("y1, marks , covid_mean") == (
        "y1",
        "marks",
        "covid_mean",
    )
    with pytest.raises(ValueError, match="unknown variant"):
        ablate.parse_variant("not_a_real_token")

    toks, rest = ablate._extract_variant(
        ["--split", "carried", "--variant", "y1,sbf", "--seed", "1"]
    )
    assert toks == ("y1", "sbf")
    assert rest == ["--split", "carried", "--seed", "1"]

    toks2, rest2 = ablate._extract_variant(["--variant=covid_vol", "--seed", "2"])
    assert toks2 == ("covid_vol",)
    assert rest2 == ["--seed", "2"]


def test_concession_gap_is_strictly_causal(tmp_path: Path):
    rows_pq = tmp_path / "rows.parquet"
    pd.DataFrame(
        {
            "listing_id": ["L1", "L2", "L3", "L4"],
            "months_free": [0.0, 2.0, 0.0, 1.0],
        }
    ).to_parquet(rows_pq, index=False)
    frame = pd.DataFrame(
        {
            "listing_id": ["L1", "L2", "L3", "L4"],
            "building": ["B1", "B1", "B1", "B1"],
            "price_at": [
                "2020-05-01T00:00:00Z",
                "2020-06-01T00:00:00Z",
                "2020-07-01T00:00:00Z",
                "2023-07-01T00:00:00Z",
            ],
        }
    )
    # L2 is held out, so L3 must NOT see L2's concession!
    train = np.array([True, False, True, True])
    mat, names = ablate.concession_gap_features(frame, train, rows_path=rows_pq)
    assert names == [
        "ad:concess_2020_22_bld",
        "ad:concess_2020_22_missing",
        "ad:concess_2020_22_rate",
    ]
    assert np.allclose(mat, 0.0)

    # Now L2 is in training: L1 (before L2) sees 0, L3 (after L2, no concession in 2020) sees 1,
    # and L4 (2023, outside 2020-2022) sees 0.
    train2 = np.array([True, True, False, True])
    mat2, _ = ablate.concession_gap_features(frame, train2, rows_path=rows_pq)
    assert mat2[0, 0] == 0.0
    assert mat2[2, 0] == 1.0  # bld_ever in 2020-2022
    assert mat2[2, 1] == 1.0  # missing concession on L3
    assert mat2[2, 2] == pytest.approx(0.5)  # 1 of 2 prior training ads
    assert mat2[3, 0] == 0.0  # 2023 outside 2020-2022


def test_rentstab_dhcr_uses_strictly_prior_year(tmp_path: Path, monkeypatch):
    reg = tmp_path / "registry.parquet"
    pd.DataFrame(
        {"building": ["B1", "B2"], "bbl": [1000000001, 3000000002]}
    ).to_parquet(reg, index=False)
    monkeypatch.setattr(building_attrs, "REGISTRY", reg)

    rs = tmp_path / "rentstab.parquet"
    pd.DataFrame(
        {
            "bbl": [1000000001, 1000000001],
            "year": [2019, 2021],
            "units": [0, 12],
        }
    ).to_parquet(rs, index=False)

    frame = pd.DataFrame(
        {
            "building": ["B1", "B1", "B2"],
            "price_at": [
                "2021-03-01T00:00:00Z",  # ad_yr-1 = 2020 -> sees 2019 (0 units), NOT 2021!
                "2022-03-01T00:00:00Z",  # ad_yr-1 = 2021 -> sees 2021 (12 units)
                "2022-03-01T00:00:00Z",  # not in rentstab
            ],
            "rent_stabilized": [False, False, True],
        }
    )
    mat, names = ablate.rentstab_dhcr_features(frame, rentstab_path=rs)
    assert len(names) == 4
    assert mat[0, 0] == 0.0  # strictly prior year: 2021 ad does NOT peek at 2021 DHCR
    assert mat[1, 0] == 1.0  # 2022 ad sees 2021 DHCR (12 units)
    assert mat[1, 3] == 1.0  # stab:x_2022_on active
    assert mat[2, 0] == 0.0  # B2 not in DHCR
    assert mat[2, 3] == 1.0  # B2 still active via text rent_stabilized


def test_covid_features_are_causal_and_zero_pre_pandemic(tmp_path: Path, monkeypatch):
    reg = tmp_path / "registry.parquet"
    pd.DataFrame(
        {"building": ["B_MN", "B_BK"], "bbl": [1000000001, 3000000002]}
    ).to_parquet(reg, index=False)
    monkeypatch.setattr(building_attrs, "REGISTRY", reg)

    csv_p = tmp_path / "covid.csv"
    pd.DataFrame(
        {
            "date_of_interest": ["03/01/2020", "04/01/2020"],
            "HOSP_COUNT_7DAY_AVG": [10.0, 500.0],
            "CASE_COUNT_7DAY_AVG": [50.0, 4000.0],
            "MN_HOSPITALIZED_COUNT_7DAY_AVG": [4.0, 120.0],
            "BX_HOSPITALIZED_COUNT_7DAY_AVG": [2.0, 100.0],
            "BK_HOSPITALIZED_COUNT_7DAY_AVG": [2.0, 160.0],
            "QN_HOSPITALIZED_COUNT_7DAY_AVG": [2.0, 100.0],
            "SI_HOSPITALIZED_COUNT_7DAY_AVG": [0.0, 20.0],
            "MN_CASE_COUNT_7DAY_AVG": [20.0, 900.0],
            "BX_CASE_COUNT_7DAY_AVG": [10.0, 800.0],
            "BK_CASE_COUNT_7DAY_AVG": [10.0, 1200.0],
            "QN_CASE_COUNT_7DAY_AVG": [10.0, 900.0],
            "SI_CASE_COUNT_7DAY_AVG": [0.0, 200.0],
        }
    ).to_csv(csv_p, index=False)

    frame = pd.DataFrame(
        {
            "building": ["B_MN", "B_MN", "B_BK"],
            "price_at": [
                "2019-06-01T00:00:00Z",  # pre-pandemic -> all zero
                "2020-04-10T00:00:00Z",  # 14d lag = 2020-03-27 -> sees 03/01 (hosp=10), NOT 04/01!
                "2020-04-20T00:00:00Z",  # 14d lag = 2020-04-06 -> sees 04/01 (hosp=500 -> surge!)
            ],
            "bedrooms": [1, 2, 2],
        }
    )

    class _DummyDesign:
        names = ("bld:doorman_full", "unit:private_outdoor_space")
        x = np.array([[1.0, 0.0], [1.0, 1.0], [0.0, 0.0]])
        y = np.zeros(3)

    mean_mat, names, vol_mat = ablate.covid_features(
        frame, _DummyDesign(), csv_path=csv_p
    )
    assert len(names) == 6
    assert np.allclose(mean_mat[0], 0.0)
    assert np.allclose(vol_mat[0], 0.0)
    # Row 1 (2020-04-10, lagged to 03/27) must NOT see the 04/01 surge!
    assert vol_mat[1, 0] == 0.0
    # Row 2 (2020-04-20, lagged to 04/06) sees hosp=500 -> surge=1, elevated=0
    assert vol_mat[2, 0] == 1.0
    assert vol_mat[2, 1] == 0.0
    assert mean_mat[2, 3] > 0.0  # hosp_x_2pbr active


@pytest.fixture
def screen_rows(monkeypatch):
    d = td._design(n=400, weeks=30)
    n = len(d.y)
    frame = pd.DataFrame(
        {
            "building": ["shared"] * 8 + [f"b{i}" for i in range(8, n)],
            "unit_id": ["u"] * 4 + [f"u{i}" for i in range(4, n)],
            "price_at": pd.date_range("2023-10-02", periods=n, freq="D", tz="UTC"),
            "bedrooms": 1,
            "full_baths": 1,
            "half_baths": 0,
            "bed_flex_at": False,
            "bed_text_fewer": False,
        }
    )
    frame.loc[1, ["bedrooms", "full_baths"]] = 3  # Held out and ignored by later rows.
    frame.loc[3, "full_baths"] = 2
    frame.loc[4, "full_baths"] = 3
    held = np.zeros(n, dtype=bool)
    held[1] = True
    phase = np.full(n, ablate.PHASES.index("none"))
    phase[[2, 3]] = 0
    above_floor_one = np.ones(n)
    above_floor_one[:2] = 0
    size = np.zeros(n)
    size[[0, 4]] = 0.5
    d = dataclasses.replace(
        d,
        start=pd.Timestamp("2023-10-02"),
        phase=phase,
        phases=ablate.PHASES,
        names=[*d.names, "unit:elev_f2", "unit:log_size_rel"],
        x=np.column_stack([d.x, above_floor_one, size]),
    )
    monkeypatch.setattr(
        ablate.drift_building_phase_unitkn_level, "design", lambda *a, **k: d
    )
    return frame, held


def _row_tokens(d, row):
    return set(d.phases[d.phase[row]].split("|"))


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("mark_changed", {"mark:changed_counts": [1, 3]}),
        ("mark_baths", {"mark:baths_2": [3], "mark:baths_3p": [1, 4]}),
        ("mark_floor1", {"mark:floor_1": [0, 1]}),
        ("mark_large01br", {"mark:large_01br": [0, 4]}),
        ("mark_thin", {"mark:thin_first_ad": [0, 1, 4, 5]}),
    ],
)
def test_individual_scale_marks_add_only_the_requested_factors(
    screen_rows, token, expected
):
    frame, held = screen_rows
    base = ablate.design(frame, held=held)
    d = ablate.design(frame, held=held, variant=token)
    assert d.names == base.names
    all_marks = {
        mark
        for cell in d.phases
        for mark in cell.split("|")
        if mark.startswith("mark:")
    }
    assert all_marks == expected.keys()
    for mark, want in expected.items():
        assert [row for row in range(8) if mark in _row_tokens(d, row)] == want


def test_scale_mark_bundles_can_be_combined_without_duplicates(screen_rows):
    frame, held = screen_rows
    full = ablate.design(frame, held=held, variant="marks")
    without_thin = ablate.design(frame, held=held, variant="marks_no_thin")
    combined = ablate.design(
        frame, held=held, variant="marks_no_thin,mark_thin,mark_baths"
    )
    assert all("mark:thin_first_ad" not in cell for cell in without_thin.phases)
    assert combined.phases == full.phases
    np.testing.assert_array_equal(combined.phase_map, full.phase_map)
    np.testing.assert_array_equal(combined.phase, full.phase)


def test_pre2024_year_factors_keep_recent_years_at_reference(screen_rows):
    frame, held = screen_rows
    year = 2013 + np.arange(len(frame)) % 14
    frame["price_at"] = pd.to_datetime(pd.Series(year).astype(str) + "-07-01", utc=True)
    held |= year == 2019
    d = ablate.design(frame, held=held, variant="y1_pre2024")
    legacy = ablate.design(frame, held=held, variant="y1")

    for row, y in enumerate(year):
        tokens = {t for t in _row_tokens(d, row) if t.startswith("yr:")}
        assert tokens == ({f"yr:{max(2014, y)}"} if y < 2024 and y != 2019 else set())
    assert "yr:2025" in _row_tokens(legacy, 12)
    assert "yr:2026" in _row_tokens(legacy, 13)


def test_segment_variant_reuses_unified_identifiable_paths_and_gp_priors(
    screen_rows, monkeypatch
):
    frame, held = screen_rows
    base = ablate.design(frame, held=held, variant="mark_baths")
    assert all(not g["name"].startswith("seg:") for g in ablate.gp_spec(base.names))
    monkeypatch.setattr(ablate, "ACTIVE_VARIANT", ("mark_baths", "seg"))
    d = ablate.design(frame, held=held)
    want = unified_seg.identifiable_segment_paths(base)
    assert d.names == want.names
    np.testing.assert_array_equal(d.x, want.x)
    np.testing.assert_array_equal(d.phase_map, base.phase_map)
    path_names = [n for n in d.names if n.startswith("seg:")]
    assert path_names
    assert not any(
        n.startswith("seg:manhattan:1br:") or n.endswith(":2024q1") for n in path_names
    )

    gps = ablate.gp_spec(d.names)
    specs = [g for g in gps if g["name"].startswith("seg:")]
    assert specs and all(
        g["kernel"] == "matern32" and g["nugget"] == 1e-4 for g in specs
    )
    settings = ablate.Settings(
        chains=2, warmup=2, draws=4, keep_every=2, budget_seconds=None
    )
    train = ablate.subset(d, ~held)
    out = ablate.run(train, ablate.Priors(), settings, log=lambda _: None)
    assert out["trace"]["gp_amp"].shape == (2, 4, len(gps))
    assert out["kept"]["phase_scale"].shape == (2, 2, len(d.phases))
    rows = ablate.diagnostics(out["trace"], d.names)["per_quantity"]
    scales = {f"gp_ls[{g['name']}]" for g in specs}
    assert scales <= rows.keys()
    assert scales <= ablate.summarize(out["kept"], d.names)["segment_gp"].keys()

    # The design's columns also carry the variant for direct callers of design(variant=...).
    monkeypatch.setattr(ablate, "ACTIVE_VARIANT", ())
    assert [g["name"] for g in ablate.gp_spec(d.names)] == [g["name"] for g in gps]
    monkeypatch.setattr(drift, "run", lambda *args, **kw: kw["gp"])
    assert [g["name"] for g in ablate.run(base, ablate.Priors(), settings)] == [
        g["name"] for g in ablate.gp_spec(base.names)
    ]


def test_extract_variant_rejects_legacy_ablate_flag():
    with pytest.raises(ValueError, match="--variant"):
        ablate._extract_variant(["--ablate", "mark_baths"])
    with pytest.raises(ValueError, match="--variant"):
        ablate._extract_variant(["--ablate=mark_baths"])


def test_sv_gp_basis_matches_anchored_matern32_and_samples(screen_rows):
    frame, held = screen_rows
    B = ablate.sv_gp_basis()
    assert B.shape[0] == ablate.SV_QUARTERS
    assert np.all(B[ablate.SV_REF_QUARTER] == 0.0)
    # Prior covariance under Normal(0, PHASE_PRIOR^2) matches conditioned Matérn-3/2.
    cov = (B @ B.T) * (drift.PHASE_PRIOR**2)
    t = ablate.SV_FIRST_YEAR + 0.125 + 0.25 * np.arange(ablate.SV_QUARTERS, dtype=float)
    u = np.sqrt(3.0) * np.abs(t[:, None] - t[None, :]) / ablate.SV_LS
    K = (ablate.SV_AMP**2) * (1.0 + u) * np.exp(-u)
    k_ref = K[:, ablate.SV_REF_QUARTER]
    want = K - np.outer(k_ref, k_ref) / K[ablate.SV_REF_QUARTER, ablate.SV_REF_QUARTER]
    np.testing.assert_allclose(cov, want, atol=2.5e-3)

    # Spread rows across multiple years so multiple sv_gp modes are active and sampleable.
    frame = frame.copy()
    frame["price_at"] = pd.date_range(
        "2018-01-01", periods=len(frame), freq="7D", tz="UTC"
    )
    d = ablate.design(frame, held=held, variant="mark_baths,sv_gp")
    assert not d.phase_map[0].any()
    assert d.phases[0] == "ref"
    assert not np.all((d.phase_map == 0.0) | (d.phase_map == 1.0))
    settings = ablate.Settings(
        chains=2, warmup=2, draws=4, keep_every=2, budget_seconds=None
    )
    out = ablate.run(
        ablate.subset(d, ~held), ablate.Priors(), settings, log=lambda _: None
    )
    assert out["trace"]["phase_factor"].shape == (2, 4, d.phase_map.shape[1])
    assert out["kept"]["phase_scale"].shape == (2, 2, len(d.phases))
    rec = ablate.run_record(d)
    assert rec["phase"]["binary"] is False
    assert rec["phase"]["n_free_factors"] == d.phase_map.shape[1]


def test_vel_gp_is_strictly_leak_free_and_detects_crash_and_boom():
    n = 300
    days = pd.date_range("2019-01-01", periods=n, freq="5D", tz="UTC")
    # Flat 2019, sharp crash in 2020, sharp boom in 2021.
    log_rent = np.full(n, 8.0)
    for i, d in enumerate(days):
        if d.year == 2020:
            log_rent[i] = 8.0 - 0.30 * (d.dayofyear / 365.0)
        elif d.year == 2021:
            log_rent[i] = 7.70 + 0.35 * (d.dayofyear / 365.0)
        elif d.year >= 2022:
            log_rent[i] = 8.05
    frame = pd.DataFrame(
        {"price_at": days, "latest_ask": np.exp(log_rent), "bedrooms": 1.0}
    )
    train = np.ones(n, dtype=bool)
    train[10::5] = False  # 20% held out

    base, names = ablate.vel_gp_features(frame, train)
    assert names == ["vel:down", "vel:up"]
    # Perturb every held-out rent wildly: features must be bit-for-bit identical.
    perturbed = frame.copy()
    perturbed.loc[~train, "latest_ask"] *= 50.0
    after, _ = ablate.vel_gp_features(perturbed, train)
    np.testing.assert_array_equal(base, after)

    yr = days.year.to_numpy()
    assert base[yr == 2020, 0].mean() > base[yr == 2021, 0].mean()
    assert base[yr == 2021, 1].mean() > base[yr == 2020, 1].mean()


def test_hybrid_sv_gp_and_vel_gp_combine_cleanly(screen_rows):
    frame, held = screen_rows
    frame = frame.copy()
    frame["price_at"] = pd.date_range(
        "2018-01-01", periods=len(frame), freq="7D", tz="UTC"
    )
    frame["latest_ask"] = 3000.0 * np.exp(0.1 * np.sin(np.linspace(0, 6, len(frame))))
    d = ablate.design(frame, held=held, variant="marks,sv_gp,vel_gp")
    assert not d.phase_map[0].any()
    rec = ablate.run_record(d)
    fnames = rec["phase"]["free_factors"]
    assert any(n.startswith("sv:m") for n in fnames)
    assert "vel:down" in fnames or "vel:up" in fnames


@pytest.mark.parametrize(
    ("token", "res", "ls", "n_pts", "ref_idx", "n_modes"),
    [
        (
            "sv_gp_mo",
            "month",
            None,
            ablate.SV_MONTHS,
            ablate.SV_REF_MONTH,
            ablate.SV_MO_MODES,
        ),
        (
            "sv_gp_wk",
            "week",
            None,
            ablate.SV_WEEKS,
            ablate.SV_REF_WEEK,
            ablate.SV_WK_MODES,
        ),
        (
            "sv_gp_wk05",
            "week",
            ablate.SV_WK05_LS,
            ablate.SV_WEEKS,
            ablate.SV_REF_WEEK,
            ablate.SV_WK05_MODES,
        ),
    ],
)
def test_sv_gp_monthly_and_weekly_basis_and_future_clamp(
    screen_rows, token, res, ls, n_pts, ref_idx, n_modes
):
    B = ablate.sv_gp_basis(resolution=res, ls=ls)
    assert B.shape == (n_pts, n_modes)
    assert np.all(B[ref_idx] == 0.0)
    # Clamping: held-out future dates strictly after last training date inherit last training bucket.
    frame = pd.DataFrame(
        {
            "price_at": pd.to_datetime(
                ["2024-01-05", "2025-11-05", "2026-06-15", "2026-10-15"], utc=True
            )
        }
    )
    train = np.array([True, True, False, False])
    mat, names = ablate.sv_gp_features(frame, train=train, resolution=res, ls=ls)
    assert len(names) == n_modes
    np.testing.assert_array_equal(mat[2], mat[1])
    np.testing.assert_array_equal(mat[3], mat[1])

    # Smoke test design + MCMC for weekly sv_gp_wk.
    if token == "sv_gp_wk":
        sframe, sheld = screen_rows
        sframe = sframe.copy()
        sframe["price_at"] = pd.date_range(
            "2018-01-01", periods=len(sframe), freq="7D", tz="UTC"
        )
        d = ablate.design(sframe, held=sheld, variant=f"mark_baths,{token}")
        assert not d.phase_map[0].any()
        settings = ablate.Settings(
            chains=2, warmup=2, draws=4, keep_every=2, budget_seconds=None
        )
        out = ablate.run(
            ablate.subset(d, ~sheld), ablate.Priors(), settings, log=lambda _: None
        )
        assert out["trace"]["phase_factor"].shape == (2, 4, d.phase_map.shape[1])


def test_vel_gp_weekly_is_strictly_leak_free_and_clamps_future():
    n = 300
    days = pd.date_range("2019-01-01", periods=n, freq="5D", tz="UTC")
    log_rent = np.where(
        days.year == 2020,
        8.0 - 0.30 * (days.dayofyear / 365.0),
        np.where(days.year == 2021, 7.70 + 0.35 * (days.dayofyear / 365.0), 8.0),
    )
    frame = pd.DataFrame(
        {"price_at": days, "latest_ask": np.exp(log_rent), "bedrooms": 1.0}
    )
    train = np.ones(n, dtype=bool)
    train[10::5] = False
    train[-10:] = False  # Future tail strictly after last training date
    base, names = ablate.vel_gp_features(frame, train, weekly=True)
    assert names == ["vel:down", "vel:up"]
    perturbed = frame.copy()
    perturbed.loc[~train, "latest_ask"] *= 50.0
    after, _ = ablate.vel_gp_features(perturbed, train, weekly=True)
    np.testing.assert_array_equal(base, after)
    # Future rows strictly after last training week match last training week.
    last_tr = int(np.flatnonzero(train)[-1])
    np.testing.assert_array_equal(base[-1], base[last_tr])
    # Weekly resolution varies within 2020 (not flat within a quarter).
    q_mat, _ = ablate.vel_gp_features(frame, train, weekly=False)
    assert not np.array_equal(base, q_mat)


def test_simplification_tokens_design_and_mcmc_smoke(screen_rows, monkeypatch):
    """Test floor_poly, seg_add, seg_add_lr12, spatial_k40, scalar_sigma, biweekly_walk,
    sv_gp_mo16, phase_compact, kitchen-sink pruning, and zero-GP diagnostics end-to-end."""
    sframe, sheld = screen_rows
    sframe = sframe.copy()
    sframe["price_at"] = pd.date_range(
        "2018-01-01", periods=len(sframe), freq="14D", tz="UTC"
    )
    # 1. Baseline vs pruned design counts
    d_base = ablate.design(sframe, held=sheld, variant="layrng,size,sv_gp_mo,marks,seg")
    d_simp = ablate.design(
        sframe,
        held=sheld,
        variant=(
            "layrng,size,sv_gp_mo16,marks,seg_add_lr12,floor_poly,"
            "umean_core,ad_core,bld_core,phase_compact,no_season2,"
            "spatial_k40,scalar_sigma,biweekly_walk"
        ),
    )
    assert len(d_simp.names) < len(d_base.names)
    assert not any(n.startswith("unit:elev_f2") for n in d_simp.names)
    assert "unit:elev_f_lin" in d_simp.names
    assert ablate.gp_spec(d_simp.names) == []  # zero GPs left!
    assert sum(len(s["sd"]) for s in d_simp.surfaces) <= 40
    assert d_simp.phase_map.shape[1] < d_base.phase_map.shape[1]
    assert "phase:22-25" not in d_simp.names
    assert "sin2" not in d_simp.names

    # 2. End-to-end MCMC smoke test with zero GPs + scalar_sigma + biweekly_walk + scale_2x
    monkeypatch.setattr(
        ablate,
        "ACTIVE_VARIANT",
        (
            "layrng",
            "size",
            "sv_gp_mo16",
            "marks",
            "seg_add_lr12",
            "floor_poly",
            "scalar_sigma",
            "biweekly_walk",
            "scale_2x",
        ),
    )
    settings = ablate.Settings(
        chains=2, warmup=4, draws=4, keep_every=2, budget_seconds=None
    )
    out = ablate.run(
        ablate.subset(d_simp, ~sheld), ablate.Priors(), settings, log=lambda _: None
    )
    assert out["kept"]["sigma"].shape == (2, 2, 4)
    # scalar_sigma broadcasts identical values across all 4 bedroom groups
    np.testing.assert_array_equal(
        out["kept"]["sigma"][..., 0], out["kept"]["sigma"][..., 3]
    )
    # biweekly_walk still interpolates kept/L back to exact weekly length d_simp.weeks + 1
    assert out["kept"]["L"].shape == (2, 2, d_simp.weeks + 1)
    assert out["result"]["gibbs"]["n_sigma"] == 1
    assert out["result"]["gibbs"]["walk_stride"] == 2
    assert out["result"]["gibbs"]["scale_passes"] == 2
    assert out["result"]["gibbs"]["n_gp"] == 0
    # Zero-GP diagnostics and summarize work without KeyError on gp_amp
    diag = ablate.diagnostics(out["trace"], d_simp.names)
    assert np.isfinite(diag["max_rhat"])
    summ = ablate.summarize(out["kept"], d_simp.names)
    assert "segment_gp" not in summ


def test_seg_add_and_lowrank_covariance_exact(screen_rows):
    """Verify seg_add produces additive GP specs and lowrank_segment_paths matches anchored
    Matérn-3/2 covariance at 2024q1 = 0."""
    sframe, sheld = screen_rows
    sframe = sframe.copy()
    sframe["price_at"] = pd.date_range(
        "2018-01-01", periods=len(sframe), freq="45D", tz="UTC"
    )
    sframe["latest_day"] = sframe["price_at"].dt.tz_convert(None)
    d_add = ablate.design(sframe, held=sheld, variant="seg_add")
    specs = ablate.gp_spec(d_add.names)
    seg_specs = [s for s in specs if s["name"].startswith("seg:")]
    assert 1 <= len(seg_specs) <= 4
    assert not any(c.endswith(":2024q1") for s in seg_specs for c in s["cols"])

    # Verify semi-annual stride cuts knot count roughly in half on a multi-year grid
    d_long = td._design(n=400, weeks=160)
    d_q = ablate.additive_segment_paths(d_long, stride=1)
    d_s = ablate.additive_segment_paths(d_long, stride=2)
    q_cols = [n for n in d_q.names if n.startswith("seg:")]
    s_cols = [n for n in d_s.names if n.startswith("seg:")]
    assert len(s_cols) < len(q_cols)
    assert not any(c.endswith(":2024q1") for c in s_cols)
    d_semi = ablate.design(sframe, held=sheld, variant="seg_add_semi")
    assert any(n.startswith("seg:") for n in d_semi.names)

    d_lr = ablate.design(sframe, held=sheld, variant="seg_add_lr16")
    assert any(n.startswith("seglr:") for n in d_lr.names)
    assert not any(n.startswith("seg:") for n in d_lr.names)
    # Floor GPs remain when floor_poly is not passed, while segment GPs are 0
    assert all(not s["name"].startswith("seg:") for s in ablate.gp_spec(d_lr.names))
