"""S8: do buildings with the same manager share a level or move together beyond L1?

The script gives a building a manager where one lister placed at least half of the building's ads in
L1's dataset (five ads or more), `rentfrontier.lister.kind` reads that lister's name as a
management company, and the same lister holds two buildings or more this way. The generic
lister "Owner" is left out. HPD's registration contacts are not on thelio, so the key comes
from the ads alone.

Part A asks whether a manager's other buildings predict a building's held-out gap. The script takes
the cross-fitted shrunk mean of the clipped gap by manager (estimated on the other half of
the buildings, so each building is scored by its manager's buildings in the other half),
score its explained share of the clipped gap, and set it against 50 shuffles of the manager
labels among the managed buildings of each neighbourhood. Then the script rescores L1's predictive
with the shift.

Part B asks whether they move together in the same quarter. From each held-out ad's clipped
gap the script takes off the quarter's citywide mean, then regresses it on the same quantity averaged
over the manager's other buildings in that quarter and over other managers' buildings within
1 km in that quarter, with and without the building's own mean taken off."""

import json

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree

import common as c
from rentfrontier.lister import kind

CLIP = 0.4
f = pq.ParquetFile(c.RECS)
rec = pd.concat(
    f.read_row_group(
        g, columns=["listing_id", "last_collected_at", "lister", "source_type"]
    ).to_pandas()
    for g in range(f.num_row_groups)
)
rec = rec.sort_values("last_collected_at").drop_duplicates("listing_id", keep="last")
d = c.rows()
d["listing_id"] = d.listing_id.astype(str)
d = d.merge(rec[["listing_id", "lister", "source_type"]], on="listing_id", how="left")
del rec

cnt = (
    d[d.lister.notna()].groupby(["building", "lister"]).size().rename("n").reset_index()
)
cnt = cnt.merge(d.groupby("building").size().rename("tot"), on="building")
top = cnt.sort_values("n").drop_duplicates("building", keep="last")
top = top[(top.n >= 0.5 * top.tot) & (top.tot >= 5) & (top.lister != "Owner")]
top = top[
    kind(top.lister, pd.Series("FEED", index=top.index)).eq("management").to_numpy()
]
nb = top.groupby("lister").building.nunique()
top = top[top.lister.isin(nb[nb >= 2].index)]
bm = top.set_index("building").lister
print("managed buildings", len(bm), "managers", bm.nunique(), flush=True)

h = c.heldout(d)
h["mgr"] = h.building.map(bm)
m = h.mgr.notna().to_numpy()
res = {
    "n_heldout": len(h),
    "n_managed_ads": int(m.sum()),
    "managed_buildings": len(bm),
    "managers": int(bm.nunique()),
    "top_managers": bm.value_counts().head(15).to_dict(),
}
g = np.clip(h.gap.to_numpy(), -CLIP, CLIP)
fold, sub = h.fold.to_numpy(), c.subfold(h.building)


def share(shift):
    return 1 - float(((g[m] - shift) ** 2).sum() / ((g[m] - g[m].mean()) ** 2).sum())


s_real, k = c.crossfit_shift(g[m], h.mgr.to_numpy()[m], fold[m], sub[m])
res["A"] = {"explained": share(s_real), "k": k}
# the null: shuffle manager labels among managed buildings in the same neighbourhood
bt = h[m].drop_duplicates("building")[["building", "neighbourhood"]]
rng = np.random.default_rng(8)
null = []
for _ in range(50):
    perm = {}
    for _, grp in bt.groupby("neighbourhood"):
        b = grp.building.to_numpy()
        perm.update(zip(b, bm.reindex(b).to_numpy()[rng.permutation(len(b))]))
    key = h.building[m].map(perm).to_numpy()
    s, _ = c.crossfit_shift(g[m], key, fold[m], sub[m])
    null.append(share(s))
null = np.array(null)
res["A"].update(
    {"null_mean": float(null.mean()), "null_95": float(np.quantile(null, 0.95))}
)
# the same with a neighbourhood shift, for scale
s_nb, _ = c.crossfit_shift(
    g[m], h.neighbourhood.astype(str).to_numpy()[m], fold[m], sub[m]
)
res["A"]["explained_neighbourhood"] = share(s_nb)
dr = c.Draws()
delta = np.zeros(len(h))
delta[m] = s_real
idx = np.flatnonzero(m)
e = dr.gain(idx, delta=delta)
# over a constant shift of the managed ads and over a neighbourhood shift, fitted the same way
for name, s0 in (
    ("constant", c.crossfit_shift(g[m], np.zeros(m.sum()), fold[m], sub[m])[0]),
    ("neighbourhood", s_nb),
):
    delta0 = np.zeros(len(h))
    delta0[m] = s0
    inc = e - dr.gain(idx, delta=delta0)
    res["A"][f"over_{name}"] = [
        float(inc.sum()),
        c.cluster_se(inc, h.building.to_numpy()[idx]),
    ]
res["A"].update(
    {
        "elpd_gain": float(e.sum()),
        "elpd_se": c.cluster_se(e, h.building.to_numpy()[idx]),
    }
)
print("A", json.dumps(res["A"]), flush=True)
del dr

# Part B
h["q"] = h.day.dt.year * 4 + (h.day.dt.month - 1) // 3
h["gq"] = g - pd.Series(g).groupby(h.q.to_numpy()).transform("mean").to_numpy()
reg = pd.read_parquet(
    c.REG, columns=["building", "latitude", "longitude"]
).drop_duplicates("building")
h = h.merge(reg, on="building", how="left")
cell = h.groupby(["building", "q"]).agg(S=("gq", "sum"), N=("gq", "size")).reset_index()
cell["mgr"] = cell.building.map(bm)
mq = cell[cell.mgr.notna()].groupby(["mgr", "q"])[["S", "N"]].sum()
ok = cell.mgr.notna().to_numpy()
tot = mq.reindex(pd.MultiIndex.from_arrays([cell.mgr[ok], cell.q[ok]])).to_numpy()
cell["S_same"] = np.nan
cell["N_same"] = 0.0
cell.loc[ok, "S_same"] = tot[:, 0] - cell.S[ok].to_numpy()
cell.loc[ok, "N_same"] = tot[:, 1] - cell.N[ok].to_numpy()
xy = reg.set_index("building").reindex(cell.building)
lat, lon = xy.latitude.to_numpy(), xy.longitude.to_numpy()
cell["x"] = lon * np.cos(np.radians(40.75)) * 111_320
cell["y"] = lat * 110_540
cell["S_near"] = np.nan
cell["N_near"] = 0.0
for q, grp in cell[np.isfinite(cell.x)].groupby("q"):
    tree = cKDTree(grp[["x", "y"]].to_numpy())
    nbrs = tree.query_ball_point(grp[["x", "y"]].to_numpy(), r=1000)
    S, N, M = grp.S.to_numpy(), grp.N.to_numpy(), grp.mgr.to_numpy()
    sn, nn = np.zeros(len(grp)), np.zeros(len(grp))
    for i, js in enumerate(nbrs):
        js = [j for j in js if j != i and (pd.isna(M[i]) or M[j] != M[i])]
        sn[i], nn[i] = S[js].sum(), N[js].sum()
    cell.loc[grp.index, "S_near"] = sn
    cell.loc[grp.index, "N_near"] = nn
cell["M_same"] = cell.S_same / cell.N_same.where(cell.N_same >= 3)
cell["M_near"] = cell.S_near / cell.N_near.where(cell.N_near >= 10)
h = h.merge(
    cell[["building", "q", "M_same", "M_near"]], on=["building", "q"], how="left"
)


def joint(y, X, b):
    X = np.column_stack([np.ones(len(y))] + list(X))
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    A = np.linalg.inv(X.T @ X)
    sc = pd.DataFrame(X * e[:, None]).groupby(np.asarray(b)).sum().to_numpy()
    V = A @ (sc.T @ sc) @ A
    return [[float(beta[i]), float(np.sqrt(V[i, i]))] for i in range(1, X.shape[1])]


u = h[h.M_same.notna() & h.M_near.notna()].copy()
res["B"] = {"n": len(u), "buildings": int(u.building.nunique())}
res["B"]["raw"] = dict(
    zip(["same", "near"], joint(u.gq.to_numpy(), [u.M_same, u.M_near], u.building))
)
for col in ("gq", "M_same", "M_near"):
    u[col + "_w"] = c.within(u[col], u.building)
multi = u.groupby("building").q.transform("nunique") >= 2
w = u[multi]
res["B"]["within_building"] = dict(
    zip(
        ["same", "near"], joint(w.gq_w.to_numpy(), [w.M_same_w, w.M_near_w], w.building)
    )
)
res["B"]["within_n"] = len(w)
print("B", json.dumps(res["B"]), flush=True)
json.dump(res, open(c.OUT + "s8.json", "w"), indent=1)
