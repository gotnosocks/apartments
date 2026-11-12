import numpy as np, pandas as pd

R = "/data1/apartments/frontier/runs/"
D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
a = np.load(
    R + "drift-building-phase-b0-latest-9a7830fb-l1/pred_scores.npz", allow_pickle=True
)
b = np.load(
    R + "drift-building-b0-latest-ae875fc6-c3ab/pred_scores.npz", allow_pickle=True
)
qs = list(a["quantiles"])
i1, i9 = qs.index(0.1), qs.index(0.9)
held = a["heldout"]
d = pd.read_parquet(
    D,
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "latest_ask",
        "latest_day",
        "bedrooms",
        "full_baths",
    ],
)
assert (b["heldout"] == held).all()
assert (d.listing_id.astype(str).values[held] == a["listing"]).all(), "order"
assert np.allclose(
    np.log(d.latest_ask.values[held].astype(float)), a["y"], atol=1e-4
), "y"
d["ly"] = np.log(d.latest_ask.astype(float))
dd = pd.to_datetime(d.latest_day)
d["mon"] = dd.dt.year * 12 + dd.dt.month
d["held"] = held
# index: monthly mean of log ask over training rows, by bedrooms-free simple mean (repeat-ad index approximated by unit-demeaned change)
t = d[~d.held]
# repeat-ad index: within-unit deviation from unit mean, averaged by month
u = (
    t.assign(dev=t.ly - t.groupby("unit_id").ly.transform("mean"))
    .groupby("mon")
    .dev.mean()
)
idx = (
    u.reindex(range(int(d.mon.min()), int(d.mon.max()) + 1))
    .interpolate()
    .bfill()
    .ffill()
)
t = t.assign(adj=t.ly - idx.reindex(t.mon).values)
h = d[held].reset_index(drop=True)
h["l1"] = a["pred"]
h["c3"] = b["pred"]
h["y"] = a["y"]
for n, z in (("l1", a), ("c3", b)):
    h["lo_" + n] = z["q"][:, i1]
    h["hi_" + n] = z["q"][:, i9]
A = t.groupby(["building", "bedrooms", "mon"]).adj.agg(["sum", "size"]).reset_index()
U = (
    t.groupby(["unit_id", "building", "bedrooms", "mon"])
    .adj.agg(["sum", "size"])
    .reset_index()
)


def win(T, on):
    m = h[["listing_id", "mon", *on]].merge(T.rename(columns={"mon": "mt"}), on=on)
    m = m[(m.mt <= m.mon) & (m.mon - m.mt <= 24)]
    return m.groupby("listing_id")[["sum", "size"]].sum()


aa = win(A, ["building", "bedrooms"])
uu = win(U, ["unit_id", "building", "bedrooms"])
aa = aa.sub(uu.reindex(aa.index).fillna(0))
aa = aa[aa["size"] > 0]
g = pd.DataFrame({"bn": aa["size"], "badj": aa["sum"] / aa["size"]})
x = h.join(g, on="listing_id").dropna(subset=["badj"])
x["bmean"] = x.badj + idx.reindex(x.mon).values

sel = x.listing_id[(x.bmean - x.l1) < -0.15].astype(str)
import json, sys

out = {}
for f in ("h.parquet", "h_time.parquet"):
    try:
        H = pd.read_parquet("/data1/apartments/tmp/sprint-20261112/line-check/" + f)
    except FileNotFoundError:
        continue
    H["listing_id"] = H.listing_id.astype(str)
    m = H.listing_id.isin(set(sel))
    for name in ("building", "bld_bed", "line"):
        z = H[m]
        dl = z["d_" + name]
        e = z.y - z.pred
        out[f + ":" + name] = dict(
            n=int(m.sum()),
            gain=float(z["e_" + name].sum()),
            se=float(
                np.sqrt(
                    z.building.nunique()
                    * z.groupby("building")["e_" + name].sum().var(ddof=1)
                )
            ),
            signed0=float(e.median()),
            signed1=float((e - dl).median()),
            mae0=float(e.abs().median()),
            mae1=float((e - dl).abs().median()),
            cov0=float(((z.y >= z.lo) & (z.y <= z.hi)).mean()),
            cov1=float(z["c_" + name].mean()),
        )
        print(f, name, json.dumps(out[f + ":" + name]), flush=True)
json.dump(
    out,
    open("/data1/apartments/tmp/sprint-20261112/line-check/pricier.json", "w"),
    indent=1,
)
