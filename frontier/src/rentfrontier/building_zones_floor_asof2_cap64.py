"""Building zones with the unit's floor on as-of features, with the elevator curve run to floor 64.

The model is `rentfrontier.building_zones_floor_asof2`, except at the top of the elevator floor
curve. That model caps elevator floors at 47 (`building_zones_floor.ELEV_CAP`), about the 99th
percentile of elevator training ads, so its floor-47 column pools every unit from 47 up. The
pooled node sits 3.4 points above floor 46, and floors 47+ have a median of 52
(docs/notes/conference-followups-2026-10-22.md, section d). Here I run the curve to ELEV_CAP =
64, about the 99.9th percentile of elevator training ads on the latest split of the corrected
build, with at least 12 buildings on each floor up to it. The Gaussian process prior on log
floor keeps its amplitude and lengthscale priors, so it pools the sparse floors toward their
neighbors.

To build the design I take the as-of floor design and split its floor-47 column: an elevator
unit on floor k > 47 moves to column `unit:elev_f{min(k, ELEV_CAP)}`. The walk-up curve keeps
its cap of 6.

    python -m rentfrontier.run --model building-zones-floor-asof2-cap64 --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import (
    b0,
    building_zones_floor,
    building_zones_floor_asof,
    building_zones_floor_asof2,
    building_zones_gibbs,
    building_zones_unit,
)
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
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)

NAME = "building-zones-floor-asof2-cap64"
ELEV_CAP = 64
GROUPS = (("elev", ELEV_CAP), ("walkup", building_zones_floor.WALKUP_CAP))
OLD_CAP = building_zones_floor.ELEV_CAP


def split_top(d: Design, frame: pd.DataFrame, floors: pd.DataFrame) -> Design:
    """`d` with its `unit:elev_f{OLD_CAP}` column split into one column per floor from
    OLD_CAP to ELEV_CAP, by each row's floor in `floors`. The new columns follow the old one."""
    f = floors.drop_duplicates("listing_id").set_index("listing_id")
    floor = f.floor.reindex(frame.listing_id.astype(str)).to_numpy(float)
    names = list(d.names)
    j = names.index(f"unit:elev_f{OLD_CAP}")
    pooled = d.x[:, j] == 1
    k = np.minimum(np.nan_to_num(floor, nan=0.0), ELEV_CAP)
    new = np.column_stack(
        [pooled & (k == c) for c in range(OLD_CAP, ELEV_CAP + 1)]
    ).astype(d.x.dtype)
    assert (new.sum(1) == pooled).all()
    cols = [f"unit:elev_f{c}" for c in range(OLD_CAP, ELEV_CAP + 1)]
    count = dict(d.count) | {c: int(new[:, i].sum()) for i, c in enumerate(cols)}
    return dataclasses.replace(
        d,
        x=np.hstack([d.x[:, :j], new, d.x[:, j + 1 :]]),
        names=names[:j] + cols + names[j + 1 :],
        count=count,
    )


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    held=None,
    ads: pd.DataFrame | None = None,
    amenities: pd.DataFrame | None = None,
    lots: pd.DataFrame | None = None,
    units: pd.DataFrame | None = None,
    **tables,
) -> Design:
    """The as-of floor design of `frame` (`building_zones_floor_asof2`), with the elevator
    curve run to ELEV_CAP."""
    held = building_zones_floor_asof.held_out(frame, held)
    if ads is None:
        ads = pd.read_parquet(
            building_zones_floor_asof2.ROWS, columns=["listing_id", *AD_FIELDS]
        )
    if amenities is None:
        amenities = pd.read_parquet(
            building_zones_floor_asof.AMENITIES / "amenities.parquet"
        )
    if lots is None:
        lots = building_zones_floor_asof.load_lots()
    if units is None:
        units = pd.read_parquet(building_zones_unit.SNAPSHOT / "unit_features.parquet")
    rebuilt = building_zones_floor_asof.tables_for(
        frame, held, ads, amenities, lots, units
    )
    tables = {k: v for k, v in tables.items() if k not in rebuilt}
    d = building_zones_floor.design(frame, start, **rebuilt, **tables)
    return split_top(d, frame, rebuilt["floors"])


def gp_spec(names) -> list[dict]:
    """The floor curves' Gaussian process priors, as `building_zones_floor.gp_spec` gives
    them, with the elevator curve's columns up to ELEV_CAP."""
    out = []
    for g, cap in GROUPS:
        cols = [f"unit:{g}_f{k}" for k in range(2, cap + 1)]
        cols = [c for c in cols if c in names]
        if cols:
            k = [float(c.rsplit("_f", 1)[1]) for c in cols]
            out.append(
                dict(
                    name=g,
                    cols=cols,
                    x=np.log(k),
                    amp=building_zones_floor.GP_AMP,
                    ls=building_zones_floor.GP_LS,
                )
            )
    return out


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """The blocked Gibbs sweep with the floor curves' Gaussian process priors to ELEV_CAP."""
    return building_zones_gibbs.run(
        d, priors, settings, log, checkpoint, gp=gp_spec(d.names)
    )


def run_record(d: Design) -> dict:
    """The as-of floor model's record on the corrected build, with the raised cap."""
    rec = building_zones_floor_asof2.run_record(d)
    rec["floor_gp"] = rec["floor_gp"] | {"caps": dict(GROUPS)}
    return rec


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof2-cap64`: fit on the split's
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
