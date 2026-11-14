"""Count the rows of L1's dataset whose MapPLUTO reading P1 changes, by field and by column.

I read the rows' buildings, months, units and ads, then build the columns that read MapPLUTO
twice with P1's own functions (`drift_building_phase_plutoasof.pluto_columns`): once with
every row reading 26v2, which is L1's reading (the release file's 26v2 equals
`building_attrs.PLUTO` on every field), and once with each row reading the release of its
month. The rest of L1's design stays unbuilt, since it peaks near 9 GB. A row whose building
has no lot keeps L1's columns, so I count only rows with a lot.

The work runs in three steps, each in its own 3 GB scope:

1. `reads OUT` finds each row's lot and release for both readings, counts the rows whose
   fields differ, and writes the reads to OUT;
2. `columns OUT C K` builds both readings' columns for the buildings of part C of K and
   writes the rows each column changes. Every column of a row comes from its own ad and its
   own building's earlier training ads, so the parts need nothing from each other;
3. `tally OUT` counts the rows, units (building and unit_id) and buildings that each field and
   column changes, over all rows and over the held-out ads of the latest split, into
   OUT/counts.json.

    systemd-run --user --scope -q -p MemoryMax=3G python count.py reads OUT
"""

import dataclasses
import glob
import json
import sys
import time

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds

from rentfrontier import (
    building_attrs,
    building_zones_floor_asof,
    building_zones_floor_asof3,
    splits,
)
from rentfrontier import building_zones_kitchen_sink as ks
from rentfrontier import drift_building_phase_plutoasof as M

DATA = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
FRAME = ["listing_id", "building", "unit_id", "price_at", "bedrooms", "full_baths"]
NUMERIC = set(M.FIELDS) - {"lottype", "landmark", "bldgclass"}
# The columns each group of fields reaches, for the summary by feature.
FEATURES = {
    "condo (class)": ["bld:condo"],
    "elevator (class)": ["bld:elevator", "bld:elevator_unknown"],
    "floor columns (floors, class)": list(ks.FLOOR_COLUMNS),
    "year built": [c for c in M.AGE_COLUMNS if c.startswith("bld:built")],
    "alteration year": ["bld:altered_2000_on"],
    "retail": ["bld:retail", "bld:retail_unknown"],
}


@dataclasses.dataclass
class Slim:
    y: np.ndarray
    x: np.ndarray
    names: list
    site: np.ndarray
    count: dict


def log(*a):
    print(f"{time.strftime('%H:%M:%S')}", *a, flush=True)


def same(a, b, numeric):
    """Whether each pair of field values reads the same, both blank counting as the same."""
    if numeric:
        a, b = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    a, b = pd.Series(a), pd.Series(b)
    both = a.isna().to_numpy() & b.isna().to_numpy()
    return both | (a.to_numpy() == b.to_numpy())


def reads(out):
    frame = pd.read_parquet(f"{DATA}/rows.parquet", columns=[*FRAME, "audit_id"])
    frame = frame.assign(building=frame.building.astype(str))
    held = splits.SPLITS["latest"](frame)
    log("rows", len(frame), "held", int(held.sum()))
    registry = pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"])
    t0 = time.perf_counter()
    rows, table, from_today = M.lot_reads(frame, registry)
    log("P1 lot reads", round(time.perf_counter() - t0, 1), "s", len(table))
    late = frame.assign(price_at=pd.Timestamp("2026-11-01", tz="UTC"))
    rows26, table26, _ = M.lot_reads(late, registry)
    assert set(rows26.release) == {"26v2"}
    lot = rows.bbl.to_numpy() != ""
    uid = frame.unit_id.astype(str).where(frame.unit_id.notna(), "")
    unit = np.where(uid == "", "", frame.building + "/" + uid)
    keep = pd.DataFrame(
        {
            "building": frame.building.to_numpy(),
            "unit": unit,
            "held": held,
            "lot": lot,
            "release": rows.release.to_numpy(),
            "status": rows.status.to_numpy(),
            "key": rows.key.to_numpy(),
            "key26": rows26.key.to_numpy(),
        }
    )

    for f in M.FIELDS:
        a = table[f].reindex(rows.key).to_numpy(dtype=object)
        b = table26[f].reindex(rows26.key).to_numpy(dtype=object)
        keep[f"field:{f}"] = ~same(a, b, f in NUMERIC) & lot
    keep.to_parquet(f"{out}/reads.parquet")
    table.reset_index().to_parquet(f"{out}/table.parquet")
    table26.reset_index().to_parquet(f"{out}/table26.parquet")
    with open(f"{out}/reads.json", "w") as fh:
        json.dump({"fields_from_26v2": from_today}, fh)
    log("wrote reads")


def columns(out, part, parts):
    keep = pd.read_parquet(
        f"{out}/reads.parquet", columns=["building", "held", "lot", "key", "key26"]
    )
    mine = pd.util.hash_array(keep.building.to_numpy()) % parts == part
    index = np.flatnonzero(mine)
    keep = keep.iloc[index].reset_index(drop=True)
    frame = pd.read_parquet(f"{DATA}/rows.parquet", columns=FRAME).iloc[index]
    frame = frame.reset_index(drop=True).assign(building=keep.building.to_numpy())
    train = ~keep.held.to_numpy()
    log("part", part, "rows", len(frame))
    ids = frame.listing_id.astype(str).unique().tolist()
    ads = (
        ds.dataset(building_zones_floor_asof3.ROWS)
        .to_table(
            columns=["listing_id", *building_zones_floor_asof.AD_FIELDS],
            filter=pc.field("listing_id").cast("string").isin(ids),
        )
        .to_pandas()
    )
    amenities = ds.dataset(building_zones_floor_asof.AMENITIES / "amenities.parquet")
    amenities = amenities.to_table(
        filter=pc.field("listing_id").cast("string").isin(ids)
    ).to_pandas()
    log("ads", len(ads), "amenities", len(amenities))
    names = [*ks.BASE_COLUMNS, *ks.FLOOR_COLUMNS]
    n = len(frame)
    d = Slim(
        y=np.zeros(n, np.float32),
        x=np.zeros((n, len(names)), bool),
        names=names,
        site=pd.factorize(frame.building)[0],
        count={},
    )
    got = {}
    for which, col in (("l1", "key26"), ("p1", "key")):
        keys = keep[col].to_numpy(dtype=object)
        t = ds.dataset(f"{out}/table{'26' if which == 'l1' else ''}.parquet")
        table = t.to_table(filter=pc.field("key").isin(sorted(set(keys))))
        table = table.to_pandas().set_index("key").astype(object)
        table = table.where(table.notna(), None)
        t0 = time.perf_counter()
        got[which] = M.pluto_columns(d, frame, train, ads, amenities, keys, table)
        log(which, "columns", round(time.perf_counter() - t0, 1), "s")
    lot = keep.lot.to_numpy()
    names = list(got["l1"])
    moved = np.column_stack(
        [
            (np.asarray(got["l1"][c], float) != np.asarray(got["p1"][c], float)) & lot
            for c in names
        ]
    )
    np.savez(f"{out}/moved-{part}.npz", index=index, moved=moved, names=np.array(names))
    log("wrote part", part)


def tally(out):
    keep = pd.read_parquet(f"{out}/reads.parquet")
    n = len(keep)
    held = keep.held.to_numpy()
    building = keep.building.to_numpy()
    unit = keep.unit.to_numpy()

    def count(differ):
        res = {}
        for part, on in (("all", np.ones(n, bool)), ("held", held)):
            m = differ & on
            res[part] = {
                "rows": int(m.sum()),
                "units": int(pd.unique(unit[m & (unit != "")]).size),
                "buildings": int(pd.unique(building[m]).size),
            }
        return res

    result = json.load(open(f"{out}/reads.json"))
    result |= {
        "rows": n,
        "held": int(held.sum()),
        "rows_with_a_lot": int(keep.lot.sum()),
        "held_with_a_lot": int((keep.lot & keep.held).sum()),
        "rows_by_release": keep.release.replace("", "none").value_counts().to_dict(),
        "held_by_release": keep.release[held]
        .replace("", "none")
        .value_counts()
        .to_dict(),
        "rows_by_status": keep.status.value_counts().to_dict(),
        "held_by_status": keep.status[held].value_counts().to_dict(),
        "fields": {f: count(keep[f"field:{f}"].to_numpy()) for f in M.FIELDS},
    }
    moved, names = None, None
    for path in sorted(glob.glob(f"{out}/moved-*.npz")):
        z = np.load(path)
        if moved is None:
            names = list(z["names"])
            moved = np.zeros((n, len(names)), bool)
        moved[z["index"]] = z["moved"]
    by = {c: moved[:, j] for j, c in enumerate(names)}
    result["columns"] = {c: count(v) for c, v in by.items()}
    grouped = {c for v in FEATURES.values() for c in v}
    features = {
        k: count(np.any([by[c] for c in v], axis=0)) for k, v in FEATURES.items()
    }
    features |= {c: result["columns"][c] for c in names if c not in grouped}
    features["any column"] = count(moved.any(axis=1))
    result["features"] = features
    with open(f"{out}/counts.json", "w") as fh:
        json.dump(result, fh, indent=1)
    log("wrote counts")


if __name__ == "__main__":
    step, out, *rest = sys.argv[1:]
    {"reads": reads, "columns": columns, "tally": tally}[step](out, *map(int, rest))
