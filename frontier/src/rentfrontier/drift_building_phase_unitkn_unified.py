"""Unified base-refit drift model (`drift-building-phase-unitkn-unified`): L2 on the
Student-t unitkn base (`drift_building_phase_unitkn_level`) combined with the leak-free
level and noise-scale upgrades sized on `l2bt` and `range-j` (2026-11-21).

Mean upgrades (global block):
- `same_bed_first=True` as-of size fill (`sizefill.asof_size`: same-bed unit -> line ->
  other-bed unit; docs/notes/size-fills-read-2026-11-20.md);
- `bedunit` (`ad:bed_text_smaller` + `uever:ad:bed_text_smaller`;
  docs/notes/bed-text-2026-11-16.md);
- `layout-range` (8 strictly as-of bedroom/bath change and range columns from
  `drift_building_bedtext_layout` and `drift_building_bedtext_layout_range`);
- `ad:size_imp_log_size_rel` (filled-size slope: `unit:size_imputed * unit:log_size_rel`)
  and `ad:large_01br` (large 0-1 bedroom indicator from the model's own as-of size).

Additive noise-scale upgrades (`Design.phase_map`, compact observed-cell encoding):
- Lease phases (6 free factors, reference `10-13`);
- Calendar years Y1 (up to 12 free factors, reference `2024`, clipped `2014..2026`,
  automatically dropping years with zero training rows so earlier as-of backtests such
  as `asof-20251110` have no empty factors);
- Six strictly exogenous noise-scale marks:
  1. `mark:changed_counts`: coded bed or bath count outside the apartment's earlier
     training range;
  2. `mark:baths_2`: `full_baths == 2`;
  3. `mark:baths_3p`: `full_baths >= 3`;
  4. `mark:floor_1`: unit is on floor 1 (known floor with no floor>=2 column set);
  5. `mark:large_01br`: 0-1BR unit with large as-of size (>2x studio median or >1.4x 1BR
     median, matching ~1,000 sq ft on NYC data);
  6. `mark:thin_first_ad`: unit has no earlier training ad (`phase == none`) and fewer
     than 5 strictly earlier training ads in the same `(building, bedrooms_cap)`.

Every covariate reads only the row's own non-rent attributes or strictly earlier training
rows (zero target/future peeking).

    python -m rentfrontier.run --model drift-building-phase-unitkn-unified --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import math
import sys

import numpy as np
import pandas as pd

from . import (
    building_zones_floor_asof,
    drift,
    drift_building_bedtext_layout,
    drift_building_bedtext_layout_range,
    drift_building_phase,
    drift_building_phase_level,
    drift_building_phase_unitkn_level,
    drift_building_phase_unitkn_level_bedunit,
    drift_building_phase_year,
)
from .building_zones_kitchen_sink import append
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
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-unitkn-unified"
SIZE_COLUMNS = ("ad:size_imp_log_size_rel", "ad:large_01br")
SCALE_MARKS = (
    "mark:changed_counts",
    "mark:baths_2",
    "mark:baths_3p",
    "mark:floor_1",
    "mark:large_01br",
    "mark:thin_first_ad",
)
# Dimensionless thresholds on `unit:log_size_rel` matching ~1,000 sq ft for studios (~480 sf
# median) and 1-bedrooms (~700 sf median) without hardcoding NYC medians.
STUDIO_LARGE_REL = math.log(2.0)
ONEBR_LARGE_REL = math.log(1.4)
THIN_BLD_BED_MAX = 5


def _col(d: Design, name: str) -> np.ndarray:
    if name in d.names:
        return d.x[:, d.names.index(name)]
    return np.zeros(len(d.y), float)


def large_01br_flag(d: Design, frame: pd.DataFrame) -> np.ndarray:
    """1.0 on 0-1BR rows with known as-of size above STUDIO_LARGE_REL (0BR) or
    ONEBR_LARGE_REL (1BR), else 0.0."""
    lsr = _col(d, "unit:log_size_rel")
    unk = _col(d, "unit:size_unknown") > 0.5
    bd = frame.bedrooms.to_numpy(float)
    is_large = (~unk) & (
        ((bd == 0) & (lsr > STUDIO_LARGE_REL)) | ((bd == 1) & (lsr > ONEBR_LARGE_REL))
    )
    return is_large.astype(float)


def floor_1_flag(d: Design) -> np.ndarray:
    """1.0 on rows with known floor 1 (no elev_f*/walkup_f* >=2 and no floor_unknown)."""
    unk = (_col(d, "unit:elev_floor_unknown") > 0.5) | (
        _col(d, "unit:walkup_floor_unknown") > 0.5
    )
    high_idx = [
        j
        for j, n in enumerate(d.names)
        if n.startswith("unit:elev_f") or n.startswith("unit:walkup_f")
    ]
    if high_idx:
        above1 = (d.x[:, high_idx] > 0.5).any(axis=1)
    else:
        above1 = np.zeros(len(d.y), bool)
    return (~unk & ~above1).astype(float)


def prior_bld_bed_count(frame: pd.DataFrame, train: np.ndarray) -> np.ndarray:
    """For each row of `frame`, the count of training rows in the same `(building,
    bedrooms.clip(0, 4))` priced on strictly earlier days."""
    day = pd.to_datetime(frame.price_at, utc=True).dt.floor("D")
    bd = frame.bedrooms.clip(0, 4).fillna(-1).astype(int)
    key = frame.building.astype(str) + "|" + bd.astype(str)
    q = pd.DataFrame({"key": key.to_numpy(), "day": day.to_numpy()})
    q["row"] = np.arange(len(q))
    tr_mask = np.asarray(train, bool)
    tr_days = (
        q.loc[tr_mask]
        .groupby(["key", "day"], sort=False)
        .size()
        .rename("n_day")
        .reset_index()
        .sort_values("day", kind="stable")
    )
    if len(tr_days) == 0:
        return np.zeros(len(frame), dtype=np.int64)
    tr_days["cum"] = tr_days.groupby("key", sort=False)["n_day"].cumsum()
    got = pd.merge_asof(
        q.sort_values("day", kind="stable"),
        tr_days[["key", "day", "cum"]],
        on="day",
        by="key",
        allow_exact_matches=False,
    ).set_index("row")
    return got["cum"].reindex(q["row"]).fillna(0).to_numpy(np.int64)


def compact_phase_map(
    factor_names: list[str],
    matrix: np.ndarray,
    train: np.ndarray,
) -> tuple[np.ndarray, tuple[str, ...], np.ndarray, list[str]]:
    """Compress a (rows, F) binary additive factor matrix into unique observed cells.

    Drops any factor column with zero training rows so every free factor in `phase_map`
    is identified by training data. Row 0 of the returned `phase_map` is always the
    all-zeros reference cell (required by `drift.make_sampler`).
    """
    tr = np.asarray(train, bool)
    keep = [j for j in range(matrix.shape[1]) if (matrix[tr, j] > 0.5).any()]
    kept_names = [factor_names[j] for j in keep]
    M = matrix[:, keep].astype(np.int8) if keep else np.zeros((len(matrix), 0), np.int8)
    n_free = M.shape[1]
    if n_free == 0:
        return (
            np.zeros(len(matrix), dtype=np.int64),
            ("ref",),
            np.zeros((1, 0), dtype=float),
            [],
        )
    # Build unique cell rows with the all-zero reference cell guaranteed at index 0.
    zero_row = np.zeros((1, n_free), dtype=np.int8)
    stacked = np.vstack([zero_row, M])
    uniq, inv = np.unique(stacked, axis=0, return_inverse=True)
    # Ensure all-zero row sits at index 0 (np.unique sorts lexicographically, so all-zeros
    # is already index 0 whenever values are in {0, 1}).
    assert not uniq[0].any(), "reference cell must be all zeros"
    cell_idx = inv[1:].astype(np.int64)
    cell_names = tuple(
        "ref"
        if not row.any()
        else "|".join(kept_names[j] for j, v in enumerate(row) if v)
        for row in uniq
    )
    return cell_idx, cell_names, uniq.astype(float), kept_names


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """Unified L2-unitkn design of `frame`."""
    drift_building_phase_unitkn_level_bedunit.check(frame)
    held = building_zones_floor_asof.held_out(frame, held)
    train = ~np.asarray(held, bool)

    # 1. Base L2 design with same_bed_first=True as-of size fill
    d = drift_building_phase_unitkn_level.design(
        frame, start, held=held, same_bed_first=True, **kw
    )
    assert len(d.y) == len(frame)
    base_phase = d.phase.copy()

    # 2. Mean upgrades: bedunit, layout, layout-range, size_imp_slope, large_01br
    d = drift_building_phase_unitkn_level_bedunit.with_flag(d, frame, held)
    d = drift_building_bedtext_layout.with_layout(d, frame, held)
    d = drift_building_bedtext_layout_range.with_range(d, frame, held)

    imp = _col(d, "unit:size_imputed")
    lsr = _col(d, "unit:log_size_rel")
    l01 = large_01br_flag(d, frame)
    d = append(d, list(SIZE_COLUMNS), np.column_stack([imp * lsr, l01]))

    # 3. Additive noise-scale factor matrix (phase + year + 6 exogenous marks)
    yr_idx = drift_building_phase_year.year_index(frame)
    yr_names = [f"yr:{y}" for y in drift_building_phase_year.YEARS[1:]]
    ph_names = [f"phase:{p}" for p in PHASES[1:]]

    rng_cols = [_col(d, c) > 0.5 for c in drift_building_bedtext_layout_range.COLUMNS]
    changed_counts = np.logical_or.reduce(rng_cols).astype(float)
    fb = frame.full_baths.to_numpy(float)
    baths_2 = (fb == 2).astype(float)
    baths_3p = (fb >= 3).astype(float)
    fl1 = floor_1_flag(d)
    none_idx = PHASES.index("none")
    prior_bb = prior_bld_bed_count(frame, train)
    thin_first = ((base_phase == none_idx) & (prior_bb < THIN_BLD_BED_MAX)).astype(
        float
    )

    ph_mat = (base_phase[:, None] == np.arange(1, len(PHASES))[None, :]).astype(float)
    yr_mat = (
        yr_idx[:, None] == np.arange(1, len(drift_building_phase_year.YEARS))[None, :]
    ).astype(float)
    mk_mat = np.column_stack([changed_counts, baths_2, baths_3p, fl1, l01, thin_first])

    factor_names = ph_names + yr_names + list(SCALE_MARKS)
    full_mat = np.hstack([ph_mat, yr_mat, mk_mat])
    cell_idx, cell_names, pmap, kept_factors = compact_phase_map(
        factor_names, full_mat, train
    )
    d = dataclasses.replace(d, phase=cell_idx, phases=cell_names, phase_map=pmap)
    # Attach kept factor metadata via count-safe attribute? Design is a frozen dataclass;
    # run_record recomputes factor names directly from d.phase_map and d.phases.
    return d


def free_factor_names(d: Design) -> list[str]:
    """Recover the ordered names of the free factors (columns of `d.phase_map`) from
    `d.phases` and `d.phase_map`."""
    pmap = np.asarray(d.phase_map)
    n_free = pmap.shape[1]
    names = [f"factor[{j}]" for j in range(n_free)]
    # Any single-factor cell immediately names its factor; otherwise intersect cell tokens.
    sets = [None] * n_free
    for cell_name, row in zip(d.phases, pmap):
        ones = np.flatnonzero(row > 0.5)
        if len(ones) == 0:
            continue
        toks = set(cell_name.split("|"))
        if len(ones) == 1:
            names[ones[0]] = cell_name
        else:
            for j in ones:
                sets[j] = toks if sets[j] is None else (sets[j] & toks)
    for j in range(n_free):
        if names[j].startswith("factor[") and sets[j] and len(sets[j]) == 1:
            names[j] = next(iter(sets[j]))
    return names


def run_record(d: Design) -> dict:
    """Unified model provenance record."""
    rec = drift_building_phase_unitkn_level.run_record(d)
    rec["asof"] = rec.get("asof", {}) | {
        "size_same_bed_first": True,
        "size_order": "own -> same-bed unit -> line -> other-bed unit",
    }
    rec["bed_text"] = {
        "source": "the row's own bed_flex_at or bed_text_fewer (rentfrontier.b0bedtext)",
        "columns": [
            n
            for n in d.names
            if n
            in (
                drift_building_phase_unitkn_level_bedunit.COLUMN,
                drift_building_phase_unitkn_level_bedunit.EVER,
            )
        ],
    }
    rec["layout_range"] = {
        "columns": [
            n
            for n in d.names
            if n
            in (
                *drift_building_bedtext_layout.COLUMNS,
                *drift_building_bedtext_layout_range.COLUMNS,
            )
        ],
    }
    rec["size_extras"] = {
        "columns": [n for n in d.names if n in SIZE_COLUMNS],
        "rows": {n: int(d.count.get(n, 0)) for n in SIZE_COLUMNS},
    }
    pmap = np.asarray(d.phase_map)
    counts = np.bincount(d.phase, minlength=len(d.phases))
    fnames = free_factor_names(d)
    f_rows = counts @ pmap
    rec["phase"] = {
        "free_factors": fnames,
        "n_free_factors": len(fnames),
        "n_observed_cells": len(d.phases),
        "log_factor_prior": f"Normal(0, {drift.PHASE_PRIOR})",
        "factor_rows": {n: int(round(c)) for n, c in zip(fnames, f_rows)},
    }
    return rec


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-unified`."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
