"""Building zones with the unit's floor on as-of features, with a wider prior on the zone map's
amplitude.

The design and sampler are those of `rentfrontier.building_zones_floor_asof`. I change only the
prior on each zone's map amplitude `amp`, from the family's HalfNormal(0.3)
(`two_zone.Priors.amp`) to HalfNormal(1.0). In the as-of floor fit the Manhattan amplitude has
a posterior median of 0.92, about 3 prior standard deviations out, so I refit with the wider
prior to check whether the old one held the amplitude down
(docs/notes/conference-followups-2026-10-22.md, section e).

    python -m rentfrontier.run --model building-zones-floor-asof-amp1 --split latest --name NAME
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from . import b0, building_zones_floor_asof
from .building_zones_floor_asof import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Settings,
    design,
    diagnostics,
    gp_spec,
    run,
    run_record,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)

NAME = "building-zones-floor-asof-amp1"


@dataclass(frozen=True)
class Priors(building_zones_floor_asof.Priors):
    amp: float = 1.0  # HalfNormal scale of each zone's amplitude


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof-amp1`: fit on the split's training
    rows and save the run."""
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
