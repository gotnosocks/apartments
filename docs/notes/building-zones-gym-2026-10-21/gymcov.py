import numpy as np, pandas as pd
from rentfrontier import b0, splits, building_zones_unit as bzu

frame = b0.load_frame(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
held = splits.SPLITS["latest"](frame)
t = bzu.subset(bzu.design(frame), ~held)
nm = list(t.names)
g = pd.read_parquet(
    "/data1/apartments/external/building-gym/20261021-752c7d3d/gym.parquet"
).set_index("building")
b = frame.building.astype(str)[~held].reset_index(drop=True)
gym = b.map(g.gym).fillna(0).to_numpy()
unk = b.map(g.gym_unknown).fillna(1).to_numpy()
sh = b.map(g.gym_share)
print(
    "ads",
    len(b),
    "gym",
    gym.mean().round(4),
    "unknown",
    unk.mean().round(4),
    "missing from table",
    b.map(g.gym).isna().mean().round(4),
)
print(
    "ads in buildings with split vote (0<share<1)",
    ((sh > 0) & (sh < 1)).mean().round(4),
    "share in [0.3,0.7]",
    ((sh >= 0.3) & (sh <= 0.7)).mean().round(4),
)
lab = np.where(unk == 1, "unknown", np.where(gym == 1, "gym", "no gym"))
X = pd.DataFrame({n: t.x[:, nm.index(n)] for n in nm if n.startswith("bld:")})
X["zone"] = (
    np.where(frame.borough[~held].to_numpy() == "Manhattan", "M", "BK+Q")
    if "borough" in frame
    else 0
)
for c in [
    "bld:doorman_full",
    "bld:doorman_part",
    "bld:doorman_virtual",
    "bld:elevator",
    "bld:condo",
]:
    print(
        pd.crosstab(lab, X[c] > 0, normalize="index")
        .round(3)
        .rename(columns={False: "no", True: c})
        .iloc[:, -1:]
        .T.to_string()
    )
print(pd.Series(lab).value_counts())
print(pd.crosstab(lab, X["zone"]))
