"""How much the as-of rebuild (`rentfrontier.building_zones_floor_asof`) changes on the latest
split, against the snapshot tables the floor model reads.

I rebuild the size, building and floor tables from the latest split's training rows and
report:

1. the share of training rows whose snapshot size came from a unit or line fill and which get
   no fill from earlier training rows (the snapshot's fill read a later or held-out ad);
2. the share of training and held-out rows whose size, elevator, doorman, floors, gym or top
   floor value changes;
3. the share of the frame's buildings whose elevator, doorman, floors or gym value changes.

Run it from the repo root with about 6 GB:

    FRONTIER_DATASET=/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc \\
    FRONTIER_LISTING_AMENITIES=/data1/apartments/tmp/asof-features/listing-amenities \\
    PYTHONPATH=frontier/src python docs/notes/conference-followups-2026-10-22/asof_counts.py
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import (
    building_attrs,
    building_zones_floor,
    building_zones_floor_asof,
    building_zones_gym,
    building_zones_unit,
    splits,
    unit_features,
)


def changed(a, b) -> np.ndarray:
    """Rows where `a` and `b` differ, two missing values counting as equal."""
    a = pd.Series(np.asarray(a, dtype=object))
    b = pd.Series(np.asarray(b, dtype=object))
    na = a.isna() & b.isna()
    num_a, num_b = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    both = num_a.notna() & num_b.notna()
    close = both & np.isclose(num_a.fillna(0), num_b.fillna(0), rtol=0, atol=1e-9)
    same = na | close | (~both & (a.astype(str) == b.astype(str)))
    return ~same.to_numpy()


def share(mask) -> str:
    mask = np.asarray(mask, bool)
    return f"{mask.mean():.4f} ({int(mask.sum()):,} of {len(mask):,})"


def main() -> None:
    frame = pd.read_parquet(Path(os.environ["FRONTIER_DATASET"]) / "rows.parquet")
    held = splits.latest_split(frame)
    train = ~held
    ads = pd.read_parquet(
        unit_features.ROWS, columns=["listing_id", *building_zones_floor_asof.AD_FIELDS]
    )
    amenities = pd.read_parquet(
        building_zones_floor_asof.AMENITIES / "amenities.parquet"
    )
    lots = building_zones_floor_asof.load_lots()
    units = pd.read_parquet(building_zones_unit.SNAPSHOT / "unit_features.parquet")
    new = building_zones_floor_asof.tables_for(frame, held, ads, amenities, lots, units)
    print(f"rows {len(frame):,}, held out {int(held.sum()):,}")

    lid = frame.listing_id.astype(str)
    bld = frame.building.astype(str)

    def by_listing(t):
        t = t.drop_duplicates("listing_id")
        return t.assign(listing_id=t.listing_id.astype(str)).set_index("listing_id")

    def by_building(t):
        t = t.drop_duplicates("building")
        return t.assign(building=t.building.astype(str)).set_index("building")

    old_u = by_listing(units).reindex(lid)
    new_u = by_listing(new["units"]).reindex(lid)
    filled = old_u.size_source.isin(["unit", "line"]).to_numpy()
    lost = filled & (new_u.size_source == "none").to_numpy()
    print("(i) training rows with a snapshot unit or line fill and no as-of fill:")
    print("    of training rows", share(lost[train]))
    print("    of filled training rows", share(lost[train & filled]))
    print(
        "    filled training rows by as-of source",
        new_u.size_source[train & filled].value_counts().to_dict(),
    )

    old_a = by_building(pd.read_parquet(building_attrs.ATTRS)).reindex(bld)
    new_a = by_building(new["attrs"]).reindex(bld)
    old_g = by_building(
        pd.read_parquet(building_zones_gym.GYM_SNAPSHOT / "gym.parquet")
    ).reindex(bld)
    new_g = by_building(new["gyms"]).reindex(bld)
    floor_dir = building_zones_floor.FLOOR_SNAPSHOT
    old_f = by_listing(pd.read_parquet(floor_dir / "floor.parquet")).reindex(lid)
    new_f = by_listing(new["floors"]).reindex(lid)
    values = {
        "sqft": changed(old_u.sqft, new_u.sqft),
        "size": changed(old_u.sqft, new_u.sqft)
        | changed(old_u.log_size_rel, new_u.log_size_rel),
        "elevator": changed(old_a.elevator, new_a.elevator),
        "doorman": changed(old_a.doorman, new_a.doorman),
        "floors": changed(old_a.floors, new_a.floors),
        "gym": changed(old_g.gym, new_g.gym)
        | changed(old_g.gym_unknown, new_g.gym_unknown),
        "top": changed(old_f.top, new_f.top),
    }
    print("(ii) rows whose value changes, training / held out:")
    for name, m in values.items():
        print(f"    {name:9s} {share(m[train])}  /  {share(m[held])}")
    anyb = np.zeros(len(frame), bool)
    for name in ("elevator", "doorman", "floors", "gym"):
        anyb |= values[name]
    print(f"    any bld   {share(anyb[train])}  /  {share(anyb[held])}")

    print("(iii) buildings whose value changes:")
    first = ~bld.duplicated().to_numpy()
    for name in ("elevator", "doorman", "floors", "gym"):
        print(f"    {name:9s} {share(values[name][first])}")
    print(f"    any       {share(anyb[first])}")


if __name__ == "__main__":
    main()
