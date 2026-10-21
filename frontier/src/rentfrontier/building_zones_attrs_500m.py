"""Building zones with attributes (`rentfrontier.building_zones_attrs`), with every zone's
surface at a 500 m length-scale in place of 1 km.

At half the length-scale the box of each zone holds about twice the waves along each side,
so the global block of the Gibbs sweep holds about four times the wave coefficients.

    python -m rentfrontier.run --model building-zones-attrs-500m --split latest --name NAME
"""

from __future__ import annotations

import functools
import sys

from . import b0
from .building_zones_attrs import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    BLD_SD_PRIOR,
    COLUMNS,
    HEIGHT_REF,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    run,
    run_record,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)
from .building_zones_attrs import design as _design

NAME = "building-zones-attrs-500m"
LENGTHSCALE = 0.5  # km
design = functools.partial(_design, lengthscale=LENGTHSCALE)


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-attrs-500m`: fit on the split's training rows
    and save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
