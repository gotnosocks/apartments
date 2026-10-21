"""Building zones with attributes, plus unit size, laundry, dishwasher and through truck routes.

The model is building zones with attributes (`rentfrontier.building_zones_attrs`) at its 1 km
surfaces, with the 2 bedroom bath ladder capped at three full baths, and seven more columns
read from the unit-features snapshot (`rentfrontier.unit_features`):

1. `unit:log_size_rel`, the log of the unit's size over the median stated size for its
   bedroom count, clipped to plus or minus log 2.5. I take the ad's stated size, then the
   median over the unit's other listings, then the median over units on the same line.
   `unit:size_imputed` marks a size from either fill, and `unit:size_unknown` a unit with
   none, whose `unit:log_size_rel` is 0.
2. `unit:laundry_in_unit` and `unit:laundry_in_building`, against an ad that states no
   laundry. StreetEasy has no code for a unit without laundry, so unstated is the reference.
3. `unit:dishwasher`, an ad listing StreetEasy's DISHWASHER feature, against every other ad.
4. `bld:truck_through`, a building facing an NYC DOT through truck route.

The unit columns change between ads of a building, so they cannot move the building level's
mean the way the `bld:` columns do. They join the rows' fixed design like the bed and bath
steps, and their coefficients join the global block with the Normal(0, 0.5) prior. The saved
building effects `bld` are each building's level less its map value, so they come out net of
every column, unit and building alike.

    python -m rentfrontier.run --model building-zones-unit --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, building_zones_attrs
from .building_zones_attrs import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
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
    site_rows,
    site_zone,
    split_index,
    subset,
    wave_matrix,
)
from .registry import EXTERNAL_ROOT

NAME = "building-zones-unit"
SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_UNIT_FEATURES",
        EXTERNAL_ROOT / "unit-features" / "20261021-16cea7c",
    )
)
COLUMNS = (
    "unit:log_size_rel",
    "unit:size_imputed",
    "unit:size_unknown",
    "unit:laundry_in_unit",
    "unit:laundry_in_building",
    "unit:dishwasher",
    "bld:truck_through",
)


def columns(
    frame: pd.DataFrame, units: pd.DataFrame, trucks: pd.DataFrame
) -> np.ndarray:
    """The new columns (COLUMNS) of `frame`'s rows. A listing missing from `units` has no
    size, no laundry stated and no dishwasher, and a building missing from `trucks` faces no
    through route."""
    u = units.drop_duplicates("listing_id").set_index("listing_id")
    u = u.reindex(frame.listing_id.astype(str))
    source = u.size_source.fillna("none").to_numpy()
    laundry = u.laundry.fillna("unstated").to_numpy()
    t = trucks.drop_duplicates("building").set_index("building").truck_through
    truck = frame.building.astype(str).map(t).fillna(0.0).to_numpy(float)
    return np.column_stack(
        [
            np.where(source == "none", 0.0, u.log_size_rel.fillna(0.0).to_numpy(float)),
            np.isin(source, ["unit", "line"]),
            source == "none",
            laundry == "in_unit",
            laundry == "in_building",
            u.dishwasher.fillna(0.0).to_numpy(float) == 1,
            truck == 1,
        ]
    ).astype(float)


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
    nj_registry: pd.DataFrame | None = None,
    attrs: pd.DataFrame | None = None,
    footprints: pd.DataFrame | None = None,
    units: pd.DataFrame | None = None,
    trucks: pd.DataFrame | None = None,
) -> Design:
    """Building zones with attributes' design of `frame` with the new columns appended. I
    leave out a column no row sets."""
    if units is None:
        units = pd.read_parquet(SNAPSHOT / "unit_features.parquet")
    if trucks is None:
        trucks = pd.read_parquet(SNAPSHOT / "truck.parquet")
    d = building_zones_attrs.design(
        frame,
        start,
        registry=registry,
        nj_registry=nj_registry,
        attrs=attrs,
        footprints=footprints,
    )
    new = columns(frame, units, trucks)
    count = dict(d.count)
    keep = []
    for j, n in enumerate(COLUMNS):
        count[n] = int((new[:, j] != 0).sum())
        if count[n] > 0:
            keep.append(j)
    return dataclasses.replace(
        d,
        x=np.hstack([d.x, new[:, keep]]),
        names=list(d.names) + [COLUMNS[j] for j in keep],
        count=count,
    )


def run_record(d: Design) -> dict:
    """Building zones with attributes' record, with the unit-features snapshot."""
    return building_zones_attrs.run_record(d) | {"unit_features": str(SNAPSHOT)}


def summarize(kept: dict, names) -> dict:
    """Building zones with attributes' summary, with each unit coefficient as a percent
    premium too: for `unit:log_size_rel`, a unit e times its bedroom median size."""
    out = building_zones_attrs.summarize(kept, names)
    beta = np.asarray(kept["beta"])
    out["unit"] = {}
    for j, n in enumerate(names):
        if n.startswith("unit:"):
            v = 100 * np.expm1(beta[..., j]).ravel()
            out["unit"][n] = {
                "median": float(np.median(v)),
                "lo": float(np.quantile(v, 0.05)),
                "hi": float(np.quantile(v, 0.95)),
            }
    return out


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-unit`: fit on the split's training rows and
    save the run."""
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
