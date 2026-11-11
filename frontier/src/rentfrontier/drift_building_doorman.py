"""The building model (`rentfrontier.drift_building`) with a Manhattan doorman premium.

The building model gives each doorman class one coefficient for the whole city. Its building
levels still carry a doorman premium in Manhattan: full-doorman buildings there sit about 8%
above their neighbourhoods, and outer-borough ones about 0
(docs/notes/drift-building-doorman-2026-11-11.md). So this design adds a Manhattan copy of
each doorman column:

    bld:doorman_full_manhattan = bld:doorman_full * (building in Manhattan)

and likewise for the part-time and virtual classes. The citywide column's coefficient then
reads as the outer boroughs' premium, and the copy's as Manhattan's difference from it. With
its prior centred on zero, the copy stays near zero unless the rows pull it away.

    python -m rentfrontier.run --model drift-building-doorman --split latest --name NAME
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import building_zones_kitchen_sink, drift, drift_building
from .drift_building import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    make_sampler,
    run,
    run_record,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
    years,
)

NAME = "drift-building-doorman"
DOORMAN = ("bld:doorman_full", "bld:doorman_part", "bld:doorman_virtual")


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The building model's design of `frame`, with a Manhattan copy of each doorman column."""
    return manhattan_doorman(drift_building.design(frame, start, held=held, **kw))


def manhattan_doorman(d: Design) -> Design:
    """`d` with a Manhattan copy of each of its doorman columns."""
    # Zones are numbered by their place in `d.surfaces`, so the zone is found by its name.
    zone = [s["name"] for s in d.surfaces].index("manhattan")
    manhattan = site_zone(d)[d.site] == zone
    have = [n for n in DOORMAN if n in d.names]
    if not have:
        return d
    x = np.column_stack([d.x[:, d.names.index(n)] * manhattan for n in have])
    return building_zones_kitchen_sink.append(d, [f"{n}_manhattan" for n in have], x)


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-doorman`: fit on the split's training rows
    and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
