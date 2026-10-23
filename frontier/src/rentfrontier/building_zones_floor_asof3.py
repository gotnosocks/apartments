"""Building zones with the unit's floor on as-of features, read from the build after #1242.

The model, sampler and run record are those of `rentfrontier.building_zones_floor_asof2`, which
reads each ad's size, floor and building fields from build b495f6dd53222649. Here I read them
from ROWS below, the build made after the ledger rows of #1242 set two studios to 1 bath and
excluded one row. The fit dataset comes from the same build
(b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc), so the ads and the rows agree.

    python -m rentfrontier.run --model building-zones-floor-asof3 --split latest --name NAME
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from . import b0, building_zones_floor_asof
from .building_zones_floor_asof2 import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
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

NAME = "building-zones-floor-asof3"
ROWS = Path("/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet")


def read_ads() -> pd.DataFrame:
    """The ad fields of the as-of design, read from ROWS."""
    return pd.read_parquet(ROWS, columns=["listing_id", *AD_FIELDS])


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, ads=None, **kw
):
    """The as-of floor design of `frame`, with `ads` read from ROWS when not given."""
    if ads is None:
        ads = read_ads()
    return building_zones_floor_asof.design(frame, start, held=held, ads=ads, **kw)


def run_record(d: Design) -> dict:
    """The as-of floor model's record, with the pipeline rows this module reads."""
    rec = building_zones_floor_asof.run_record(d)
    rec["asof"] = rec["asof"] | {"pipeline_rows": str(ROWS)}
    return rec


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof3`: fit on the split's training rows
    and save the run."""
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
