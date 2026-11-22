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
- `y1`: adds calendar-year additive noise scale factors (`yr:2014..2026`).
- `marks`: adds all 6 exogenous noise-scale marks from `unified`.
- `marks_no_thin`: adds 5 exogenous noise-scale marks (excluding `mark:thin_first_ad`).
- `covid_mean`: adds 14-day-lagged NYC DOHMH borough-relative Covid hospitalizations/cases and
  Covid x property-type (Manhattan, 2+BR, doorman, private outdoor) mean interactions.
- `covid_vol`: adds 2 causal 14-day-lagged Covid volatility regime scale marks (`surge`, `elevated`).
- `concess_gap`: adds strictly as-of building concession history x 2020-2022 gap columns.
- `stab_dhcr`: joins DHCR rent-stabilized BBL counts (as-of prior year) + stabilized x regime
  (2020-2021 dip, 2022+ boom) path decoupling terms.
- `income_scale`: adds noise scale mark for `income_restricted` ads.
- `u4_bed`: adds per-bedroom new-unit (`phase == none`) noise scale marks for 2BR and 3+BR.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import (
    building_attrs,
    building_zones_floor_asof,
    building_zones_floor_asof3,
    drift,
    drift_building_bedtext_layout,
    drift_building_bedtext_layout_range,
    drift_building_phase_unitkn_level,
    drift_building_phase_unitkn_level_bedtext,
    drift_building_phase_unitkn_level_bedunit,
    drift_building_phase_unitkn_unified,
    drift_building_phase_year,
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
    diagnostics,
    gp_spec,
    make_sampler,
    months_since_previous,
    phase_index,
    phase_levels,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-unitkn-ablate"
COVID_CSV = EXTERNAL_ROOT / "covid" / "20261122-nychealth" / "data-by-day.csv"
RENTSTAB_PARQUET = EXTERNAL_ROOT / "rentstab" / "20261008-b487c8a" / "rentstab.parquet"

ALL_TOKENS = (
    "sbf",
    "bedunit",
    "layrng",
    "size",
    "y1",
    "marks",
    "marks_no_thin",
    "covid_mean",
    "covid_vol",
    "concess_gap",
    "stab_dhcr",
    "income_scale",
    "u4_bed",
)
# Active variant tuple for the current CLI run (set in `main_run`, or passed to `design`).
ACTIVE_VARIANT: tuple[str, ...] = ()

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
        else:
            out.append(argv[i])
            i += 1
    return parse_variant(val), out


def _col(d: Design, name: str) -> np.ndarray:
    return drift_building_phase_unitkn_unified._col(d, name)


def _building_bbl(buildings: pd.Series) -> pd.Series:
    reg = pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"])
    reg = reg.dropna(subset=["bbl"]).drop_duplicates("building")
    bmap = reg.set_index(reg["building"].astype(str))["bbl"].astype("int64")
    return buildings.astype(str).map(bmap)


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
    need_layrng = ("layrng" in tok) or ("marks" in tok) or ("marks_no_thin" in tok)
    if "layrng" in tok:
        d = drift_building_bedtext_layout.with_layout(d, frame, held)
        d = drift_building_bedtext_layout_range.with_range(d, frame, held)

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

    # 4. Additive noise-scale upgrades (only when any scale token is active)
    scale_tokens = tok & {
        "y1",
        "marks",
        "marks_no_thin",
        "covid_vol",
        "income_scale",
        "u4_bed",
    }
    if scale_tokens:
        ph_names = [f"phase:{p}" for p in PHASES[1:]]
        ph_mat = (base_phase[:, None] == np.arange(1, len(PHASES))[None, :]).astype(
            float
        )
        factor_names = list(ph_names)
        mats = [ph_mat]

        if "y1" in tok:
            yr_idx = drift_building_phase_year.year_index(frame)
            yr_names = [f"yr:{y}" for y in drift_building_phase_year.YEARS[1:]]
            yr_mat = (
                yr_idx[:, None]
                == np.arange(1, len(drift_building_phase_year.YEARS))[None, :]
            ).astype(float)
            factor_names.extend(yr_names)
            mats.append(yr_mat)

        if "marks" in tok or "marks_no_thin" in tok:
            # Compute changed_counts strictly from layout-range helper without adding mean cols
            # unless `layrng` was requested.
            if "layrng" in tok:
                d_rng = d
            else:
                d_rng = drift_building_bedtext_layout_range.with_range(
                    drift_building_bedtext_layout.with_layout(d, frame, held),
                    frame,
                    held,
                )
            rng_cols = [
                _col(d_rng, c) > 0.5
                for c in drift_building_bedtext_layout_range.COLUMNS
            ]
            changed_counts = np.logical_or.reduce(rng_cols).astype(float)
            fb = frame.full_baths.to_numpy(float)
            baths_2 = (fb == 2).astype(float)
            baths_3p = (fb >= 3).astype(float)
            fl1 = drift_building_phase_unitkn_unified.floor_1_flag(d)
            if "marks" in tok:
                none_idx = PHASES.index("none")
                prior_bb = drift_building_phase_unitkn_unified.prior_bld_bed_count(
                    frame, train
                )
                thin_first = (
                    (base_phase == none_idx)
                    & (prior_bb < drift_building_phase_unitkn_unified.THIN_BLD_BED_MAX)
                ).astype(float)
                factor_names.extend(drift_building_phase_unitkn_unified.SCALE_MARKS)
                mats.append(
                    np.column_stack(
                        [changed_counts, baths_2, baths_3p, fl1, l01, thin_first]
                    )
                )
            else:
                factor_names.extend(
                    drift_building_phase_unitkn_unified.SCALE_MARKS[:-1]
                )
                mats.append(
                    np.column_stack([changed_counts, baths_2, baths_3p, fl1, l01])
                )

        if "covid_vol" in tok:
            assert covid_vol_mat is not None
            factor_names.extend(["mark:covid_surge", "mark:covid_elevated"])
            mats.append(covid_vol_mat)

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

        full_mat = np.hstack(mats)
        cell_idx, cell_names, pmap, _ = (
            drift_building_phase_unitkn_unified.compact_phase_map(
                factor_names, full_mat, train
            )
        )
        d = dataclasses.replace(d, phase=cell_idx, phases=cell_names, phase_map=pmap)

    _ = need_layrng
    return d


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """Run L2-unitkn sweep, automatically enabling `phase_collapsed` when `phase_map` is set."""
    return drift.run(
        d,
        priors,
        settings,
        log,
        checkpoint,
        groups=drift.groups_of(d, GROUPS),
        unit_t=True,
        unit_dof_fixed=UNIT_DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=ROW_DOF,
        phase_collapsed=(d.phase_map is not None),
    )


def run_record(d: Design) -> dict:
    rec = drift_building_phase_unitkn_level.run_record(d)
    rec["ablate_variant"] = list(ACTIVE_VARIANT)
    if d.phase_map is not None:
        pmap = np.asarray(d.phase_map)
        counts = np.bincount(d.phase, minlength=len(d.phases))
        fnames = drift_building_phase_unitkn_unified.free_factor_names(d)
        f_rows = counts @ pmap
        rec["phase"] = {
            "free_factors": fnames,
            "n_free_factors": len(fnames),
            "n_observed_cells": len(d.phases),
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
