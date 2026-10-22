"""Within-building support for the top of the elevator floor curve on the latest split.

    python floor_support.py

For each elevator floor from 30 up, and for the pooled 47+ node, this counts the training ads
and buildings with a unit on that floor, the buildings among them with training ads on some
other elevator floor (so a within-building contrast exists), and the largest building's share of
the floor's ads. For the 47+ node it also prints the distribution of the actual floors.
"""

import numpy as np
import pandas as pd

from rentfrontier import b0, splits
from rentfrontier import building_zones_floor as bzf

DATASET = (
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
SNAP = "/data1/apartments/external/unit-floor/20261021-d84914c0/floor.parquet"

frame = b0.load_frame(DATASET)
train = ~splits.SPLITS["latest"](frame)
d = bzf.design(frame)
names = list(d.names)
elev = d.x[:, names.index("bld:elevator")] == 1
floors = pd.read_parquet(SNAP, columns=["listing_id", "floor"])
fl = (
    frame.listing_id.astype(str)
    .map(
        floors.assign(listing_id=floors.listing_id.astype(str))
        .set_index("listing_id")
        .floor
    )
    .to_numpy()
)
keep = train & elev & np.isfinite(fl)
t = pd.DataFrame(
    {
        "building": frame.building.astype(str).to_numpy()[keep],
        "floor": np.minimum(fl[keep], bzf.ELEV_CAP).astype(int),
        "raw": fl[keep],
    }
)
nfloors = t.groupby("building").floor.nunique()
rows = []
for k in list(range(30, bzf.ELEV_CAP + 1)):
    s = t[t.floor == k]
    b = s.building.value_counts()
    rows.append(
        dict(
            floor=f"{k}+" if k == bzf.ELEV_CAP else str(k),
            ads=len(s),
            buildings=len(b),
            with_other_floor=int((nfloors[b.index] > 1).sum()),
            top_building_share=round(b.iloc[0] / len(s), 3) if len(s) else np.nan,
            top3_share=round(b.iloc[:3].sum() / len(s), 3) if len(s) else np.nan,
        )
    )
print(pd.DataFrame(rows).to_string(index=False))
top = t[t.floor == bzf.ELEV_CAP].raw
print("47+ training ads", len(top))
print(top.describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.99]).round(1).to_string())
print(
    pd.cut(top, [46, 50, 55, 60, 70, 80, 200]).value_counts().sort_index().to_string()
)
