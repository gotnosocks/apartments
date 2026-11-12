import json, numpy as np, pyarrow.parquet as pq
from rentfrontier.clusterse import cluster_se

R = "/data1/apartments/frontier/runs/"
D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
a = np.load(
    R + "drift-building-phase-b0-latest-9a7830fb-l1/pred_scores.npz", allow_pickle=True
)
b = np.load(
    R + "drift-building-b0-latest-ae875fc6-c3ab/pred_scores.npz", allow_pickle=True
)
assert (a["listing"] == b["listing"]).all() and (a["heldout"] == b["heldout"]).all()
t = pq.read_table(D, columns=["listing_id", "price_at"])
lid = t.column("listing_id").to_numpy()[a["heldout"]]
pa = t.column("price_at").to_numpy()[a["heldout"]]
print("listing match", (lid.astype(str) == a["listing"].astype(str)).mean())
yr = pa.astype("datetime64[Y]").astype(int) + 1970
qs = list(a["quantiles"])


def cov(z, m, lo, hi):
    q = z["q"][m]
    y = z["y"][m]
    return float(((y >= q[:, qs.index(lo)]) & (y <= q[:, qs.index(hi)])).mean())


out = {}
groups = [(str(y), yr == y) for y in range(2014, 2027)] + [
    ("to 2019", yr <= 2019),
    ("2020-22", (yr >= 2020) & (yr <= 2022)),
    ("2023 on", yr >= 2023),
    ("all", yr > 0),
]
for k, m in groups:
    d = a["elpd"][m] - b["elpd"][m]
    r = dict(
        n=int(m.sum()),
        gain=round(float(d.sum()), 1),
        se=round(float(cluster_se(d, a["building"][m])), 1),
    )
    for nm, z in (("l1", a), ("c3", b)):
        r["c50_" + nm] = round(cov(z, m, 0.25, 0.75), 3)
        r["c80_" + nm] = round(cov(z, m, 0.1, 0.9), 3)
        r["c95_" + nm] = round(cov(z, m, 0.025, 0.975), 3)
        r["elpd_" + nm] = round(float(z["elpd"][m].mean()), 4)
    out[k] = r
    print(k, r)
json.dump(
    out, open("/data1/apartments/tmp/sprint-20261112/y1/by_year.json", "w"), indent=1
)
