"""Coverage of the year built bands, altered since 2000 and retail on the latest split's training ads."""

import sys, numpy as np, pandas as pd

sys.path.insert(0, "/data1/apartments/tmp/bzy")
from common import DATASET
from rentfrontier import b0, splits

f = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](f)
f = f[~held]
a = pd.read_parquet(
    "/data1/apartments/external/building-age/20261021-3a64aa22/age.parquet"
).set_index("building")
b = f.building.astype(str)
y = b.map(a.year_built)
yr = f.price_at.dt.year.to_numpy()
al = np.fmax(b.map(a.alter1).to_numpy(float), b.map(a.alter2).to_numpy(float))
a1, a2 = b.map(a.alter1).to_numpy(float), b.map(a.alter2).to_numpy(float)
altered = ((a1 >= 2000) & (a1 <= yr)) | ((a2 >= 2000) & (a2 <= yr))
altered_static = al >= 2000
era = pd.cut(
    y,
    [0, 1899, 1939, 1979, 1999, 2009, 3000],
    labels=["<1900", "1900-39", "1940-79", "1980-99", "2000-09", "2010+"],
).astype(str)
print(pd.Series(era).value_counts(normalize=True).round(4))
print("built after ad year", float((y.to_numpy() > yr).mean()))
print("altered (by ad date)", altered.mean(), "static", altered_static.mean())
print(
    "retail",
    b.map(a.retail).fillna(0).mean(),
    "retail unknown",
    b.map(a.retail_unknown).fillna(1).mean(),
    "missing from table",
    (~b.isin(a.index)).mean(),
)
tr = (
    pd.read_parquet(
        "/data1/apartments/external/unit-features/20261021-16cea7c/truck.parquet"
    )
    .drop_duplicates("building")
    .set_index("building")
    .truck_through
)
gy = (
    pd.read_parquet(
        "/data1/apartments/external/building-gym/20261021-752c7d3d/gym.parquet"
    )
    .drop_duplicates("building")
    .set_index("building")
    .gym
)
t = b.map(tr).fillna(0) == 1
g = b.map(gy).fillna(0) == 1
r = b.map(a.retail).fillna(0) == 1
df = pd.DataFrame(
    {
        "era": era,
        "truck": t.to_numpy(),
        "gym": g.to_numpy(),
        "retail": r.to_numpy(),
        "altered": altered,
    }
)
print(df.groupby("era")[["truck", "gym", "retail", "altered"]].mean().round(3))
print("retail share: truck", r[t].mean(), "non-truck", r[~t].mean())
print("price_at years", pd.Series(yr).value_counts().sort_index().to_dict())
