import json, numpy as np, pandas as pd
from rentfrontier.clusterse import cluster_se

R = "/data1/apartments/frontier/runs/"
a = np.load(
    R + "drift-building-phase-unitt-b0-latest-bc8e7b95-l1t/pred_scores.npz",
    allow_pickle=True,
)
b = np.load(
    R + "drift-building-phase-b0-latest-9a7830fb-l1/pred_scores.npz", allow_pickle=True
)
assert (a["listing"] == b["listing"]).all() and (a["heldout"] == b["heldout"]).all()
qs = list(a["quantiles"])


def stats(z, m):
    q, y = z["q"][m], z["y"][m]
    med = z["pred"][m]
    out = dict(mae=float(np.median(np.abs(y - med))))
    for lab, lo, hi in (("c50", 0.25, 0.75), ("c80", 0.1, 0.9), ("c95", 0.025, 0.975)):
        out[lab] = float(((y >= q[:, qs.index(lo)]) & (y <= q[:, qs.index(hi)])).mean())
    out["above80"] = float((y > q[:, qs.index(0.9)]).mean())
    out["below80"] = float((y < q[:, qs.index(0.1)]).mean())
    out["med_signed"] = float(np.median(y - med))
    return out


t = pd.read_parquet("/data1/apartments/tmp/sprint-20261112/unitlevels/targets.parquet")
lis = pd.Series(np.arange(len(a["listing"])), index=a["listing"].astype(str))
groups = {"all": np.ones(len(a["listing"]), bool)}
for name, sel in (
    ("top200 above", (t.stratum == "top200") & (t.dev > 0)),
    ("top200 below", (t.stratum == "top200") & (t.dev < 0)),
    ("201-2000 above", (t.stratum != "top200") & (t.dev > 0)),
    ("201-2000 below", (t.stratum != "top200") & (t.dev < 0)),
):
    ids = t.loc[sel, "listing_id"].astype(str)
    m = np.zeros(len(a["listing"]), bool)
    m[lis.reindex(ids).dropna().astype(int).values] = True
    groups[name] = m
res = {}
for k, m in groups.items():
    d = a["elpd"][m] - b["elpd"][m]
    res[k] = dict(
        n=int(m.sum()),
        gain=float(d.sum()),
        se=float(cluster_se(d, a["building"][m])),
        l1t=stats(a, m),
        l1=stats(b, m),
    )
    print(k, json.dumps(res[k], default=lambda x: round(x, 4)))
json.dump(
    res, open("/data1/apartments/tmp/sprint-20261112/l1t/pair.json", "w"), indent=1
)
