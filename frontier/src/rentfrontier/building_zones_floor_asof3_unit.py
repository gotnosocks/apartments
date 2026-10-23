"""Building zones with the unit's floor on as-of features read from the build after #1242, with
a random effect for each unit.

The model and its sampler come from `rentfrontier.building_zones_floor_asof2_unit`, which adds
a Normal(0, su^2) effect for each (building, unit_id) with a training row to the as-of floor
model and samples it with its own blocked Gibbs sweep. That module builds its design from
`building_zones_floor_asof2`. Here I build it from `building_zones_floor_asof3` instead, so the
ads come from ROWS of that module (build b3ddebf19af1dc1e), and I number the units on top of
that design as the asof2 version does. The run record is the asof3 record with the unit
effects' settings added.

    python -m rentfrontier.run --model building-zones-floor-asof3-unit --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import pandas as pd

from . import b0, building_zones_floor_asof, building_zones_floor_asof3
from .building_zones_floor_asof2_unit import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    KEPT,
    MIN_UNIT_ROWS,
    PROGRESS,
    TRACED,
    UNIT_SD_PRIOR,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    make_sampler,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    unit_index,
    unit_offset,
    wave_matrix,
)

NAME = "building-zones-floor-asof3-unit"


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The as-of floor design of `frame` on the build after #1242
    (`building_zones_floor_asof3`), with each row's unit number."""
    held = building_zones_floor_asof.held_out(frame, held)
    d = building_zones_floor_asof3.design(frame, start, held=held, **kw)
    unit, units = unit_index(frame, held)
    return Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(d)},
        unit=unit,
        units=units,
    )


def run_record(d: Design) -> dict:
    """The asof3 record, with the unit effects' settings."""
    return building_zones_floor_asof3.run_record(d) | {
        "unit_effect": {
            "key": "building and unit_id",
            "min_training_rows": MIN_UNIT_ROWS,
            "units": int(d.units),
            "sd_prior": f"HalfNormal({UNIT_SD_PRIOR})",
            "kept": "running mean and variance per chain (unit_mean, unit_var)",
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof3-unit`: fit on the split's
    training rows and save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    building_zones_floor_asof.SPLIT = parser.parse_known_args(argv)[0].split
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
