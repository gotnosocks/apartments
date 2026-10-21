"""Whether each building has a gym, from StreetEasy's amenity codes on its ads.

I read each listing's latest raw record and take its amenity list, `propertyDetails.amenities.list`.
A listing with an empty or missing list states no amenities. For each building of the pipeline
rows I then count

1. `stating`, the building's listings that state amenities, and
2. `gym_share`, the share of those listings whose list has the GYM code.

`gym` is 1 where at least half of the stating listings list a gym, and `gym_unknown` is 1 where
no listing of the building states amenities. Ads of one building disagree about the gym when a
broker leaves amenities out, so the majority over listings gives a single value per building.
I write the table to EXTERNAL_ROOT/building-gym/<date>-<sha>/gym.parquet.

    python -m rentfrontier.building_gym OUT_DIR
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from .unit_features import RECORDS, ROWS

GYM_CODE = "GYM"
MAJORITY = 0.5


def amenities(records: Path = RECORDS) -> pd.DataFrame:
    """`states` and `gym` for each listing's latest raw record, by listing_id."""
    import pyarrow.parquet as pq

    f = pq.ParquetFile(records)
    latest: dict[str, tuple] = {}
    for i in range(f.num_row_groups):
        t = f.read_row_group(
            i, columns=["listing_id", "collected_at", "raw_listing_json"]
        ).to_pandas()
        for lid, at, raw in zip(
            t.listing_id.astype(str), t.collected_at, t.raw_listing_json
        ):
            if lid in latest and latest[lid][0] >= at:
                continue
            try:
                j = json.loads(raw)
            except (TypeError, ValueError):
                continue
            am = ((j.get("propertyDetails") or {}).get("amenities") or {}).get("list")
            am = am or []
            latest[lid] = (at, bool(am), GYM_CODE in am)
    return pd.DataFrame(
        [(k, v[1], v[2]) for k, v in latest.items()],
        columns=["listing_id", "states", "gym"],
    )


def building_table(rows: pd.DataFrame, listing: pd.DataFrame) -> pd.DataFrame:
    """`stating`, `gym_share`, `gym` and `gym_unknown` for each building of `rows`, from the
    per-listing amenity table `listing`. `rows` needs listing_id and building."""
    r = rows[["listing_id", "building"]].drop_duplicates("listing_id")
    r = r.assign(listing_id=r.listing_id.astype(str), building=r.building.astype(str))
    r = r.merge(listing, on="listing_id", how="left")
    r["states"] = r.states.fillna(False).astype(bool)
    r["gym"] = r.gym.fillna(False).astype(bool) & r.states
    g = r.groupby("building").agg(
        stating=("states", "sum"), gyms=("gym", "sum"), listings=("states", "size")
    )
    share = g.gyms / g.stating.where(g.stating > 0)
    return pd.DataFrame(
        {
            "building": g.index.astype(str),
            "listings": g.listings.to_numpy(int),
            "stating": g.stating.to_numpy(int),
            "gym_share": share.to_numpy(float),
            "gym": (share >= MAJORITY).to_numpy(float),
            "gym_unknown": (g.stating == 0).to_numpy(float),
        }
    )


def main(argv=None) -> None:
    """Write OUT_DIR/gym.parquet."""
    out = Path((argv or sys.argv[1:])[0])
    out.mkdir(parents=True, exist_ok=True)
    rows = pd.read_parquet(ROWS, columns=["listing_id", "building"])
    t = building_table(rows, amenities())
    t.to_parquet(out / "gym.parquet")
    print(
        f"{len(t)} buildings, gym {int(t.gym.sum())}, unknown {int(t.gym_unknown.sum())}",
        f"disagreeing {int(((t.gym_share > 0) & (t.gym_share < 1)).sum())}",
    )


if __name__ == "__main__":
    main()
