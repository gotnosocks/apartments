import json, numpy as np, pandas as pd

a = pd.read_parquet(
    "/data1/apartments/tmp/resid/resid_attrs.parquet",
    columns=["building", "F", "zone", "bld"],
)
u = pd.read_parquet("resid_unit.parquet", columns=["building", "F", "bld"])
z = np.load(
    "/data1/apartments/frontier/runs/building-zones-unit-b0-latest-a3aec3ff-dense-w650/posterior.npz"
)
rows = pd.read_parquet(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc/rows.parquet",
    columns=["neighbourhood"],
)[~z["heldout"]].reset_index(drop=True)
d = pd.DataFrame(
    {
        "nb": rows.neighbourhood,
        "zone": a.zone,
        "Fb": a.F,
        "Fa": u.F,
        "db": a.bld,
        "da": u.bld,
    }
)
for c in ["Fb", "Fa"]:
    d[c] -= d.groupby("zone")[c].transform("mean")
g = (
    d.groupby(["zone", "nb"])
    .agg(
        ads=("Fa", "size"),
        before=("Fb", "mean"),
        after=("Fa", "mean"),
        d_before=("db", "mean"),
        d_after=("da", "mean"),
    )
    .reset_index()
)
g["move"] = g.after - g.before
g = g[g.ads >= 2000].sort_values("move")
pd.set_option("display.width", 200)
print(g.head(10).round(3).to_string())
print(g.tail(10).round(3).to_string())
print("rms move over ads", np.sqrt(((d.Fa - d.Fb) ** 2).mean()).round(4))
json.dump(
    {
        "note": "map value F at the training ads, posterior mean, demeaned within zone; neighborhoods with at least 2,000 training ads; move = after - before, log scale",
        "rms_move": float(np.sqrt(((d.Fa - d.Fb) ** 2).mean())),
        "down": g.head(10).round(4).to_dict("records"),
        "up": g.tail(10).round(4).to_dict("records"),
    },
    open("mapmove.json", "w"),
)
