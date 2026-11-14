"""L1TKN (`rentfrontier.drift_building_phase_unitkn`) with the segment model's path in time
for each bedroom group in each zone (`rentfrontier.drift_building_phase_segment`).

L1TKN gives each unit's lasting level a Student-t prior at 3 degrees of freedom and holds
the rows' nu at 2. The segment model adds to L1's design a level column for each outer
bedroom group past studios and a centered hat column for each of eight segments at each
quarter start, with a Gaussian process prior over each segment's coefficients held at 0 on
2024-01-01. This module puts the two together: the design, the processes, the convergence
table and the summary are the segment model's, and the sweep is L1TKN's with the segments'
processes beside the floor curves'.

`sample` takes the processes as an argument, so a module with another prior on the paths
can run the same sweep.

    python -m rentfrontier.run --model drift-building-phase-unitkn-segment --split latest --name NAME
"""

from __future__ import annotations

import sys

from . import drift, drift_building_phase_segment, drift_building_phase_unitkn
from .drift_building_phase_segment import (  # noqa: F401
    BEDS,
    REFERENCE,
    SEG_AMP,
    SEG_LS,
    design,
    diagnostics,
    gp_spec,
    segment_index,
    segment_names,
    segment_paths,
    segment_spec,
    summarize,
)
from .drift_building_phase_unitkn import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    EDGES,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
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

NAME = "drift-building-phase-unitkn-segment"


def sample(d: Design, priors: Priors, settings: Settings, log, checkpoint, gp):
    """`drift.run` with L1TKN's model and sweep and the processes `gp`."""
    return drift.run(
        d,
        priors,
        settings,
        log,
        checkpoint,
        gp=gp,
        groups=drift.groups_of(d, GROUPS),
        unit_t=True,
        unit_dof_fixed=UNIT_DOF,
        unit_kap_collapsed=True,
        row_dof_fixed=ROW_DOF,
    )


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """L1TKN's sweep with the segments' processes beside the floor curves'."""
    return sample(d, priors, settings, log, checkpoint, gp_spec(d.names))


def run_record(d: Design) -> dict:
    """L1TKN's record, with the segments, their quarter starts and the paths' priors from
    the segment model's."""
    return drift_building_phase_unitkn.run_record(d) | {
        "segments": drift_building_phase_segment.run_record(d)["segments"]
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-unitkn-segment`: fit on the split's
    training rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
