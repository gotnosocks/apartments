"""The kitchen sink (`rentfrontier.building_zones_kitchen_sink`), with every zone's surface at
a 150 m length-scale in place of 1 km.

I build the kitchen sink's design, then rebuild each zone's wave basis at 150 m with
`building_zones_attrs.surfaces_at`. The building offsets and the columns stay as they are. At
150 m the zone boxes hold about 3,400 and 5,000 waves, against 85 and 110 at 1 km, so the
global block of the Gibbs sweep grows about forty-fold.

    python -m rentfrontier.run --model building-zones-kitchen-sink-150m --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import pandas as pd

from . import building_zones_kitchen_sink, whitened_zones
from .building_zones_attrs import surfaces_at
from .building_zones_kitchen_sink import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    BLD_SD_PRIOR,
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

NAME = "building-zones-kitchen-sink-150m"
LENGTHSCALE = 0.15  # km


def design(frame: pd.DataFrame, start=None, held=None, registry=None, **kw) -> Design:
    """The kitchen sink's design of `frame` with its surfaces rebuilt at LENGTHSCALE."""
    d = building_zones_kitchen_sink.design(frame, start, held=held, **kw)
    if registry is None:
        registry = pd.read_parquet(
            whitened_zones.REGISTRY,
            columns=["building", "bbl", "bin", "latitude", "longitude"],
        )
    return dataclasses.replace(
        d, surfaces=surfaces_at(d, frame, registry, None, LENGTHSCALE)
    )


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-kitchen-sink-150m`: fit on the split's
    training rows and save the run."""
    building_zones_kitchen_sink.main_run(argv, name=NAME, spec=sys.modules[__name__])
