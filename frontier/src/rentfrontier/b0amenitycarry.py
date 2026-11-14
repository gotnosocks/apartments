"""Write a B0 dataset whose rows carry each unit code that their unit's earlier ads stated.

    python -m rentfrontier.b0amenitycarry SRC OUT

The kitchen-sink designs, L1 among them, read a row's unit codes (hardwood floors, central air,
a balcony, a view and so on) from its own ad's latest StreetEasy record in the listing-codes
file. A broker who leaves a code out of one ad leaves the row without it, even when the same
unit's earlier ads stated it. This script adds, for each of those codes, a column holding the
union of the row's own code and the codes of its unit's earlier ads.

For each row I take

1. its unit, the (building, unit_id) pair, and its place among the unit's ads in price_at
   order, then audit_id, as `drift_building_phase.months_since_previous` orders them;
2. its opening day, the ad's `on_day` in the ads file the SRC build read (the record's
   onMarketAt, or its createdAt without one), or the UTC day of its price_at when that comes
   first or `on_day` is missing;
3. its earlier ads, the unit's ads placed before it in that order with an opening day before
   its own. An ad placed later, or opened on the same day or later, is never read.

The codes are the unit lists `building_zones_kitchen_sink.code_columns` reads (`feat`,
`private_outdoor`, `views`, `fireplace`, less the dishwasher, washer-dryer and furnished codes
the design takes from the pipeline's fields), and the flag `states_features`. A row with no
unit_id keeps its own codes. I leave the building lists (`amen`, `parking`, `shared_outdoor`,
`storage`) as they are: the design's `bld:` columns already take a majority over the building's
earlier training ads that state amenities.

I write OUT with:

- `rows.parquet`: SRC's rows in SRC's order, with an int8 column `carry:<list>:<code>` for each
  code, `carry:states_features`, and `carry:earlier_ads`, the count of earlier ads read;
- SRC's other files, copied;
- `manifest.json`: SRC's manifest with `rows_sha256` updated and an `amenity_carry` entry
  giving SRC's path and rows SHA-256, the codes and ads files with their SHA-256, the rule,
  and the rows holding and gaining each code.

SRC stays as it is, and OUT must not exist yet.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .b0data import sha256
from .building_zones_kitchen_sink import CODES, UNIT_LISTS, code_columns, days

STATED = "states_features"
PREFIX = "carry:"


def read_codes(path: Path, ids: set[str]) -> tuple[pd.DataFrame, list[str]]:
    """The unit code columns of the listing-codes file `path`, with `states_features`, for
    the listings in `ids`, and the names of the code columns."""
    names = pq.read_schema(path).names
    codes = code_columns(pd.DataFrame(columns=names), UNIT_LISTS)
    t = pq.read_table(path, columns=["listing_id", *codes, STATED])
    ids_ = pa.array(sorted(ids), pa.string()).cast(t["listing_id"].type)
    t = t.filter(pc.is_in(t["listing_id"], value_set=ids_))
    return t.to_pandas(), codes


def read_on_days(path: Path, ids: set[str]) -> pd.Series:
    """Each listing's `on_day` in the ads file `path`, as a UTC day number, for the listings
    in `ids`."""
    t = pq.read_table(path, columns=["listing_id", "on_day"])
    ids_ = pa.array(sorted(ids), pa.string()).cast(t["listing_id"].type)
    a = t.filter(pc.is_in(t["listing_id"], value_set=ids_)).to_pandas()
    on = pd.to_datetime(a.on_day).to_numpy().astype("datetime64[D]")
    return pd.Series(
        np.where(np.isnat(on), np.nan, on.astype(np.int64)),
        index=a.listing_id.astype(str).to_numpy(),
    )


def opening_days(frame: pd.DataFrame, on_days: pd.Series) -> np.ndarray:
    """Each row's opening day: its ad's `on_day` in `on_days`, or its price_at's UTC day when
    that comes first or the ad has none."""
    price_day = days(frame.price_at).astype(float)
    on = frame.listing_id.astype(str).map(on_days).to_numpy(float)
    return np.fmin(on, price_day).astype(np.int64)


def unit_order(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """The rows of `frame` in the order of `drift_building_phase.months_since_previous`, and
    each row's unit as a group number in that order, -1 for a row with no unit_id."""
    at = pd.to_datetime(frame.price_at, utc=True).dt.tz_convert(None).to_numpy()
    none = frame.unit_id.isna().to_numpy()
    unit_id = frame.unit_id.astype(object).to_numpy()
    key = (
        frame.building.astype(str).to_numpy(object) + "|" + np.where(none, "", unit_id)
    )
    order = (
        pd.DataFrame(
            {
                "key": key.astype(str),
                "at": at,
                "audit": frame.audit_id.astype(str).to_numpy(),
            }
        )
        .sort_values(["key", "at", "audit"], kind="stable")
        .index.to_numpy()
    )
    group = pd.factorize(key[order])[0]
    return order, np.where(none[order], -1, group)


def earlier_pairs(
    group: np.ndarray, opened: np.ndarray
) -> tuple[np.ndarray, np.ndarray, int]:
    """For rows in unit order with unit numbers `group` and opening days `opened`: the
    (row, earlier ad) pairs of positions where the earlier ad sits before the row in its unit
    and opened on an earlier day, and the count of pairs dropped for opening on the same day
    or later."""
    n = len(group)
    start = np.r_[True, group[1:] != group[:-1]]
    first = np.maximum.accumulate(np.where(start, np.arange(n), 0))
    rank = np.where(group >= 0, np.arange(n) - first, 0)
    row = np.repeat(np.arange(n), rank)
    offset = np.arange(len(row)) - np.repeat(np.cumsum(rank) - rank, rank)
    earlier = np.repeat(first, rank) + offset
    keep = opened[earlier] < opened[row]
    return row[keep], earlier[keep], int((~keep).sum())


def masks(frame: pd.DataFrame, codes: pd.DataFrame, names: list[str]) -> np.ndarray:
    """Each row's codes in `names`, then `states_features`, as bits of an int64, read from
    its own listing's line of `codes` (0 for a listing without one)."""
    c = codes.set_index(codes.listing_id.astype(str)).reindex(
        frame.listing_id.astype(str)
    )
    m = np.zeros(len(frame), np.int64)
    for k, name in enumerate([*names, STATED]):
        m |= (c[name].fillna(0).to_numpy() > 0).astype(np.int64) << k
    return m


def carry(
    frame: pd.DataFrame, own: np.ndarray, opened: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict]:
    """The union of each row's mask in `own` with the masks of its unit's earlier ads, the
    count of earlier ads read, and counts of the pairs."""
    order, group = unit_order(frame)
    row, earlier, dropped = earlier_pairs(group, opened[order])
    union = own.copy()
    np.bitwise_or.at(union, order[row], own[order[earlier]])
    count = np.bincount(order[row], minlength=len(frame))
    return (
        union,
        count,
        {"pairs_read": len(row), "pairs_opened_same_day_or_later": dropped},
    )


def amenity_carry(src: Path, out: Path, codes_file: Path = CODES) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    ads = manifest["build"]["ads"]
    ads_file = Path(ads["path"])
    if sha256(ads_file) != ads["sha256"]:
        raise SystemExit(f"{ads_file} does not match the manifest's SHA-256")
    if out.exists():
        raise FileExistsError(out)
    frame = pd.read_parquet(src / "rows.parquet")
    ids = set(frame.listing_id.astype(str))
    table, names = read_codes(codes_file, ids)
    own = masks(frame, table, names)
    del table
    opened = opening_days(frame, read_on_days(ads_file, ids))
    union, count, pairs = carry(frame, own, opened)
    columns = [*names, STATED]
    for k, name in enumerate(columns):
        frame[PREFIX + name] = ((union >> k) & 1).astype(np.int8)
    frame[PREFIX + "earlier_ads"] = count.astype(np.int16)
    # OUT is made after every read, so a failed read leaves no OUT behind.
    out.mkdir(parents=True, exist_ok=False)
    frame.to_parquet(out / "rows.parquet", index=False)
    for f in src.iterdir():
        if f.is_file() and f.name not in ("rows.parquet", "manifest.json"):
            shutil.copy(f, out / f.name)
    has = {
        name: (int(((own >> k) & 1).sum()), int(((union >> k) & 1).sum()))
        for k, name in enumerate(columns)
    }
    manifest |= {
        "rows_sha256": sha256(out / "rows.parquet"),
        "amenity_carry": {
            "source": str(src),
            "source_rows_sha256": manifest["rows_sha256"],
            "codes": {"path": str(codes_file), "sha256": sha256(codes_file)},
            "ads": {"path": str(ads_file), "sha256": sha256(ads_file)},
            "rule": "each unit code is the union of the row's own code and the codes of "
            "its unit's earlier ads, the (building, unit_id) ads placed before it in "
            "price_at, audit_id order with an opening day (the ads file's on_day, or the "
            "price_at UTC day when that comes first) before its own; building lists "
            "left as they are",
            "lists": list(UNIT_LISTS),
            "codes_carried": columns,
            "rows": len(frame),
            "rows_with_earlier_ads": int((count > 0).sum()),
            **pairs,
            "rows_own": {k: v[0] for k, v in has.items()},
            "rows_carried": {k: v[1] for k, v in has.items()},
            "rows_gaining": {k: v[1] - v[0] for k, v in has.items()},
            "rows_gaining_any": int((union != own).sum()),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("src", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    print(json.dumps(amenity_carry(args.src, args.out)["amenity_carry"], indent=2))


if __name__ == "__main__":
    main()
