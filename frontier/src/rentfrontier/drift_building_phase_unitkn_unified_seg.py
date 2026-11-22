"""Unified base-refit drift model (`rentfrontier.drift_building_phase_unitkn_unified`)
plus full-rank identifiable quarterly Gaussian-process market-segment paths
(`rentfrontier.drift_building_phase_segment`) across `(zone, bedroom_group)` segments.

Identifiability fixes over the unconstrained 8-segment pilot (`u1s-lat-p3`, which gained
+4,916 elpd over l2bt all years / +3,098 on 2022+, but had R-hat 7.81 from the shared
per-quarter constant shift across all 8 segments and R-hat 2.8 on `level:outer:*` from
the 2024q1 nugget):
1. Drops the reference segment (`manhattan:1br`, or the first segment present when absent)
   so the remaining 7 segment paths have exact full column rank at every quarter knot.
2. Drops the reference quarter knot (`2024q1`) from every segment so every path is
   identically 0 on 2024-01-01 (zero nugget trade-off against `level:*` and `bed>=*`).
3. Enables `phase_collapsed=True` so the 24 additive `phase_map` log-scale factors are
   also updated with `lam` integrated out in the noise step.

    python -m rentfrontier.run --model drift-building-phase-unitkn-unified-seg --split latest --name NAME
"""

from __future__ import annotations

import sys

import pandas as pd

from . import (
    drift,
    drift_building_phase_segment,
    drift_building_phase_unitkn_unified,
)
from .drift_building_phase_segment import (  # noqa: F401
    BEDS,
    REFERENCE,
    SEG_AMP,
    SEG_LS,
    diagnostics,
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
REF_SEGMENT = "manhattan:1br"
REF_QUARTER = "2024q1"
SEG_KERNEL = "matern32"
SEG_NUGGET = 1e-4


def gp_spec(names) -> list[dict]:
    """Floor-curve GPs (RBF) plus segment-path GPs using a Matérn-3/2 kernel with
    `SEG_NUGGET = 1e-4` so quarterly regime shifts never induce an RBF-nugget double well."""
    segs = [
        spec | {"kernel": SEG_KERNEL, "nugget": SEG_NUGGET}
        for spec in segment_spec(names)
    ]
    return drift_building_phase_unitkn_unified.gp_spec(names) + segs


def identifiable_segment_paths(d: Design) -> Design:
    """`segment_paths(d)` with the reference segment and reference quarter knot dropped so
    every segment path has exact full column rank and is identically 0 at `REF_QUARTER`."""
    d = segment_paths(d)
    seg_cols = [n for n in d.names if n.startswith("seg:")]
    present_segs = sorted({n.rsplit(":", 1)[0].split("seg:", 1)[1] for n in seg_cols})
    if not present_segs:
        return d
    ref_seg = REF_SEGMENT if REF_SEGMENT in present_segs else present_segs[0]
    drop = {
        n
        for n in seg_cols
        if n.startswith(f"seg:{ref_seg}:") or n.endswith(f":{REF_QUARTER}")
    }
    return drift.drop_columns(d, drop)


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """Unified L2-unitkn design of `frame` with identifiable quarterly segment paths."""
    d = drift_building_phase_unitkn_unified.design(frame, start, held=held, **kw)
    return identifiable_segment_paths(d)


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """L1TKN sweep with collapsed `phase_map` noise updates and segment GP processes."""
    return drift.run(
        d,
        priors,
        settings,
        log,
        checkpoint,
        gp=gp_spec(d.names),
        groups=drift.groups_of(d, GROUPS),
        unit_t=True,
        unit_dof_fixed=UNIT_DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=ROW_DOF,
        phase_collapsed=True,
    )


def run_record(d: Design) -> dict:
    """Unified record plus identifiable segment path provenance."""
    rec = drift_building_phase_unitkn_unified.run_record(d)
    rec["phase"]["phase_collapsed"] = True
    rec["segments"] = drift_building_phase_segment.run_record(d)["segments"] | {
        "reference_segment": REF_SEGMENT,
        "reference_quarter_dropped": REF_QUARTER,
        "kernel": SEG_KERNEL,
        "nugget": SEG_NUGGET,
    }
    return rec


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-unified-seg`."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
