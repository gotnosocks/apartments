"""Unified base-refit drift model (`rentfrontier.drift_building_phase_unitkn_unified`)
plus quarterly Gaussian-process market-segment paths (`rentfrontier.drift_building_phase_segment`)
for each of the 8 `(zone, bedroom_group)` segments.

Captures the cross-fitted `bed_grp x era` (+212 all years / +122 2022+) and
`outer_boro x era` (+147 all years / +47 2022+) time-varying shifts alongside all
unified mean and noise-scale upgrades.

    python -m rentfrontier.run --model drift-building-phase-unitkn-unified-seg --split latest --name NAME
"""

from __future__ import annotations

import sys

import pandas as pd

from . import (
    drift,
    drift_building_phase_segment,
    drift_building_phase_unitkn_segment,
    drift_building_phase_unitkn_unified,
)
from .drift_building_phase_segment import (  # noqa: F401
    BEDS,
    REFERENCE,
    SEG_AMP,
    SEG_LS,
    diagnostics,
    gp_spec,
    segment_index,
    segment_names,
    segment_paths,
    segment_spec,
    summarize,
)
from .drift_building_phase_unitkn_unified import (  # noqa: F401
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
    site_rows,
    site_zone,
    split_index,
    subset,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-unitkn-unified-seg"


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """Unified L2-unitkn design of `frame` with quarterly `(zone, bed)` segment paths."""
    d = drift_building_phase_unitkn_unified.design(frame, start, held=held, **kw)
    return segment_paths(d)


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """L1TKN sweep with the segments' GP processes beside the floor curves'."""
    return drift_building_phase_unitkn_segment.sample(
        d, priors, settings, log, checkpoint, gp_spec(d.names)
    )


def run_record(d: Design) -> dict:
    """Unified record plus segment path provenance."""
    return drift_building_phase_unitkn_unified.run_record(d) | {
        "segments": drift_building_phase_segment.run_record(d)["segments"]
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-unified-seg`."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
