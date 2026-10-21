import numpy as np, pandas as pd
from scipy.spatial import cKDTree
import sys

R = sys.argv[1]
z = np.load(f"{R}/posterior.npz")
bld = z["kept/bld"].reshape(-1, z["kept/bld"].shape[-1])
held = z["heldout"]
rows = pd.read_parquet(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc/rows.parquet",
    columns=["building", "neighbourhood"],
)
tr = rows[~held]
reg = (
    pd.read_parquet(
        "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet",
        columns=["building", "bbl", "latitude", "longitude"],
    )
    .drop_duplicates("building")
    .set_index("building")
)
u = pd.Index(tr.building.unique())
r = reg.reindex(u)
zone = np.where(r.bbl.astype("string").str[0] == "1", 0, 1)
order = list(u[zone == 0]) + list(u[zone == 1])
print(len(order), (zone == 0).sum())
b = pd.DataFrame({"bld": bld.mean(0), "sd": bld.std(0)}, index=order)
b["n"] = tr.building.value_counts().reindex(order).to_numpy()
b["nb"] = (
    tr.groupby("building").neighbourhood.agg(lambda s: s.mode().iat[0]).reindex(order)
)
b["zone"] = np.r_[np.zeros(21994), np.ones(45983)]
lat = reg.latitude.reindex(order).to_numpy()
lon = reg.longitude.reindex(order).to_numpy()
b["x"] = (lon + 73.98) * 84.3
b["y"] = (lat - 40.75) * 111.0
b.to_parquet(sys.argv[2])
