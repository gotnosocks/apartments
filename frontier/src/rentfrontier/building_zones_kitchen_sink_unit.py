"""The kitchen sink (`rentfrontier.building_zones_kitchen_sink`), with a random effect for each
unit as in fit 4 (`rentfrontier.building_zones_floor_asof3_unitmean`).

I build the kitchen sink's design, past-only unit means included, and number its units with
`building_zones_floor_asof2_unit.unit_index`, as the asof3 unit models do. The sampler is that
module's blocked Gibbs sweep, which adds a Normal(0, su^2) effect for each (building, unit_id)
with a training row. Its `run` reads the floor curves' Gaussian process priors from
`building_zones_floor_asof2.gp_spec`, which caps the elevator curve at floor 47. The kitchen
sink carries fit 8's curve to floor 64, so my `run` hands that sweep
`building_zones_floor_asof2_cap64.gp_spec` for the length of the call.

    python -m rentfrontier.run --model building-zones-kitchen-sink-unit --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import pandas as pd

from . import (
    b0,
    building_zones_floor_asof,
    building_zones_floor_asof2_cap64,
    building_zones_kitchen_sink,
)
from . import building_zones_floor_asof2_unit as unit2
from .building_zones_floor_asof2_unit import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    MIN_UNIT_ROWS,
    UNIT_SD_PRIOR,
    Design,
    diagnostics,
    make_sampler,
    subset,
    summarize,
    unit_index,
    unit_offset,
)
from .building_zones_kitchen_sink import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Priors,
    Settings,
    gp_spec,
    site_rows,
    site_zone,
    split_index,
    wave_matrix,
)

NAME = "building-zones-kitchen-sink-unit"


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The kitchen sink's design of `frame`, with each row's unit number."""
    held = building_zones_floor_asof.held_out(frame, held)
    d = building_zones_kitchen_sink.design(frame, start, held=held, **kw)
    unit, units = unit_index(frame, held)
    return Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(d)},
        unit=unit,
        units=units,
    )


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`building_zones_floor_asof2_unit.run`, with the floor curves' priors to floor 64."""
    saved = unit2.gp_spec
    unit2.gp_spec = building_zones_floor_asof2_cap64.gp_spec
    try:
        return unit2.run(d, priors, settings, log, checkpoint)
    finally:
        unit2.gp_spec = saved


def run_record(d: Design) -> dict:
    """The kitchen sink's record, with the unit effects' settings."""
    return building_zones_kitchen_sink.run_record(d) | {
        "unit_effect": {
            "key": "building and unit_id",
            "min_training_rows": MIN_UNIT_ROWS,
            "units": int(d.units),
            "sd_prior": f"HalfNormal({UNIT_SD_PRIOR})",
            "kept": "running mean and variance per chain (unit_mean, unit_var)",
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-kitchen-sink-unit`: fit on the split's
    training rows and save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    parser.add_argument("--joint-amp", action="store_true", default=None)
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
