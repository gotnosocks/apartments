import numpy as np, pandas as pd
from rentfrontier import b0, splits
from common import DATASET

frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
g = (
    pd.read_parquet(
        "/data1/apartments/external/building-gym/20261021-752c7d3d/gym.parquet"
    )
    .drop_duplicates("building")
    .set_index("building")
    .gym
)
gym = frame.building[~held].astype(str).map(g).fillna(0).to_numpy() == 1
for f in (
    "/data1/apartments/tmp/resid/resid_attrs.parquet",
    "/data1/apartments/tmp/bzu/resid_unit.parquet",
    "resid_gym.parquet",
):
    d = pd.read_parquet(f, columns=["bld", "F", "zone", "mu"])
    for c in ("bld", "F"):
        d[c] -= d.groupby("zone")[c].transform("mean")
    print(
        f.split("/")[-1],
        "gym: bld %.4f F %.4f | no gym: bld %.4f F %.4f"
        % (d.bld[gym].mean(), d.F[gym].mean(), d.bld[~gym].mean(), d.F[~gym].mean()),
    )
