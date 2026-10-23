"""Building zones with the unit's floor on as-of features from the build after #1242, with the
elevator curve run to floor 64.

The model is `rentfrontier.building_zones_floor_asof2_cap64` (fit 8): the as-of floor design
with its pooled floor-47 column split into one column per elevator floor up to 64, and the
elevator floor curve's Gaussian process prior run over floors 2 to 64. That module reads each
ad's fields from build b495f6dd53222649. Here I pass it the ads from
`building_zones_floor_asof3.ROWS`, build b3ddebf19af1dc1e, and record that build in the run.

    python -m rentfrontier.run --model building-zones-floor-asof3-cap64 --split latest --name NAME
"""

from __future__ import annotations

import sys

import pandas as pd

from . import (
    b0,
    building_zones_floor_asof,
    building_zones_floor_asof2_cap64,
    building_zones_floor_asof3,
)
from .building_zones_floor_asof2_cap64 import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    ELEV_CAP,
    GROUPS,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    gp_spec,
    run,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)

NAME = "building-zones-floor-asof3-cap64"


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    held=None,
    ads: pd.DataFrame | None = None,
    **kw,
) -> Design:
    """The cap-64 as-of floor design of `frame`, with `ads` read from
    `building_zones_floor_asof3.ROWS` when not given."""
    if ads is None:
        ads = building_zones_floor_asof3.read_ads()
    return building_zones_floor_asof2_cap64.design(
        frame, start, held=held, ads=ads, **kw
    )


def run_record(d: Design) -> dict:
    """The as-of floor model's record on build b3ddebf19af1dc1e, with the raised cap."""
    rec = building_zones_floor_asof3.run_record(d)
    rec["floor_gp"] = rec["floor_gp"] | {"caps": dict(GROUPS)}
    return rec


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof3-cap64`: fit on the split's
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
