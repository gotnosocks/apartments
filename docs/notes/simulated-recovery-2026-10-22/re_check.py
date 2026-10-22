import numpy as np, pandas as pd
from rentfrontier import b0, splits, building_zones_unit as bzu

frame = b0.load_frame(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
held = splits.SPLITS["latest"](frame)
u = pd.read_parquet(bzu.SNAPSHOT / "unit_features.parquet")
t = pd.read_parquet(bzu.SNAPSHOT / "truck.parquet")
X = bzu.columns(frame, u, t)[:, :6]
tr = ~held
dz = np.load("/data1/apartments/tmp/sim-recovery/design.npz")
T = np.load("/data1/apartments/tmp/sim-recovery/realistic/truth.npz")
# site of each row: map building -> site via saved design order isn't stored; rebuild from building order
bld_of = pd.Series(T["bld"])
# recover site index: sites are ordered as in the design; use frame building -> site through a quick design-free route
from rentfrontier import whitened_zones

reg = pd.read_parquet(
    "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet",
    columns=["building", "bbl", "latitude", "longitude"],
)
nj = pd.read_parquet(
    "/data1/apartments/external/registry-nj/20261019-2d485c6/registry.parquet",
    columns=["building", "latitude", "longitude"],
)
s = whitened_zones.sites_of(frame, reg, nj)
# match by coordinates to design.npz order
key = pd.DataFrame({"x": dz["site_x"], "y": dz["site_y"]}).round(6)
key["site"] = np.arange(len(key))
s = (
    s.reset_index()[["building", "x", "y"]]
    .round({"x": 6, "y": 6})
    .merge(key, on=["x", "y"], how="left")
    .drop_duplicates("building")
)
site = frame.building.astype(str).map(s.set_index("building").site).to_numpy()
ok = tr & ~np.isnan(site)
st = site[ok].astype(int)
w = np.bincount(st, minlength=len(key)).astype(float)
names = [
    "log_size_rel",
    "size_imputed",
    "size_unknown",
    "laundry_in_unit",
    "laundry_in_building",
    "dishwasher",
]
has = w > 0
for j, n in enumerate(names):
    m = np.bincount(st, X[ok, j], minlength=len(key))[has] / w[has]
    b = T["bld"][has]
    c = np.cov(m, b, aweights=w[has])
    print(
        f"{n:22s} corr(bld, building mean) = {c[0, 1] / np.sqrt(c[0, 0] * c[1, 1]):+.3f}  slope bld on mean = {c[0, 1] / c[0, 0]:+.4f}"
    )
