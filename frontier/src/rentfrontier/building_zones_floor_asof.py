"""Building zones with the unit's floor, with every feature read from other ads rebuilt from the
split's training rows.

The model and its columns are those of building zones with the unit's floor
(`rentfrontier.building_zones_floor`). The snapshots that model reads summarise every ad of the
pipeline rows, so on the latest split a held-out ad, or one dated after a training ad, can move
a training row's features. Rents never enter them, but a held-out row's own ad can still set
its building's elevator or a neighbour's size. Here I rebuild those features from the frame's
training rows at design time:

1. Unit size. A row keeps its own stated size (100 to 10,000 sq ft, as in
   `rentfrontier.unit_features`). Where it states none, I fill it with
   `sizefill.asof_size`, which reads only rows priced on earlier days, and I blank the stated
   sizes of held-out rows before the fill, so none of them fills another row. I keep the
   unit and line layers (FILLS) and drop the building layer. The as-of filler differs from
   the snapshot's fill even with no rows held out:
   - it groups units by `unit_id`, where the snapshot uses the unit label from the URL;
   - its line key adds full baths, and it keeps top floors and penthouse labels in the line;
   - it fills with a mean of log sizes, where the snapshot takes a median;
   - it reads only source sizes from 150 to 8,000 sq ft.
   `unit:log_size_rel` divides by the median
   stated size for the bedroom count (4 or more pooled) over training rows, and keeps the
   clip of plus or minus log 2.5.
2. Elevator, doorman and building floor count. I run `building_attrs.ad_attributes` on the
   training rows' ads and `building_attrs.attributes` on the result, with the same MapPLUTO
   and NJ parcel fallbacks as the building-attributes snapshot (`load_lots`). The floor model
   reads the elevator and doorman levels; the floor count goes into the table too, though no
   column of this design reads it.
3. Gym. I run `building_gym.building_table` on the training rows, with each listing's amenity
   flags from the listing amenities table (AMENITIES, written by `building_gym.amenities`).
4. The unit's floor. The top-floor flag and a penthouse's floor need the building's top floor,
   which comes from MapPLUTO's floor count, else the highest floor any listing of the building
   states. I take that fallback over training rows and then run `unit_floor.floor_table`.

I read only the frame's rows. The snapshots read every pipeline row, including the rows the
data rules drop, so with no rows held out the elevator, doorman, gym and top floors here can
still differ from the snapshots on real data.

Each building value comes from that building's training ads, at any date, and applies to all of
its rows, held-out ones included. Laundry, dishwasher and the floor and flags of the row's own
ad come from the row's own ad, so I keep them as the snapshots have them.

The design needs to know which rows are held out. `design` takes the mask as `held`; without
it, I draw the split named by SPLIT, which `main_run` sets from `--split`, on the frame it is
given, as `b0.main_run` does. With neither, `design` raises.

    python -m rentfrontier.run --model building-zones-floor-asof --split latest --name NAME
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import (
    b0,
    building_attrs,
    building_gym,
    building_zones_floor,
    building_zones_unit,
    sizefill,
    splits,
    unit_features,
    unit_floor,
)
from .building_zones_floor import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
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
from .registry import EXTERNAL_ROOT

NAME = "building-zones-floor-asof"
# Each listing's amenity flags (`states`, `gym`) from its latest raw record, as
# `building_gym.amenities` reads them.
AMENITIES = Path(
    os.environ.get(
        "FRONTIER_LISTING_AMENITIES",
        EXTERNAL_ROOT / "listing-amenities" / "20261022-e9c46a0",
    )
)
AD_FIELDS = (
    "page",
    "square_feet",
    "building_floor_count",
    "listed_floor",
    "elevator",
    "doorman_type",
)
FILLS = ("unit", "line")  # the `sizefill.asof_size` layers a missing size may come from
# The split `design` draws when it is given no mask; `main_run` sets it from --split.
SPLIT: str | None = None


def held_out(frame: pd.DataFrame, held=None) -> np.ndarray:
    """The held-out mask of `frame`'s rows: `held` if given, else SPLIT's split."""
    if held is not None:
        return np.asarray(held, bool)
    if SPLIT is None:
        raise ValueError(
            f"{NAME} needs the held-out rows: pass `held` or set SPLIT to a split name"
        )
    return splits.SPLITS[SPLIT](frame)


def ad_rows(frame: pd.DataFrame, ads: pd.DataFrame) -> pd.DataFrame:
    """`frame`'s rows in order, with the AD_FIELDS of each row's ad from the pipeline rows
    `ads`, joined on listing_id. The building and unit are the frame's."""
    a = ads.drop_duplicates("listing_id")
    a = a.assign(listing_id=a.listing_id.astype(str))[["listing_id", *AD_FIELDS]]
    r = frame[["listing_id", "unit_id", "price_at", "bedrooms", "full_baths"]].assign(
        listing_id=frame.listing_id.astype(str).to_numpy(),
        building=frame.building.astype(str).to_numpy(),
    )
    return r.reset_index(drop=True).merge(
        a, on="listing_id", how="left", validate="many_to_one"
    )


def size_table(rows: pd.DataFrame, train: np.ndarray) -> pd.DataFrame:
    """`sqft`, `size_source` and `log_size_rel` for each of `rows` (`ad_rows`' table), with
    fills from earlier training rows only."""
    lo, hi = unit_features.SQFT_RANGE
    sq = rows.square_feet.astype(float)
    stated = sq.where((sq >= lo) & (sq <= hi))
    sources = rows.assign(
        canonical_unit_url=rows.page.fillna("").astype(str),
        square_feet=sq.where(train),
    )
    fill = sizefill.asof_size(sources)
    take = stated.isna().to_numpy() & fill.source.isin(FILLS).to_numpy()
    sqft = stated.fillna(fill.sqft.where(take))
    source = np.where(
        stated.notna().to_numpy(),
        "stated",
        np.where(take, fill.source.to_numpy(str), "none"),
    )
    beds = rows.bedrooms.clip(upper=4)
    med = stated[train].groupby(beds[train]).median()
    rel = np.log(sqft / beds.map(med)).clip(-unit_features.CLIP, unit_features.CLIP)
    return pd.DataFrame(
        {
            "listing_id": rows.listing_id.to_numpy(),
            "sqft": sqft.to_numpy(float),
            "size_source": source,
            "log_size_rel": rel.fillna(0.0).to_numpy(float),
        }
    )


def unit_table(
    rows: pd.DataFrame, train: np.ndarray, units: pd.DataFrame
) -> pd.DataFrame:
    """The unit-features table of `rows`: sizes from `size_table`, and laundry and dishwasher
    from the snapshot table `units`, both of which read the row's own ad."""
    out = size_table(rows, train)
    u = units.drop_duplicates("listing_id")
    u = u.assign(listing_id=u.listing_id.astype(str)).set_index("listing_id")
    u = u.reindex(out.listing_id)
    out["laundry"] = u.laundry.to_numpy()
    out["dishwasher"] = u.dishwasher.to_numpy()
    return out


def load_lots() -> pd.DataFrame:
    """Each building's MapPLUTO or NJ parcel floors, class and year built, as the
    building-attributes snapshot reads them."""
    registry = pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"])
    registry_nj = pd.read_parquet(
        building_attrs.REGISTRY_NJ, columns=["building", "lot"]
    )
    pluto = pd.read_parquet(
        building_attrs.PLUTO, columns=["bbl", "numfloors", "bldgclass", "yearbuilt"]
    )
    parcels = pd.read_parquet(
        building_attrs.NJ_PARCELS, columns=["lot", "qualifier", "year_built"]
    )
    lots = pd.concat(
        [
            building_attrs.nyc_lots(registry, pluto),
            building_attrs.nj_lots(registry_nj, parcels),
        ]
    )
    return lots[~lots.index.duplicated()]


def attrs_table(
    rows: pd.DataFrame, train: np.ndarray, lots: pd.DataFrame
) -> pd.DataFrame:
    """The building-attributes table from the training rows' ads and the lots."""
    ads = building_attrs.ad_attributes(rows[train])
    return building_attrs.attributes(ads, lots)


def gym_table(
    rows: pd.DataFrame, train: np.ndarray, amenities: pd.DataFrame
) -> pd.DataFrame:
    """The building gym table from the training rows' listings."""
    a = amenities.assign(listing_id=amenities.listing_id.astype(str))
    return building_gym.building_table(rows[train], a)


def top_floors(
    rows: pd.DataFrame, train: np.ndarray, lots: pd.DataFrame
) -> pd.DataFrame:
    """Each building's top floor and its source, as `unit_floor.top_floors` takes them, with
    the ads' fallback read from training rows."""
    pl = np.floor(pd.to_numeric(lots.numfloors, errors="coerce"))
    pl = pl[pl >= 1]
    pl.index = pl.index.astype(str)
    seen = rows[train].groupby("building").listed_floor.max()
    top = pl.reindex(seen.index.union(pl.index))
    source = pd.Series(np.where(top.notna(), "pluto", "none"), index=top.index)
    fill = top.isna() & seen.reindex(top.index).notna()
    top[fill] = seen.reindex(top.index)[fill]
    source[fill] = "ads"
    return pd.DataFrame({"top_floor": top, "top_source": source})


def floor_table(
    rows: pd.DataFrame, train: np.ndarray, lots: pd.DataFrame
) -> pd.DataFrame:
    """The unit-floor table of `rows`, with each building's top floor from `top_floors`."""
    return unit_floor.floor_table(rows, top_floors(rows, train, lots))


def tables_for(
    frame: pd.DataFrame,
    held: np.ndarray,
    ads: pd.DataFrame,
    amenities: pd.DataFrame,
    lots: pd.DataFrame,
    units: pd.DataFrame,
) -> dict:
    """The `attrs`, `units`, `gyms` and `floors` tables `building_zones_floor.design` reads,
    rebuilt from the rows of `frame` outside `held`."""
    rows = ad_rows(frame, ads)
    train = ~np.asarray(held, bool)
    return {
        "attrs": attrs_table(rows, train, lots),
        "units": unit_table(rows, train, units),
        "gyms": gym_table(rows, train, amenities),
        "floors": floor_table(rows, train, lots),
    }


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
    """Building zones with the unit's floor's design of `frame`, with its size, building and
    floor tables rebuilt from the rows outside `held` (`held_out`). `ads` are the pipeline
    rows, `amenities` the listing amenities table, `lots` `load_lots`' table and `units` the
    unit-features snapshot; each defaults to its file."""
    held = held_out(frame, held)
    if ads is None:
        ads = pd.read_parquet(unit_features.ROWS, columns=["listing_id", *AD_FIELDS])
    if amenities is None:
        amenities = pd.read_parquet(AMENITIES / "amenities.parquet")
    if lots is None:
        lots = load_lots()
    if units is None:
        units = pd.read_parquet(building_zones_unit.SNAPSHOT / "unit_features.parquet")
    rebuilt = tables_for(frame, held, ads, amenities, lots, units)
    # A snapshot table passed under a rebuilt table's name gives way to the rebuilt one.
    tables = {k: v for k, v in tables.items() if k not in rebuilt}
    return building_zones_floor.design(frame, start, **rebuilt, **tables)


def run_record(d: Design) -> dict:
    """Building zones with the unit's floor's record, with the snapshots this design rebuilds
    marked and the as-of choices."""
    rebuilt = "rebuilt from the split's training rows (asof)"
    return building_zones_floor.run_record(d) | {
        "building_attrs": rebuilt,
        "building_gym": rebuilt,
        "unit_floor": rebuilt,
        "asof": {
            "split": SPLIT,
            "pipeline_rows": str(unit_features.ROWS),
            "listing_amenities": str(AMENITIES),
            "lots": [
                str(building_attrs.REGISTRY),
                str(building_attrs.REGISTRY_NJ),
                str(building_attrs.PLUTO),
                str(building_attrs.NJ_PARCELS),
            ],
            "size": "own stated size, else sizefill.asof_size from earlier training rows",
            "size_fills": list(FILLS),
            "size_median": "per bedroom count over training rows' stated sizes",
            "building": "elevator, doorman, floors, gym and the ads' top floor from "
            "training rows' ads, MapPLUTO and NJ parcel fallbacks as the snapshots",
        },
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof`: fit on the split's training rows
    and save the run."""
    global SPLIT
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    SPLIT = parser.parse_known_args(argv)[0].split
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
