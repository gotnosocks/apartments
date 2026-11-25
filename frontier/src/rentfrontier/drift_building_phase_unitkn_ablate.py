"""Modular single-change screening & ablation model (`drift-building-phase-unitkn-ablate`).

Built on the `l2bt` Student-t unitkn baseline (`drift_building_phase_unitkn_level_bedtext`),
accepting `--variant TOKEN[,TOKEN,...]` so each unified-model component and queued `docs/TODO.md`
idea can be screened cleanly one change at a time (or in curated Wave-2 combinations) on Modal
using `ops/modal-screen`.

Supported variant tokens (all strictly leak-free):
- `sbf`: `same_bed_first=True` in `sizefill.asof_size` (own -> same-bed -> line -> other-bed).
- `bedunit`: adds unit-ever `uever:ad:bed_text_smaller` (replaces `bedtext` with `bedunit`).
- `layrng`: adds 8 strictly as-of bed/bath change and range columns (`layout` + `layout-range`).
- `size`: adds filled-size slope (`ad:size_imp_log_size_rel`) + `ad:large_01br`.
- `y1`: adds calendar-year additive noise scale factors with 2024 as the reference.
- `y1_pre2024`: restricts year factors to 2014–2023, keeping 2024 onward at reference.
- `marks`: adds all 6 exogenous noise-scale marks from `unified`.
- `marks_no_thin`: adds 5 exogenous noise-scale marks (excluding `mark:thin_first_ad`).
- `mark_changed`, `mark_baths`, `mark_floor1`, `mark_large01br`, `mark_thin`:
  add the selected unified scale marks. `mark_baths` adds both bath categories.
- `seg`: adds the identifiable quarterly Matérn-3/2 segment paths from `unified-seg`.
- `covid_mean`: adds 14-day-lagged NYC DOHMH borough-relative Covid hospitalizations/cases and
  Covid x property-type (Manhattan, 2+BR, doorman, private outdoor) mean interactions.
- `covid_vol`: adds 2 causal 14-day-lagged Covid volatility regime scale marks (`surge`, `elevated`).
- `sv_gp`: replaces discrete calendar years with an exact anchored whitened Matérn-3/2
  stochastic volatility GP over 52 quarters (`2014 Q1-2026 Q4`, anchored at `2024 Q1 = 0`).
- `sv_gp_mo`: monthly anchored Matérn-3/2 stochastic volatility GP (`156` months, `ℓ=1.0 yr`,
  24 modes, anchored at `2024-01`, clamped at the last training month).
- `sv_gp_wk`: weekly anchored Matérn-3/2 stochastic volatility GP (`672` weeks matching `L(t)`,
  `ℓ=1.0 yr`, 28 modes, anchored at `2024-01-01`, clamped at the last training week).
- `sv_gp_wk05`: weekly anchored Matérn-3/2 stochastic volatility GP with sharper `ℓ=0.5 yr`
  (`672` weeks, 36 modes, anchored at `2024-01-01`, clamped at the last training week).
- `vel_gp`: adds 2 strictly leak-free causal trailing market-velocity scale factors
  (`vel:down`, `vel:up`) driven by prior training-row rent trend speed `|L'(t)|` (quarterly).
- `vel_gp_wk`: weekly-resolution version of `vel_gp` (exact same causal weekly EMA slope,
  evaluated directly at each listing's week instead of quarterly medians).
- `concess_gap`: adds strictly as-of building concession history x 2020-2022 gap columns.
- `stab_dhcr`: joins DHCR rent-stabilized BBL counts (as-of prior year) + stabilized x regime
  (2020-2021 dip, 2022+ boom) path decoupling terms.
- `income_scale`: adds noise scale mark for `income_restricted` ads.
- `u4_bed`: adds per-bedroom new-unit (`phase == none`) noise scale marks for 2BR and 3+BR.
- `mark_changed_bed`: adds separate noise scale mark for bedroom-count changes (`ad:beds_up_prev | ad:beds_down_prev`).
- `mark_floor_unk`: adds noise scale mark for unknown floor (`unit:elev_floor_unknown | unit:walkup_floor_unknown`).
- `mark_tenure`: adds MapPLUTO `bld:coop` mean col + `mark:condo` and `mark:coop` noise scale marks.
- `floor1_mean`: adds explicit `unit:floor_1` mean col (restores discrete ground-floor penalty erased by `floor_poly`).
- `u1_size_scale`: adds continuous `u1:log_size_gt1k = max(0, log(sqft / 1000))` noise scale factor.
- `attr_changes`: adds strictly causal count of changed binary ad/unit attributes since prior training ad (`1`, `2`, `3+`).
- `mark_sparse_photos`: adds noise scale mark for ads with `<= 1` photo (`ad:log1p_photos <= log(2)`).
- `mark_townhouse`: adds MapPLUTO `bld:small_lot_le4` (`unitsres in 1..4`) mean col + `mark:small_lot_le4` scale mark.
- `bld_bimonthly`, `bld_monthly`: refine building AR(1) step resolution from 4/yr to 6/yr or 12/yr.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import (
    building_attrs,
    building_zones_floor,
    building_zones_floor_asof,
    building_zones_floor_asof3,
    drift,
    drift_building_bedtext_layout,
    drift_building_bedtext_layout_range,
    drift_building_phase_segment,
    drift_building_phase_unitkn_level,
    drift_building_phase_unitkn_level_bedtext,
    drift_building_phase_unitkn_level_bedunit,
    drift_building_phase_unitkn_unified,
    drift_building_phase_unitkn_unified_seg,
    drift_building_phase_year,
    two_zone,
)
from .building_zones_kitchen_sink import EXTERNAL_ROOT, append
from .drift_building_phase_unitkn_level import (  # noqa: F401
    AD_FIELDS,
    BLD_SD_PRIOR,
    EDGES,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    LEVELS,
    PHASES,
    PROGRESS,
    ROW_DOF,
    TRACED,
    UNIT_DOF,
    ZONES,
    Design,
    Priors,
    Settings,
    make_sampler,
    months_since_previous,
    phase_index,
    phase_levels,
    site_rows,
    site_zone,
    split_index,
    subset,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-unitkn-ablate"
COVID_CSV = EXTERNAL_ROOT / "covid" / "20261122-nychealth" / "data-by-day.csv"
RENTSTAB_PARQUET = EXTERNAL_ROOT / "rentstab" / "20261008-b487c8a" / "rentstab.parquet"

MARK_TOKENS = {
    "mark_changed": ("mark:changed_counts",),
    "mark_baths": ("mark:baths_2", "mark:baths_3p"),
    "mark_floor1": ("mark:floor_1",),
    "mark_large01br": ("mark:large_01br",),
    "mark_thin": ("mark:thin_first_ad",),
}
SEG_TOKENS = (
    "seg",
    "seg_add",
    "seg_add_semi",
    "seg_add_lr16",
    "seg_add_lr12",
    "seg_lr16",
)
SV_TOKENS = ("sv_gp", "sv_gp_mo", "sv_gp_mo16", "sv_gp_mo12", "sv_gp_wk", "sv_gp_wk05")
VEL_TOKENS = ("vel_gp", "vel_gp_wk")
SPATIAL_TOKENS = ("spatial_k80", "spatial_k40")
BLD_STEP_TOKENS = {"bld_bimonthly": 6, "bld_monthly": 12}

ALL_TOKENS = (
    "sbf",
    "bedunit",
    "layrng",
    "size",
    "y1",
    "y1_pre2024",
    "marks",
    "marks_no_thin",
    *MARK_TOKENS,
    *SEG_TOKENS,
    "covid_mean",
    "covid_vol",
    *SV_TOKENS,
    *VEL_TOKENS,
    "concess_gap",
    "stab_dhcr",
    "income_scale",
    "u4_bed",
    # Model-simplification & parameter-pruning tokens
    "floor_poly",
    "no_umean",
    "umean_core",
    "no_ad_ks",
    "ad_core",
    "no_bld_ks",
    "bld_core",
    "scalar_sigma",
    "phase_compact",
    "no_phase_mean",
    "no_season2",
    *SPATIAL_TOKENS,
    "biweekly_walk",
    "no_bld_ar",
    "scale_2x",
    "fast_scales",
    "fast_scales_p6",
    "slow_trim",
    # Track B1/B2 (2026-11-24): A1 audit discoveries & finer building AR(1) paths
    "mark_changed_bed",
    "mark_floor_unk",
    "mark_tenure",
    "floor1_mean",
    "u1_size_scale",
    "attr_changes",
    "mark_sparse_photos",
    "mark_townhouse",
    *BLD_STEP_TOKENS,
)

# Anchored Matérn-3/2 stochastic volatility GP constants (`sv_gp*`).
SV_FIRST_YEAR = 2014
SV_QUARTERS = 52  # 2014 Q1 through 2026 Q4
SV_REF_QUARTER = 40  # 2024 Q1 (anchor: log scale = 0)
SV_AMP = 0.25  # prior log-scale sd (2 sd spans ~0.61x to 1.65x)
SV_LS = 1.0  # lengthscale in years
SV_MODES = 22  # orthogonal eigenmodes (>99% of Matérn-3/2 variance)

SV_MONTHS = 156  # 2014-01 through 2026-12
SV_REF_MONTH = 120  # 2024-01
SV_MO_MODES = 24  # >99% of Matérn-3/2 variance at ls=1.0 yr
SV_MO16_MODES = 16
SV_MO12_MODES = 12

SV_WEEK_START = pd.Timestamp("2013-12-02", tz="UTC")  # exact match to L(t) weekly grid
SV_WEEKS = 672  # 672 weeks (~2013-12-02 through late 2026)
SV_REF_WEEK = 526  # week of 2024-01-01
SV_WK_MODES = 28  # 99.27% of Matérn-3/2 variance at ls=1.0 yr
SV_WK05_LS = 0.5  # sharper 6-month lengthscale
SV_WK05_MODES = 36  # 97.68% of Matérn-3/2 variance at ls=0.5 yr

# Low-rank anchored Matérn-3/2 segment-path GP constants (`seg_*_lr*`).
SEG_LR_AMP = 0.05  # matches clean5-lat posterior segment GP amps (0.02-0.064)
SEG_LR_LS = 1.0  # lengthscale in years (matches clean5-lat posterior 0.67-1.15 yr)
SEG_LR_PRIOR_SD = 0.5  # drift.py default flag/general beta prior sd

# Core subsets for kitchen-sink pruning screens (chosen from clean5-lat posterior norms).
UMEAN_CORE_COLS = frozenset(
    {
        "umean:unit:log_size_rel",
        "umean:ad:log_size_rel_sq",
        "umean:unit:size_unknown",
        "umean:ad:months_free",
        "umean:ad:floorplan",
    }
)
AD_CORE_COLS = frozenset(
    {
        "ad:months_free",
        "ad:lease_short",
        "ad:lease_long",
        "ad:log_size_rel_sq",
        "ad:floorplan",
        "ad:log1p_photos",
    }
)
AD_VARIANT_PREFIXES = (
    "ad:beds_",
    "ad:baths_",
    "ad:bed_text",
    "ad:size_imp_",
    "ad:large_01br",
    "ad:concess_",
)
BLD_CORE_COLS = frozenset(
    {
        "bld:condo",
        "bld:class_D",
        "bld:log_height",
        "bld:height_unknown",
        "bld:log_units",
        "bld:units_unknown",
        "bld:altered_2000_on",
        "bld:doorman_full",
        "bld:doorman_part",
        "bld:gym",
        "bld:retail",
        "bld:retail_unknown",
        "bld:log_lot_front",
        "bld:log_area_per_unit",
        "bld:built_pre1900",
        "bld:built_2010_on",
        "bld:lot_unknown",
    }
)
SEASON2_DROP_COLS = frozenset(
    {
        "sin2",
        "cos2",
        "bed=1:full>=3",
        "flag:shared_space",
    }
)

# Causal market-velocity volatility constants (`vel_gp`).
VEL_SCALE = 0.15  # 15%/yr annualized trend speed maps to 1.0
VEL_CLIP = 0.60  # cap annualized velocity at 60%/yr

# Active variant tuple for the current CLI run (set in `main_run`, or passed to `design`).
ACTIVE_VARIANT: tuple[str, ...] = ()
_ACTIVE_SCALE_FACTORS: tuple[str, ...] = ()

_BORO_PREFIX = {
    1: "MN",
    2: "BX",
    3: "BK",
    4: "QN",
    5: "SI",
}


def parse_variant(spec_str: str | None) -> tuple[str, ...]:
    if not spec_str:
        return ()
    tokens = tuple(t.strip() for t in spec_str.split(",") if t.strip())
    bad = [t for t in tokens if t not in ALL_TOKENS]
    if bad:
        raise ValueError(f"unknown variant token(s): {bad}; valid: {ALL_TOKENS}")
    return tokens


def _extract_variant(argv: list[str]) -> tuple[tuple[str, ...], list[str]]:
    out: list[str] = []
    val: str | None = None
    i = 0
    while i < len(argv):
        if argv[i] == "--variant":
            if i + 1 >= len(argv):
                raise ValueError("--variant requires a value")
            val = argv[i + 1]
            i += 2
        elif argv[i].startswith("--variant="):
            val = argv[i].split("=", 1)[1]
            i += 1
        elif argv[i] == "--ablate" or argv[i].startswith("--ablate="):
            raise ValueError(
                "unknown flag --ablate; pass --variant TOKENS instead "
                "(b0.parse_known_args would otherwise silently drop it)"
            )
        else:
            out.append(argv[i])
            i += 1
    return parse_variant(val), out


def _quarter_index(frame: pd.DataFrame) -> np.ndarray:
    """Each row's quarter index in `[0, SV_QUARTERS - 1]` (`2014 Q1` .. `2026 Q4`, clamped)."""
    dt = pd.to_datetime(frame["price_at"], utc=True)
    q = (dt.dt.year.to_numpy(int) - SV_FIRST_YEAR) * 4 + (
        dt.dt.quarter.to_numpy(int) - 1
    )
    return np.clip(q, 0, SV_QUARTERS - 1)


def _month_index(frame: pd.DataFrame) -> np.ndarray:
    """Each row's month index in `[0, SV_MONTHS - 1]` (`2014-01` .. `2026-12`, clamped)."""
    dt = pd.to_datetime(frame["price_at"], utc=True)
    m = (dt.dt.year.to_numpy(int) - SV_FIRST_YEAR) * 12 + (
        dt.dt.month.to_numpy(int) - 1
    )
    return np.clip(m, 0, SV_MONTHS - 1)


def _week_index(frame: pd.DataFrame) -> np.ndarray:
    """Each row's week index in `[0, SV_WEEKS - 1]` on `L(t)`'s `2013-12-02` weekly grid."""
    dt = pd.to_datetime(frame["price_at"], utc=True)
    w = np.floor(((dt - SV_WEEK_START) / pd.Timedelta(days=7)).to_numpy(float)).astype(
        int
    )
    return np.clip(w, 0, SV_WEEKS - 1)


def _matern32_anchored_basis(
    t_years: np.ndarray,
    ref_idx: int,
    amp: float,
    ls: float,
    max_modes: int,
) -> np.ndarray:
    """Exact anchored whitened Matérn-3/2 eigenbasis `(len(t_years), m)` scaled by
    `1 / drift.PHASE_PRIOR`. Under `drift.py`'s i.i.d. `Normal(0, PHASE_PRIOR^2)` prior on
    each log factor, `B @ lf` has exact conditioned Matérn-3/2 covariance with `g(ref) = 0`."""
    r = np.abs(t_years[:, None] - t_years[None, :])
    u = np.sqrt(3.0) * r / ls
    K = (amp**2) * (1.0 + u) * np.exp(-u)
    k_ref = K[:, ref_idx]
    K_cond = K - np.outer(k_ref, k_ref) / K[ref_idx, ref_idx]
    K_cond = 0.5 * (K_cond + K_cond.T)
    evals, evecs = np.linalg.eigh(K_cond)
    order = np.argsort(evals)[::-1]
    evals = np.maximum(evals[order], 0.0)
    evecs = evecs[:, order]
    m = min(max_modes, int((evals > 1e-10).sum()))
    B = evecs[:, :m] * np.sqrt(evals[:m])[None, :] / drift.PHASE_PRIOR
    B[ref_idx, :] = 0.0
    B = np.round(B, 6)
    B[B == 0.0] = 0.0
    return B


def sv_gp_basis(
    resolution: str = "quarter",
    ls: float | None = None,
    max_modes: int | None = None,
) -> np.ndarray:
    """Anchored whitened Matérn-3/2 eigenbasis for `quarter`, `month`, or `week` grids."""
    if resolution == "quarter":
        t = SV_FIRST_YEAR + 0.125 + 0.25 * np.arange(SV_QUARTERS, dtype=float)
        return _matern32_anchored_basis(
            t,
            SV_REF_QUARTER,
            SV_AMP,
            SV_LS if ls is None else ls,
            SV_MODES if max_modes is None else max_modes,
        )
    if resolution == "month":
        t = SV_FIRST_YEAR + (np.arange(SV_MONTHS, dtype=float) + 0.5) / 12.0
        return _matern32_anchored_basis(
            t,
            SV_REF_MONTH,
            SV_AMP,
            SV_LS if ls is None else ls,
            SV_MO_MODES if max_modes is None else max_modes,
        )
    if resolution == "week":
        t = np.arange(SV_WEEKS, dtype=float) * (7.0 / 365.25)
        eff_ls = SV_LS if ls is None else ls
        default_modes = SV_WK05_MODES if eff_ls <= 0.6 else SV_WK_MODES
        return _matern32_anchored_basis(
            t,
            SV_REF_WEEK,
            SV_AMP,
            eff_ls,
            default_modes if max_modes is None else max_modes,
        )
    raise ValueError(f"unknown sv_gp resolution: {resolution!r}")


def sv_gp_features(
    frame: pd.DataFrame,
    train: np.ndarray | None = None,
    resolution: str = "quarter",
    ls: float | None = None,
    max_modes: int | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Matérn-3/2 stochastic-volatility basis features for `frame`.

    When `train` is provided for monthly/weekly grids, indices strictly after the last
    training bucket are clamped to the last training bucket so unobserved future periods
    smoothly inherit the final observed regime rather than oscillating in the eigenbasis.
    """
    B = sv_gp_basis(resolution=resolution, ls=ls, max_modes=max_modes)
    if resolution == "quarter":
        idx = _quarter_index(frame)
    elif resolution == "month":
        idx = _month_index(frame)
    elif resolution == "week":
        idx = _week_index(frame)
    else:
        raise ValueError(f"unknown sv_gp resolution: {resolution!r}")
    if train is not None and resolution != "quarter":
        tr = np.asarray(train, bool)
        if tr.any():
            idx = np.minimum(idx, int(idx[tr].max()))
    names = [f"sv:m{j:02d}" for j in range(B.shape[1])]
    return B[idx], names


def apply_floor_poly(d: Design) -> Design:
    """Replace the 68 floor GP dummies (`unit:elev_f2..64`, `unit:walkup_f2..6`) and 2 RBF
    GPs with 5 smooth strictly as-of basis columns (`elev_f_lin`, `elev_f_quad`, `elev_f_log`,
    `walkup_f2_4`, `walkup_f5p`). Zero extra I/O, -63 beta cols and -4 GP hypers."""
    elev_cols = [
        (j, int(n.rsplit("_f", 1)[1]))
        for j, n in enumerate(d.names)
        if n.startswith("unit:elev_f") and n.rsplit("_f", 1)[1].isdigit()
    ]
    walk_cols = [
        (j, int(n.rsplit("_f", 1)[1]))
        for j, n in enumerate(d.names)
        if n.startswith("unit:walkup_f") and n.rsplit("_f", 1)[1].isdigit()
    ]
    n = len(d.y)
    elev_floor = np.zeros(n, dtype=float)
    for j, k in elev_cols:
        elev_floor += d.x[:, j] * float(k)
    has_elev = elev_floor > 0.5
    e_lin = np.where(has_elev, (elev_floor - 1.0) / 30.0, 0.0)
    e_quad = e_lin * e_lin
    e_log = np.where(has_elev, np.log(np.maximum(elev_floor, 1.0)) / np.log(64.0), 0.0)

    walk_floor = np.zeros(n, dtype=float)
    for j, k in walk_cols:
        walk_floor += d.x[:, j] * float(k)
    w_2_4 = ((walk_floor >= 2.0) & (walk_floor <= 4.0)).astype(float)
    w_5p = (walk_floor >= 5.0).astype(float)

    drop = {d.names[j] for j, _ in elev_cols + walk_cols}
    d = drift.drop_columns(d, drop)
    new_names = [
        "unit:elev_f_lin",
        "unit:elev_f_quad",
        "unit:elev_f_log",
        "unit:walkup_f2_4",
        "unit:walkup_f5p",
    ]
    new_mat = np.column_stack([e_lin, e_quad, e_log, w_2_4, w_5p])
    return append(d, new_names, new_mat)


def apply_spatial_trunc(d: Design, per_zone: int) -> Design:
    """Keep only the top `per_zone` highest-sd spatial wave modes in each surface zone."""
    new_surfaces = []
    for s in d.surfaces:
        sd = np.asarray(s["sd"], float)
        basis = np.asarray(s["basis"], float)
        k = min(per_zone, len(sd))
        top = np.argsort(sd)[::-1][:k]
        top.sort()
        new_surfaces.append(s | {"basis": basis[:, top], "sd": sd[top]})
    return dataclasses.replace(d, surfaces=new_surfaces)


def _additive_path_indicators(d: Design) -> list[tuple[str, np.ndarray]]:
    """4 additive market-segment indicators (`zone:outer`, `bed:studio`, `bed:2br`,
    `bed:3br+`) relative to reference `manhattan` and `1br`."""
    zone_row = site_zone(d)[d.site]
    grp = np.asarray(d.group, int)
    cands = [
        ("zone:outer", (zone_row == 1).astype(float)),
        ("bed:studio", (grp == 0).astype(float)),
        ("bed:2br", (grp == 2).astype(float)),
        ("bed:3br+", (grp == 3).astype(float)),
    ]
    return [(name, ind) for name, ind in cands if ind.any() and not ind.all()]


def additive_segment_paths(d: Design, *, stride: int = 1) -> Design:
    """Additive identifiable Matérn-3/2 segment paths (4 paths instead of 7:
    1 zone path + 3 bedroom paths, dropping `2024q1`, retaining the 3 static `level:outer:*`
    columns). With `stride=1` (quarterly), cuts 371 -> 212 cols and 7 -> 4 segment GPs;
    with `stride=2` (semi-annual, `seg_add_semi`), cuts 371 -> ~104 cols while keeping
    learned Matérn-3/2 amplitude and lengthscale per path."""
    q_full = drift_building_phase_segment.quarter_starts(d)
    labels_full = [f"{t.year}q{t.quarter}" for t in q_full]
    ref_q = drift_building_phase_unitkn_unified_seg.REF_QUARTER
    if stride > 1:
        keep_idx = sorted(
            set(range(0, len(q_full), stride))
            | {len(q_full) - 1}
            | ({labels_full.index(ref_q)} if ref_q in labels_full else set())
        )
        q = q_full[keep_idx]
        labels = [labels_full[i] for i in keep_idx]
    else:
        q = q_full
        labels = labels_full
    knots = np.asarray((q - pd.Timestamp(d.start)).days, float) / (
        drift_building_phase_segment.YEAR_DAYS
    )
    H = drift_building_phase_segment.hat_weights(years(d), knots)
    denom = np.maximum(H.sum(axis=0), 1.0)

    lead_names, lead_x = drift_building_phase_segment.level_columns(d)
    cols: list[str] = list(lead_names)
    blocks: list[np.ndarray] = [lead_x] if lead_x.shape[1] else []
    keep_q = [j for j, lbl in enumerate(labels) if lbl != ref_q]
    for pname, ind in _additive_path_indicators(d):
        share = (ind[:, None] * H).sum(axis=0) / denom
        mat = (ind[:, None] - share[None, :]) * H
        blocks.append(mat[:, keep_q])
        cols.extend(f"seg:{pname}:{labels[j]}" for j in keep_q)
    if not cols:
        return d
    return append(d, cols, np.hstack(blocks))


def lowrank_segment_paths(
    d: Design,
    *,
    additive: bool = True,
    max_modes: int = 16,
    amp: float = SEG_LR_AMP,
    ls: float = SEG_LR_LS,
) -> Design:
    """Low-rank whitened Matérn-3/2 eigenbasis for segment paths (anchored at `2024q1 = 0`).

    Each eigenmode column is scaled by `sqrt(eval_j) * amp / SEG_LR_PRIOR_SD` so `drift.py`'s
    `Normal(0, 0.5^2)` prior on `beta` induces the exact conditioned Matérn-3/2 GP prior on
    every path with zero extra GP hyperparameters and no quarter-knot correlation ridge.
    """
    q = drift_building_phase_segment.quarter_starts(d)
    knots = np.asarray((q - pd.Timestamp(d.start)).days, float) / (
        drift_building_phase_segment.YEAR_DAYS
    )
    labels = [f"{t.year}q{t.quarter}" for t in q]
    ref_q = drift_building_phase_unitkn_unified_seg.REF_QUARTER
    ref_idx = (
        labels.index(ref_q)
        if ref_q in labels
        else int(
            np.argmin(
                np.abs(
                    (q - drift_building_phase_segment.REFERENCE).days.to_numpy(float)
                )
            )
        )
    )
    t_yr = (q - drift_building_phase_segment.REFERENCE).days.to_numpy(float) / (
        drift_building_phase_segment.YEAR_DAYS
    )
    # Build anchored Matérn-3/2 eigenbasis scaled for `Normal(0, SEG_LR_PRIOR_SD^2)` beta prior.
    r = np.abs(t_yr[:, None] - t_yr[None, :])
    u = np.sqrt(3.0) * r / ls
    K = (amp**2) * (1.0 + u) * np.exp(-u)
    k_ref = K[:, ref_idx]
    K_cond = K - np.outer(k_ref, k_ref) / K[ref_idx, ref_idx]
    K_cond = 0.5 * (K_cond + K_cond.T)
    evals, evecs = np.linalg.eigh(K_cond)
    order = np.argsort(evals)[::-1]
    evals = np.maximum(evals[order], 0.0)
    evecs = evecs[:, order]
    m = min(max_modes, int((evals > 1e-12).sum()))
    B = evecs[:, :m] * np.sqrt(evals[:m])[None, :] / SEG_LR_PRIOR_SD
    B[ref_idx, :] = 0.0

    H = drift_building_phase_segment.hat_weights(years(d), knots)
    denom = np.maximum(H.sum(axis=0), 1.0)
    lead_names, lead_x = drift_building_phase_segment.level_columns(d)
    cols: list[str] = list(lead_names)
    blocks: list[np.ndarray] = [lead_x] if lead_x.shape[1] else []

    if additive:
        paths = _additive_path_indicators(d)
    else:
        seg = drift_building_phase_segment.segment_index(d)
        snames = drift_building_phase_segment.segment_names(d)
        present = [k for k in range(len(snames)) if (seg == k).any()]
        ref_seg = drift_building_phase_unitkn_unified_seg.REF_SEGMENT
        ref_k = (
            snames.index(ref_seg)
            if ref_seg in snames and snames.index(ref_seg) in present
            else present[0]
        )
        paths = [(snames[k], (seg == k).astype(float)) for k in present if k != ref_k]

    for pname, ind in paths:
        share = (ind[:, None] * H).sum(axis=0) / denom
        centered_H = (ind[:, None] - share[None, :]) * H
        blocks.append(centered_H @ B)
        cols.extend(f"seglr:{pname}:m{j:02d}" for j in range(m))
    if not cols:
        return d
    return append(d, cols, np.hstack(blocks))


def vel_gp_features(
    frame: pd.DataFrame,
    train: np.ndarray,
    weekly: bool = False,
) -> tuple[np.ndarray, list[str]]:
    """Strictly leak-free causal trailing market-velocity scale features (`vel:down`, `vel:up`).

    Reads ONLY training rows (`train`) to build a bedroom-residualized weekly median log-ask
    index, applies a strictly forward causal EMA (`alpha=0.25`), takes the 2-week-lagged
    trailing 16-week annualized slope, and maps either directly by week (`weekly=True`,
    clamped at the last training week) or via quarterly medians (`weekly=False`) so every
    row's velocity depends solely on earlier training ads (zero held-out target leakage).
    """
    tr = np.asarray(train, bool)
    q_idx = _quarter_index(frame)
    names = ["vel:down", "vel:up"]
    if not tr.any() or "latest_ask" not in frame:
        return np.zeros((len(frame), 2), dtype=float), names

    dt = pd.to_datetime(frame["price_at"], utc=True)
    ask = pd.to_numeric(frame["latest_ask"], errors="coerce").to_numpy(float)
    valid = tr & np.isfinite(ask) & (ask > 0)
    if valid.sum() < 20:
        return np.zeros((len(frame), 2), dtype=float), names

    # Residualize by training-only bedroom medians to avoid bedroom-mix artifacts.
    bed = frame["bedrooms"].clip(0, 5).fillna(-1).astype(int).to_numpy()
    log_y = np.log(ask[valid])
    bed_v = bed[valid]
    med_by_bed = {b: float(np.median(log_y[bed_v == b])) for b in np.unique(bed_v)}
    global_med = float(np.median(log_y))
    resid = log_y - np.array([med_by_bed.get(b, global_med) for b in bed_v])

    t0 = SV_WEEK_START
    wk_all = ((dt - t0) / pd.Timedelta(days=7)).to_numpy(float)
    wk_v = np.floor(wk_all[valid]).astype(int)
    w_min = int(min(0, wk_v.min()))
    w_max = int(max(int(np.floor(wk_all.max())), wk_v.max()))
    n_wk = w_max - w_min + 1

    # Weekly median on training rows, forward-filled causally across sparse early weeks.
    s_wk = pd.Series(resid).groupby(wk_v - w_min).median()
    m_wk = np.full(n_wk, np.nan, dtype=float)
    m_wk[s_wk.index.to_numpy(int)] = s_wk.to_numpy(float)
    first_valid = int(np.flatnonzero(np.isfinite(m_wk))[0])
    m_wk[:first_valid] = m_wk[first_valid]
    for w in range(first_valid + 1, n_wk):
        if not np.isfinite(m_wk[w]):
            m_wk[w] = m_wk[w - 1]

    # Strictly causal forward EMA (half-life ~2.4 weeks) and 2-week-lagged 16-week slope.
    ema = np.empty(n_wk, dtype=float)
    ema[0] = m_wk[0]
    for w in range(1, n_wk):
        ema[w] = 0.25 * m_wk[w] + 0.75 * ema[w - 1]
    vel_wk = np.zeros(n_wk, dtype=float)
    lag, span = 2, 16
    if n_wk > lag + span:
        vel_wk[lag + span :] = (ema[span:-lag] - ema[: -(lag + span)]) * (52.0 / span)

    if weekly:
        last_tr_w = int(wk_v.max()) - w_min
        row_w = np.clip(np.floor(wk_all).astype(int) - w_min, 0, last_tr_w)
        v_raw = vel_wk[row_w]
        v_down = np.round(np.clip(-v_raw, 0.0, VEL_CLIP) / VEL_SCALE, 4)
        v_up = np.round(np.clip(v_raw, 0.0, VEL_CLIP) / VEL_SCALE, 4)
        v_down[v_down == 0.0] = 0.0
        v_up[v_up == 0.0] = 0.0
        return np.column_stack([v_down, v_up]), names

    # Map each quarter to the median causal velocity across weeks in that quarter.
    wk_dates = t0 + pd.to_timedelta((np.arange(n_wk) + w_min) * 7, unit="D")
    wk_q = np.clip(
        (wk_dates.year.to_numpy(int) - SV_FIRST_YEAR) * 4
        + (wk_dates.quarter.to_numpy(int) - 1),
        0,
        SV_QUARTERS - 1,
    )
    vel_q = np.zeros(SV_QUARTERS, dtype=float)
    for q in range(SV_QUARTERS):
        in_q = wk_q == q
        if in_q.any():
            vel_q[q] = float(np.median(vel_wk[in_q]))
        elif q > 0:
            vel_q[q] = vel_q[q - 1]

    v_down = np.round(np.clip(-vel_q, 0.0, VEL_CLIP) / VEL_SCALE, 4)
    v_up = np.round(np.clip(vel_q, 0.0, VEL_CLIP) / VEL_SCALE, 4)
    v_down[v_down == 0.0] = 0.0
    v_up[v_up == 0.0] = 0.0
    mat = np.column_stack([v_down[q_idx], v_up[q_idx]])
    return mat, names


def compact_continuous_phase_map(
    factor_names: list[str],
    matrix: np.ndarray,
    train: np.ndarray,
) -> tuple[np.ndarray, tuple[str, ...], np.ndarray, list[str]]:
    """Compress a `(rows, F)` real-valued additive factor matrix into unique observed cells.

    Guarantees row 0 of `phase_map` is the exact all-zero reference cell (even when columns
    contain negative values that `np.unique` sorts before zero).
    """
    tr = np.asarray(train, bool)
    M_raw = np.asarray(matrix, dtype=float)
    keep = [j for j in range(M_raw.shape[1]) if np.abs(M_raw[tr, j]).max() > 1e-9]
    kept_names = [factor_names[j] for j in keep]
    if not keep:
        return (
            np.zeros(len(M_raw), dtype=np.int64),
            ("ref",),
            np.zeros((1, 0), dtype=float),
            [],
        )
    M = np.round(M_raw[:, keep], 6)
    M[M == 0.0] = 0.0
    zero_row = np.zeros((1, len(keep)), dtype=float)
    stacked = np.vstack([zero_row, M])
    uniq, inv = np.unique(stacked, axis=0, return_inverse=True)
    # Move the all-zero reference row to index 0 (required by `drift.make_sampler`).
    zero_pos = int(inv[0])
    if zero_pos != 0:
        perm = np.arange(len(uniq))
        perm[0], perm[zero_pos] = zero_pos, 0
        uniq = uniq[perm]
        inv_map = np.empty(len(uniq), dtype=np.int64)
        inv_map[perm] = np.arange(len(uniq), dtype=np.int64)
        inv = inv_map[inv]
    assert not uniq[0].any(), "reference cell must be all zeros"
    cell_idx = inv[1:].astype(np.int64)
    cell_names = tuple("ref" if i == 0 else f"cell_{i}" for i in range(len(uniq)))
    return cell_idx, cell_names, uniq.astype(float), kept_names


def _col(d: Design, name: str) -> np.ndarray:
    return drift_building_phase_unitkn_unified._col(d, name)


def _building_bbl(buildings: pd.Series) -> pd.Series:
    reg = pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"])
    reg = reg.dropna(subset=["bbl"]).drop_duplicates("building")
    bmap = reg.set_index(reg["building"].astype(str))["bbl"].astype("int64")
    return buildings.astype(str).map(bmap)


def pluto_building_flags(
    buildings: pd.Series, pluto_path: Path | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Static MapPLUTO building-level flags `(is_coop, is_small_lot_le4)` joined by BBL."""
    ppath = pluto_path or building_attrs.PLUTO
    pluto = pd.read_parquet(ppath, columns=["bbl", "bldgclass", "unitsres"])
    pluto = pluto.dropna(subset=["bbl"]).copy()
    pluto["bbl"] = pd.to_numeric(pluto["bbl"], errors="coerce")
    pluto = pluto.dropna(subset=["bbl"]).drop_duplicates("bbl")
    pluto["bbl"] = pluto["bbl"].astype("int64")
    cls_map = pluto.set_index("bbl")["bldgclass"].fillna("").astype(str)
    ur_map = pd.to_numeric(pluto.set_index("bbl")["unitsres"], errors="coerce")

    bbl = _building_bbl(buildings)
    bcls = bbl.map(cls_map).fillna("")
    unitsres = bbl.map(ur_map).to_numpy(float)
    is_coop = bcls.isin(building_attrs.COOP_CLASSES).to_numpy(float)
    is_small_lot = ((unitsres >= 1.0) & (unitsres <= 4.0)).astype(float)
    return is_coop, is_small_lot


_U1_BED_MEDIAN_SQFT = {0: 480.0, 1: 700.0, 2: 950.0, 3: 1250.0, 4: 1650.0}


def u1_size_scale_feature(d: Design, frame: pd.DataFrame) -> np.ndarray:
    """Continuous size-dependent noise-scale covariate `max(0, log(sqft / 1000))`
    reconstructed strictly as-of from `unit:log_size_rel` and `bedrooms`, rounded to 0.1
    log-unit steps (capped at 2.0) to keep `phase_map` cells compact."""
    lsr = _col(d, "unit:log_size_rel")
    unk = _col(d, "unit:size_unknown") > 0.5
    bd = np.clip(frame["bedrooms"].fillna(1).to_numpy(int), 0, 4)
    med = np.array([_U1_BED_MEDIAN_SQFT[int(b)] for b in bd], dtype=float)
    log_sqft_1k = lsr + np.log(med / 1000.0)
    raw = np.where(unk, 0.0, np.clip(np.maximum(0.0, log_sqft_1k), 0.0, 2.0))
    out = np.round(raw, 1)
    out[out == 0.0] = 0.0
    return out


_ATTR_CHANGE_PREFIXES = (
    "ad:exposure_",
    "ad:feat_",
    "ad:fireplace_",
    "ad:pets_",
    "ad:private_outdoor_",
    "ad:views_",
    "ad:lease_",
    "unit:laundry_",
    "flag:",
)
_ATTR_CHANGE_EXACT = frozenset(
    {
        "ad:floorplan",
        "ad:tour3d",
        "ad:video",
        "ad:months_free",
        "unit:dishwasher",
        "unit:penthouse",
        "unit:garden",
    }
)


def attr_change_marks(
    frame: pd.DataFrame, d: Design, train: np.ndarray
) -> tuple[np.ndarray, list[str]]:
    """Strictly causal count of binary ad/unit attribute flags that differ from the unit's
    latest strictly earlier training ad (`1`, `2`, `3+` changed)."""
    names = ["mark:attr_chg_1", "mark:attr_chg_2", "mark:attr_chg_3p"]
    cols = [
        j
        for j, n in enumerate(d.names)
        if n in _ATTR_CHANGE_EXACT or n.startswith(_ATTR_CHANGE_PREFIXES)
    ]
    n = len(frame)
    if not cols or "unit_id" not in frame or "price_at" not in frame:
        return np.zeros((n, 3), dtype=float), names

    tr = np.asarray(train, bool)
    mat = (d.x[:, cols] > 0.5).astype(np.uint8)
    uid = frame["unit_id"]
    has_uid = uid.notna().to_numpy(bool)
    keys = (
        frame["building"].astype(str) + "\x1f" + uid.fillna("").astype(str)
    ).to_numpy()
    ts = pd.to_datetime(frame["price_at"], utc=True).astype("int64").to_numpy()

    # Sort by (unit_key, timestamp) so each unit's history is contiguous and time-ordered.
    valid_idx = np.flatnonzero(has_uid)
    order = valid_idx[np.lexsort((ts[valid_idx], keys[valid_idx]))]
    prev_tr = np.full(n, -1, dtype=np.int64)

    # Walk contiguous unit blocks; maintain last strictly-earlier training row index.
    i = 0
    m = len(order)
    while i < m:
        k = keys[order[i]]
        j = i + 1
        while j < m and keys[order[j]] == k:
            j += 1
        last_tr = -1
        p = i
        while p < j:
            t_cur = ts[order[p]]
            q = p + 1
            while q < j and ts[order[q]] == t_cur:
                q += 1
            # All rows at timestamp t_cur see only training rows strictly before t_cur.
            if last_tr >= 0:
                prev_tr[order[p:q]] = last_tr
            for r in range(p, q):
                idx = order[r]
                if tr[idx]:
                    last_tr = idx
            p = q
        i = j

    has_prev = prev_tr >= 0
    diff_cnt = np.zeros(n, dtype=np.int32)
    if has_prev.any():
        hp = np.flatnonzero(has_prev)
        diff_cnt[hp] = np.bitwise_xor(mat[hp], mat[prev_tr[hp]]).sum(axis=1)
    out = np.column_stack(
        [
            (diff_cnt == 1).astype(float),
            (diff_cnt == 2).astype(float),
            (diff_cnt >= 3).astype(float),
        ]
    )
    return out, names


def _load_covid_daily(csv_path: Path = COVID_CSV) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["day"] = pd.to_datetime(df["date_of_interest"], format="%m/%d/%Y", utc=True)
    df = df.sort_values("day", kind="stable").reset_index(drop=True)
    return df


def covid_features(
    frame: pd.DataFrame, d: Design, csv_path: Path = COVID_CSV
) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Strictly causal 14-day-lagged NYC Covid-19 mean interactions and volatility regime."""
    cov = _load_covid_daily(csv_path)
    ad_day = pd.to_datetime(frame["price_at"], utc=True).dt.floor("D")
    lag_day = ad_day - pd.Timedelta(days=14)

    cols = [
        "day",
        "HOSP_COUNT_7DAY_AVG",
        "CASE_COUNT_7DAY_AVG",
        "MN_HOSPITALIZED_COUNT_7DAY_AVG",
        "BX_HOSPITALIZED_COUNT_7DAY_AVG",
        "BK_HOSPITALIZED_COUNT_7DAY_AVG",
        "QN_HOSPITALIZED_COUNT_7DAY_AVG",
        "SI_HOSPITALIZED_COUNT_7DAY_AVG",
        "MN_CASE_COUNT_7DAY_AVG",
        "BX_CASE_COUNT_7DAY_AVG",
        "BK_CASE_COUNT_7DAY_AVG",
        "QN_CASE_COUNT_7DAY_AVG",
        "SI_CASE_COUNT_7DAY_AVG",
    ]
    q = pd.DataFrame({"row": np.arange(len(frame)), "day": lag_day.to_numpy()})
    merged = (
        pd.merge_asof(
            q.sort_values("day", kind="stable"),
            cov[cols],
            on="day",
            direction="backward",
        )
        .set_index("row")
        .reindex(q["row"])
    )
    # Zero before Covid began (Feb 29, 2020) and after NYC DOHMH data ends? Keep backward-fill
    # only through 2025-10-13; rows >30 days past max Covid date are post-pandemic (0).
    max_cov = cov["day"].max()
    post_end = (lag_day > (max_cov + pd.Timedelta(days=30))).to_numpy(bool)
    for c in cols[1:]:
        v = merged[c].fillna(0.0).to_numpy(float, copy=True)
        v[post_end] = 0.0
        merged[c] = v

    nyc_hosp = merged["HOSP_COUNT_7DAY_AVG"].to_numpy(float)
    nyc_case = merged["CASE_COUNT_7DAY_AVG"].to_numpy(float)
    log_nyc_hosp = np.log1p(np.maximum(nyc_hosp, 0.0)) / 5.0  # ~O(1) scale

    bbl = _building_bbl(frame["building"])
    boro_code = (bbl // 10**9).fillna(0).astype(int).to_numpy()
    boro_hosp = np.zeros(len(frame), float)
    boro_case = np.zeros(len(frame), float)
    for code, pfx in _BORO_PREFIX.items():
        m = boro_code == code
        if m.any():
            boro_hosp[m] = merged[f"{pfx}_HOSPITALIZED_COUNT_7DAY_AVG"].to_numpy(float)[
                m
            ]
            boro_case[m] = merged[f"{pfx}_CASE_COUNT_7DAY_AVG"].to_numpy(float)[m]

    has_boro = boro_code > 0
    boro_hosp_rel = np.where(
        has_boro,
        np.log1p(np.maximum(boro_hosp, 0.0))
        - np.log1p(np.maximum(nyc_hosp / 5.0, 0.0)),
        0.0,
    )
    boro_case_rel = np.where(
        has_boro,
        np.log1p(np.maximum(boro_case, 0.0))
        - np.log1p(np.maximum(nyc_case / 5.0, 0.0)),
        0.0,
    )

    is_manh = (boro_code == 1).astype(float)
    is_2pbr = (frame["bedrooms"].fillna(0).to_numpy(float) >= 2).astype(float)
    is_doorman = (
        (_col(d, "bld:doorman_full") > 0.5) | (_col(d, "bld:doorman_part") > 0.5)
    ).astype(float)
    is_outdoor = (
        (_col(d, "unit:private_outdoor_space") > 0.5)
        | (_col(d, "bld:amen_shared_outdoor_space") > 0.5)
    ).astype(float)

    mean_mat = np.column_stack(
        [
            boro_hosp_rel,
            boro_case_rel,
            log_nyc_hosp * is_manh,
            log_nyc_hosp * is_2pbr,
            log_nyc_hosp * is_doorman,
            log_nyc_hosp * is_outdoor,
        ]
    )
    mean_names = [
        "covid:boro_hosp_rel",
        "covid:boro_case_rel",
        "covid:hosp_x_manh",
        "covid:hosp_x_2pbr",
        "covid:hosp_x_doorman",
        "covid:hosp_x_outdoor",
    ]
    vol_mat = np.column_stack(
        [
            (nyc_hosp >= 150.0).astype(float),
            ((nyc_hosp >= 30.0) & (nyc_hosp < 150.0)).astype(float),
        ]
    )
    return mean_mat, mean_names, vol_mat


def concession_gap_features(
    frame: pd.DataFrame, train: np.ndarray, rows_path: Path | None = None
) -> tuple[np.ndarray, list[str]]:
    """Strictly causal 2020-2022 concession-building history and unrecorded-concession gap."""
    rpath = rows_path or building_zones_floor_asof3.ROWS
    raw = pd.read_parquet(rpath, columns=["listing_id", "months_free"])
    raw = raw.drop_duplicates("listing_id")
    mf_map = raw.set_index(raw["listing_id"].astype(str))["months_free"]
    mf = frame["listing_id"].astype(str).map(mf_map).fillna(0.0).to_numpy(float)
    row_has = (mf > 0.0).astype(float)

    day = pd.to_datetime(frame["price_at"], utc=True).dt.floor("D")
    yr = day.dt.year.to_numpy()
    is_20_22 = ((yr >= 2020) & (yr <= 2022)).astype(float)

    q = pd.DataFrame(
        {
            "row": np.arange(len(frame)),
            "bld": frame["building"].astype(str).to_numpy(),
            "day": day.to_numpy(),
            "has": row_has,
        }
    )
    tr = np.asarray(train, bool)
    tr_days = (
        q.loc[tr]
        .groupby(["bld", "day"], sort=False)["has"]
        .agg(["count", "sum"])
        .reset_index()
        .sort_values("day", kind="stable")
    )
    if len(tr_days) > 0:
        tr_days["cum_n"] = tr_days.groupby("bld", sort=False)["count"].cumsum()
        tr_days["cum_c"] = tr_days.groupby("bld", sort=False)["sum"].cumsum()
        got = (
            pd.merge_asof(
                q[["row", "bld", "day"]].sort_values("day", kind="stable"),
                tr_days[["bld", "day", "cum_n", "cum_c"]],
                on="day",
                by="bld",
                allow_exact_matches=False,
            )
            .set_index("row")
            .reindex(q["row"])
        )
        cum_n = got["cum_n"].fillna(0.0).to_numpy(float)
        cum_c = got["cum_c"].fillna(0.0).to_numpy(float)
    else:
        cum_n = np.zeros(len(frame), float)
        cum_c = np.zeros(len(frame), float)

    bld_ever = (cum_c > 0.5).astype(float)
    bld_rate = np.where(cum_n > 0, cum_c / np.maximum(cum_n, 1.0), 0.0)
    mat = np.column_stack(
        [
            is_20_22 * bld_ever,
            is_20_22 * bld_ever * (1.0 - row_has),
            is_20_22 * bld_rate,
        ]
    )
    names = [
        "ad:concess_2020_22_bld",
        "ad:concess_2020_22_missing",
        "ad:concess_2020_22_rate",
    ]
    return mat, names


def rentstab_dhcr_features(
    frame: pd.DataFrame, rentstab_path: Path = RENTSTAB_PARQUET
) -> tuple[np.ndarray, list[str]]:
    """Join DHCR rent-stabilized BBL counts strictly as-of `year <= ad_year - 1` + regime
    path-decoupling indicators (2020-2021 dip, 2022+ boom)."""
    rs = pd.read_parquet(rentstab_path, columns=["bbl", "year", "units"])
    rs = rs.dropna(subset=["bbl", "year"]).copy()
    rs["bbl"] = rs["bbl"].astype("int64")
    rs["year"] = rs["year"].astype("int64")
    rs["units"] = rs["units"].fillna(0.0).astype(float)
    rs = rs.sort_values("year", kind="stable")

    bbl = _building_bbl(frame["building"])
    ad_yr = pd.to_datetime(frame["price_at"], utc=True).dt.year.to_numpy(np.int64)
    q = pd.DataFrame(
        {
            "row": np.arange(len(frame)),
            "bbl": bbl.fillna(-1).astype("int64").to_numpy(),
            "year": ad_yr - 1,
        }
    )
    got = (
        pd.merge_asof(
            q.sort_values("year", kind="stable"),
            rs,
            on="year",
            by="bbl",
            direction="backward",
        )
        .set_index("row")
        .reindex(q["row"])
    )
    dhcr_units = got["units"].fillna(0.0).to_numpy(float)
    dhcr_flag = (dhcr_units > 0.0).astype(float)
    text_stab = (
        frame["rent_stabilized"].eq(True).to_numpy(float)
        if "rent_stabilized" in frame
        else np.zeros(len(frame), float)
    )
    any_stab = np.maximum(dhcr_flag, text_stab)
    is_20_21 = ((ad_yr >= 2020) & (ad_yr <= 2021)).astype(float)
    is_22_on = (ad_yr >= 2022).astype(float)
    mat = np.column_stack(
        [
            dhcr_flag,
            np.log1p(np.maximum(dhcr_units, 0.0)) / 4.0,
            any_stab * is_20_21,
            any_stab * is_22_on,
        ]
    )
    names = [
        "bld:dhcr_stab",
        "bld:dhcr_log_stab",
        "stab:x_2020_21",
        "stab:x_2022_on",
    ]
    return mat, names


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    held=None,
    variant: tuple[str, ...] | str | None = None,
    **kw,
) -> Design:
    """Build `l2bt` plus the selected leak-free ablation/screening variant tokens."""
    tokens = (
        parse_variant(variant)
        if isinstance(variant, str)
        else (tuple(variant) if variant is not None else ACTIVE_VARIANT)
    )
    tok = set(tokens)
    drift_building_phase_unitkn_level_bedtext.check(frame)
    held = building_zones_floor_asof.held_out(frame, held)
    train = ~np.asarray(held, bool)

    # 1. Base L2 design (with optional same_bed_first)
    d = drift_building_phase_unitkn_level.design(
        frame, start, held=held, same_bed_first=("sbf" in tok), **kw
    )
    base_phase = d.phase.copy()

    # 2. Bedtext baseline (or bedunit upgrade)
    if "bedunit" in tok:
        d = drift_building_phase_unitkn_level_bedunit.with_flag(d, frame, held)
    else:
        d = drift_building_phase_unitkn_level_bedtext.with_flag(d, frame, held)

    # 3. Mean upgrades
    if "layrng" in tok:
        d = drift_building_bedtext_layout.with_layout(d, frame, held)
        d = drift_building_bedtext_layout_range.with_range(d, frame, held)

    mark_tokens = tok & MARK_TOKENS.keys()
    if "marks" in tok:
        mark_tokens.update(MARK_TOKENS)
    elif "marks_no_thin" in tok:
        mark_tokens.update(MARK_TOKENS.keys() - {"mark_thin"})
    marks = {mark for token in mark_tokens for mark in MARK_TOKENS[token]}

    if "size" in tok or "mark:large_01br" in marks:
        l01 = drift_building_phase_unitkn_unified.large_01br_flag(d, frame)
    if "size" in tok:
        imp = _col(d, "unit:size_imputed")
        lsr = _col(d, "unit:log_size_rel")
        d = append(
            d,
            list(drift_building_phase_unitkn_unified.SIZE_COLUMNS),
            np.column_stack([imp * lsr, l01]),
        )

    covid_vol_mat = None
    if "covid_mean" in tok or "covid_vol" in tok:
        c_mean, c_names, covid_vol_mat = covid_features(frame, d)
        if "covid_mean" in tok:
            d = append(d, c_names, c_mean)

    if "concess_gap" in tok:
        cg_mat, cg_names = concession_gap_features(frame, train)
        d = append(d, cg_names, cg_mat)

    if "stab_dhcr" in tok:
        st_mat, st_names = rentstab_dhcr_features(frame)
        d = append(d, st_names, st_mat)

    # Compute floor_1 and PLUTO building flags BEFORE floor_poly / ad_core pruning!
    floor1_vec = (
        drift_building_phase_unitkn_unified.floor_1_flag(d)
        if ("floor1_mean" in tok or "mark:floor_1" in marks)
        else None
    )
    if "floor1_mean" in tok:
        assert floor1_vec is not None
        d = append(d, ["unit:floor_1"], floor1_vec[:, None])

    coop_vec = small_lot_vec = None
    if "mark_tenure" in tok or "mark_townhouse" in tok:
        coop_vec, small_lot_vec = pluto_building_flags(frame["building"])
        if "mark_tenure" in tok:
            d = append(d, ["bld:coop"], coop_vec[:, None])
        if "mark_townhouse" in tok:
            d = append(d, ["bld:small_lot_le4"], small_lot_vec[:, None])

    attr_chg_mat, attr_chg_names = (
        attr_change_marks(frame, d, train) if "attr_changes" in tok else (None, [])
    )

    # 4. Additive noise-scale upgrades (only when any scale token is active)
    seg_active = [t for t in SEG_TOKENS if t in tok]
    if len(seg_active) > 1:
        raise ValueError(f"at most one segment token allowed, got {seg_active}")
    sv_active = [t for t in SV_TOKENS if t in tok]
    if len(sv_active) > 1:
        raise ValueError(f"at most one sv_gp resolution token allowed, got {sv_active}")
    vel_active = [t for t in VEL_TOKENS if t in tok]
    if len(vel_active) > 1:
        raise ValueError(
            f"at most one vel_gp resolution token allowed, got {vel_active}"
        )
    spatial_active = [t for t in SPATIAL_TOKENS if t in tok]
    if len(spatial_active) > 1:
        raise ValueError(f"at most one spatial token allowed, got {spatial_active}")
    bld_step_active = [t for t in BLD_STEP_TOKENS if t in tok]
    if len(bld_step_active) > 1:
        raise ValueError(
            f"at most one building step token allowed, got {bld_step_active}"
        )

    scale_tokens = tok & {
        "y1",
        "y1_pre2024",
        "covid_vol",
        *SV_TOKENS,
        *VEL_TOKENS,
        "income_scale",
        "u4_bed",
        "phase_compact",
        "mark_changed_bed",
        "mark_floor_unk",
        "mark_tenure",
        "u1_size_scale",
        "attr_changes",
        "mark_sparse_photos",
        "mark_townhouse",
    }
    global _ACTIVE_SCALE_FACTORS
    _ACTIVE_SCALE_FACTORS = ()
    if scale_tokens or marks:
        ph_skip = {"22-25"} if "phase_compact" in tok else set()
        ph_keep = [(j, p) for j, p in enumerate(PHASES[1:], 1) if p not in ph_skip]
        ph_names = [f"phase:{p}" for _, p in ph_keep]
        ph_mat = (
            base_phase[:, None] == np.array([j for j, _ in ph_keep])[None, :]
        ).astype(float)
        factor_names = list(ph_names)
        mats = [ph_mat]

        if tok & {"y1", "y1_pre2024"}:
            year = drift_building_phase_year
            selected = [
                (j, y)
                for j, y in enumerate(year.YEARS[1:], 1)
                if "y1_pre2024" not in tok or y < year.REFERENCE_YEAR
            ]
            yr_idx = year.year_index(frame)
            factor_names.extend(f"yr:{y}" for _, y in selected)
            mats.append(yr_idx[:, None] == [j for j, _ in selected])

        mark_cols = {}
        if "mark:changed_counts" in marks:
            if "layrng" in tok:
                cols = drift_building_bedtext_layout_range.COLUMNS
                changed = np.logical_or.reduce([_col(d, c) > 0.5 for c in cols])
            else:
                changed = drift_building_bedtext_layout_range.marks(frame, train).any(
                    axis=1
                )
            mark_cols["mark:changed_counts"] = changed
        if "mark:baths_2" in marks:
            fb = frame.full_baths.to_numpy(float)
            mark_cols["mark:baths_2"] = fb == 2
            mark_cols["mark:baths_3p"] = fb >= 3
        if "mark:floor_1" in marks:
            assert floor1_vec is not None
            mark_cols["mark:floor_1"] = floor1_vec
        if "mark:large_01br" in marks:
            mark_cols["mark:large_01br"] = l01
        if "mark:thin_first_ad" in marks:
            prior_bb = drift_building_phase_unitkn_unified.prior_bld_bed_count(
                frame, train
            )
            mark_cols["mark:thin_first_ad"] = (base_phase == PHASES.index("none")) & (
                prior_bb < drift_building_phase_unitkn_unified.THIN_BLD_BED_MAX
            )
        if mark_cols:
            factor_names.extend(mark_cols)
            mats.append(np.column_stack(list(mark_cols.values())))

        if "covid_vol" in tok:
            assert covid_vol_mat is not None
            factor_names.extend(["mark:covid_surge", "mark:covid_elevated"])
            mats.append(covid_vol_mat)

        if sv_active:
            sv_tok = sv_active[0]
            if sv_tok == "sv_gp":
                sv_mat, sv_names = sv_gp_features(frame)
            elif sv_tok == "sv_gp_mo":
                sv_mat, sv_names = sv_gp_features(
                    frame, train=train, resolution="month"
                )
            elif sv_tok == "sv_gp_mo16":
                sv_mat, sv_names = sv_gp_features(
                    frame, train=train, resolution="month", max_modes=SV_MO16_MODES
                )
            elif sv_tok == "sv_gp_mo12":
                sv_mat, sv_names = sv_gp_features(
                    frame, train=train, resolution="month", max_modes=SV_MO12_MODES
                )
            elif sv_tok == "sv_gp_wk":
                sv_mat, sv_names = sv_gp_features(frame, train=train, resolution="week")
            else:  # sv_gp_wk05
                sv_mat, sv_names = sv_gp_features(
                    frame, train=train, resolution="week", ls=SV_WK05_LS
                )
            factor_names.extend(sv_names)
            mats.append(sv_mat)

        if vel_active:
            vel_mat, vel_names = vel_gp_features(
                frame, train, weekly=(vel_active[0] == "vel_gp_wk")
            )
            factor_names.extend(vel_names)
            mats.append(vel_mat)

        if "income_scale" in tok:
            inc = (
                frame["income_restricted"].eq(True).to_numpy(float)
                if "income_restricted" in frame
                else np.zeros(len(frame), float)
            )
            factor_names.append("mark:income_restricted")
            mats.append(inc[:, None])

        if "u4_bed" in tok:
            none_idx = PHASES.index("none")
            bd = frame["bedrooms"].fillna(-1).to_numpy(float)
            new_b2 = ((base_phase == none_idx) & (bd == 2)).astype(float)
            new_b3p = ((base_phase == none_idx) & (bd >= 3)).astype(float)
            factor_names.extend(["mark:new_bed2", "mark:new_bed3p"])
            mats.append(np.column_stack([new_b2, new_b3p]))

        if "mark_changed_bed" in tok:
            if "layrng" in tok:
                chg_bed = (
                    (_col(d, "ad:beds_up_prev") > 0.5)
                    | (_col(d, "ad:beds_down_prev") > 0.5)
                ).astype(float)
            else:
                lay = drift_building_bedtext_layout.marks(frame, train)
                chg_bed = ((lay[:, 0] > 0.5) | (lay[:, 1] > 0.5)).astype(float)
            factor_names.append("mark:changed_bed")
            mats.append(chg_bed[:, None])

        if "mark_floor_unk" in tok:
            f_unk = (
                (_col(d, "unit:elev_floor_unknown") > 0.5)
                | (_col(d, "unit:walkup_floor_unknown") > 0.5)
            ).astype(float)
            factor_names.append("mark:floor_unknown")
            mats.append(f_unk[:, None])

        if "mark_tenure" in tok:
            assert coop_vec is not None
            condo_vec = (_col(d, "bld:condo") > 0.5).astype(float)
            factor_names.extend(["mark:condo", "mark:coop"])
            mats.append(np.column_stack([condo_vec, coop_vec]))

        if "u1_size_scale" in tok:
            u1_vec = u1_size_scale_feature(d, frame)
            factor_names.append("u1:log_size_gt1k")
            mats.append(u1_vec[:, None])

        if "attr_changes" in tok:
            assert attr_chg_mat is not None
            factor_names.extend(attr_chg_names)
            mats.append(attr_chg_mat)

        if "mark_sparse_photos" in tok:
            sparse_ph = (_col(d, "ad:log1p_photos") <= np.log1p(1.0) + 1e-6).astype(
                float
            )
            factor_names.append("mark:sparse_photos")
            mats.append(sparse_ph[:, None])

        if "mark_townhouse" in tok:
            assert small_lot_vec is not None
            factor_names.append("mark:small_lot_le4")
            mats.append(small_lot_vec[:, None])

        full_mat = np.hstack(mats)
        if sv_active or vel_active or "u1_size_scale" in tok:
            cell_idx, cell_names, pmap, kept_fnames = compact_continuous_phase_map(
                factor_names, full_mat, train
            )
        else:
            cell_idx, cell_names, pmap, kept_fnames = (
                drift_building_phase_unitkn_unified.compact_phase_map(
                    factor_names, full_mat, train
                )
            )
        _ACTIVE_SCALE_FACTORS = tuple(kept_fnames)
        d = dataclasses.replace(d, phase=cell_idx, phases=cell_names, phase_map=pmap)

    # 5. Model-simplification & pruning transforms (applied AFTER `mark:floor_1` / `size` reads!)
    if "floor_poly" in tok:
        d = apply_floor_poly(d)

    drop_cols: set[str] = set()
    if "no_umean" in tok:
        drop_cols.update(n for n in d.names if n.startswith("umean:"))
    elif "umean_core" in tok:
        drop_cols.update(
            n for n in d.names if n.startswith("umean:") and n not in UMEAN_CORE_COLS
        )
    if "no_ad_ks" in tok:
        drop_cols.update(
            n
            for n in d.names
            if n.startswith("ad:") and not n.startswith(AD_VARIANT_PREFIXES)
        )
    elif "ad_core" in tok:
        drop_cols.update(
            n
            for n in d.names
            if n.startswith("ad:")
            and not n.startswith(AD_VARIANT_PREFIXES)
            and n not in AD_CORE_COLS
        )
    if "no_bld_ks" in tok:
        drop_cols.update(
            n
            for n in d.names
            if n.startswith("bld:") and n not in {"bld:coop", "bld:small_lot_le4"}
        )
    elif "bld_core" in tok:
        drop_cols.update(
            n
            for n in d.names
            if n.startswith("bld:")
            and n not in BLD_CORE_COLS
            and n not in {"bld:coop", "bld:small_lot_le4"}
        )
    if "no_phase_mean" in tok:
        drop_cols.update(n for n in d.names if n.startswith("phase:"))
    elif "phase_compact" in tok:
        drop_cols.update({"phase:22-25", "phase:none"})
    if "no_season2" in tok:
        drop_cols.update(SEASON2_DROP_COLS)
    if drop_cols:
        d = drift.drop_columns(d, drop_cols)

    if spatial_active:
        per_zone = 40 if spatial_active[0] == "spatial_k80" else 20
        d = apply_spatial_trunc(d, per_zone=per_zone)

    # 6. Segment paths (full GP, additive GP, semi-annual additive GP, or low-rank)
    if "seg" in tok:
        d = drift_building_phase_unitkn_unified_seg.identifiable_segment_paths(d)
    elif "seg_add" in tok:
        d = additive_segment_paths(d, stride=1)
    elif "seg_add_semi" in tok:
        d = additive_segment_paths(d, stride=2)
    elif "seg_add_lr16" in tok:
        d = lowrank_segment_paths(d, additive=True, max_modes=16)
    elif "seg_add_lr12" in tok:
        d = lowrank_segment_paths(d, additive=True, max_modes=12)
    elif "seg_lr16" in tok:
        d = lowrank_segment_paths(d, additive=False, max_modes=16)
    return d


def gp_spec(names: list[str]) -> list[dict]:
    """Active floor GPs (if present) plus active segment GPs (if `seg:*` present)."""
    floor_gps = building_zones_floor.gp_spec(names)
    segs = [
        spec
        | {
            "kernel": drift_building_phase_unitkn_unified_seg.SEG_KERNEL,
            "nugget": drift_building_phase_unitkn_unified_seg.SEG_NUGGET,
        }
        for spec in drift_building_phase_segment.segment_spec(names)
    ]
    return floor_gps + segs


def _ablate_gp_extras(arrs: dict, names: list[str]) -> dict:
    """Named GP amplitude & lengthscale draws matching `gp_spec(names)`."""
    specs = gp_spec(names)
    if not specs or "gp_amp" not in arrs:
        return {}
    out = {}
    for k, spec in enumerate(specs):
        for q in ("gp_amp", "gp_ls"):
            out[f"{q}[{spec['name']}]"] = np.asarray(arrs[q])[..., k]
    return out


def diagnostics(trace: dict, names: list[str]) -> dict:
    """Convergence diagnostics adapting to active floor/segment GPs (including zero GPs)."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = drift.diagnostics(trace, names)
    extras = _ablate_gp_extras(trace, names)
    if not extras:
        return out
    rows = out["per_quantity"]
    for n, x in extras.items():
        rows[n] = {"rhat": split_rhat(x), "ess": ess(x)}
    worst = max(rows, key=lambda n: rows[n]["rhat"])
    least = min(rows, key=lambda n: rows[n]["ess"])
    return out | {
        "max_rhat": rows[worst]["rhat"],
        "max_rhat_name": worst,
        "min_ess": rows[least]["ess"],
        "min_ess_name": least,
        "passes": rows[worst]["rhat"] <= RHAT_GATE and rows[least]["ess"] > ESS_GATE,
    }


def summarize(kept: dict, names: list[str]) -> dict:
    """Summarize the noise factors and any active floor/segment GP scales."""
    out = drift.summarize(kept, names)
    extras = _ablate_gp_extras(kept, names)
    if extras:
        out["segment_gp"] = {n: two_zone._q(x) for n, x in extras.items()}
    return out


def _active_groups(d: Design, tok: set[str]) -> list[dict] | None:
    if "no_bld_ar" in tok:
        return None
    out = drift.groups_of(d, GROUPS)
    for step_tok, per_yr in BLD_STEP_TOKENS.items():
        if step_tok in tok:
            for g in out:
                if g["name"] == "building":
                    g["per_year"] = per_yr
    return out


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """Run the L2-unitkn sweep with active simplification tokens."""
    tok = set(ACTIVE_VARIANT)
    if "slow_trim" in tok and settings.slow_within == 0.0:
        settings = dataclasses.replace(settings, slow_within=0.001)
    return drift.run(
        d,
        priors,
        settings,
        log,
        checkpoint,
        gp=gp_spec(d.names),
        groups=_active_groups(d, tok),
        unit_t=True,
        unit_dof_fixed=UNIT_DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=ROW_DOF,
        phase_collapsed=d.phase_map is not None and d.phase_map.shape[1] > 0,
        scalar_sigma=("scalar_sigma" in tok),
        walk_stride=2 if "biweekly_walk" in tok else 1,
        scale_passes=2 if "scale_2x" in tok else 1,
        scales_no_phase=("fast_scales" in tok),
        scales_phase_k=6 if "fast_scales_p6" in tok else None,
    )


def run_record(d: Design) -> dict:
    rec = drift_building_phase_unitkn_level.run_record(d)
    rec["ablate_variant"] = list(ACTIVE_VARIANT)
    grps = _active_groups(d, set(ACTIVE_VARIANT))
    if grps is not None and "local" in rec:
        for g in grps:
            if g["name"] in rec["local"]:
                rec["local"][g["name"]]["steps_per_year"] = g["per_year"]
    if d.phase_map is not None:
        pmap = np.asarray(d.phase_map, float)
        counts = np.bincount(d.phase, minlength=len(d.phases))
        is_binary = bool(np.all((pmap == 0.0) | (pmap == 1.0)))
        if is_binary:
            fnames = drift_building_phase_unitkn_unified.free_factor_names(d)
            f_rows = counts @ pmap
        else:
            fnames = (
                list(_ACTIVE_SCALE_FACTORS)
                if len(_ACTIVE_SCALE_FACTORS) == pmap.shape[1]
                else [f"factor_{j}" for j in range(pmap.shape[1])]
            )
            f_rows = counts @ (np.abs(pmap) > 1e-9).astype(float)
        rec["phase"] = {
            "free_factors": fnames,
            "n_free_factors": len(fnames),
            "n_observed_cells": len(d.phases),
            "binary": is_binary,
            "factor_rows": {n: int(round(c)) for n, c in zip(fnames, f_rows)},
        }
    return rec


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-ablate --variant ...`."""
    global ACTIVE_VARIANT
    tokens, rest = _extract_variant(list(argv))
    ACTIVE_VARIANT = tokens
    drift.main_run(
        rest, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
