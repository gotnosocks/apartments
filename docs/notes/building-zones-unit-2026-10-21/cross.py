import json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
import sys

b = pd.read_parquet(sys.argv[1])
bm = pd.read_parquet(
    "/data1/apartments/external/basemap/20261016-5f07157-all/basemap.parquet"
)
s = bm[bm.layer == "street"]
segs = []
W = []
for a, g in zip(s.attributes, s.geometry):
    w = float(json.loads(a).get("streetwidth") or 0)
    for line in json.loads(g)["coordinates"]:
        p = np.array(line)
        p = np.c_[(p[:, 0] + 73.98) * 84.3, (p[:, 1] - 40.75) * 111.0]
        for i in range(len(p) - 1):
            a0, a1 = p[i], p[i + 1]
            L = np.hypot(*(a1 - a0))
            k = max(1, int(np.ceil(L / 0.05)))
            for j in range(k):
                segs.append(np.r_[a0 + (a1 - a0) * j / k, a0 + (a1 - a0) * (j + 1) / k])
                W.append(w)
S = np.array(segs)
W = np.array(W)
print(
    "street pieces",
    len(S),
    "x range",
    S[:, 0].min(),
    S[:, 0].max(),
    "y",
    S[:, 1].min(),
    S[:, 1].max(),
)
print("width quantiles", np.quantile(W[W > 0], [0.25, 0.5, 0.75, 0.9, 0.95]))
# restrict buildings to the basemap's bbox
xy = b[["x", "y"]].to_numpy()
inb = (
    (xy[:, 0] > S[:, 0].min())
    & (xy[:, 0] < S[:, 0].max())
    & (xy[:, 1] > S[:, 1].min())
    & (xy[:, 1] < S[:, 1].max())
)
print("buildings inside bbox", inb.sum(), "zones", b.zone[inb].value_counts().to_dict())


def crosses(P0, P1, S):
    def orient(a, b, c):
        return np.sign(
            (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1])
            - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0])
        )

    A, B, C, D = P0, P1, S[..., :2], S[..., 2:]
    return (orient(A, B, C) != orient(A, B, D)) & (orient(C, D, A) != orient(C, D, B))


q = b[inb & (b.n >= 5)]
X = q[["x", "y"]].to_numpy()
v = q.bld.to_numpy()
nb = q.nb.to_numpy()
P = cKDTree(X).query_pairs(0.2, output_type="ndarray")
rng = np.random.default_rng(1)
P = P[rng.choice(len(P), min(len(P), 300000), replace=False)]
d = np.hypot(*(X[P[:, 0]] - X[P[:, 1]]).T)
P, d = P[d > 0.01], d[d > 0.01]
mid = (X[P[:, 0]] + X[P[:, 1]]) / 2
mids = (S[:, :2] + S[:, 2:]) / 2
T = cKDTree(mids)
wmax = np.zeros(len(P))
for i, (nbrs) in enumerate(T.query_ball_point(mid, d / 2 + 0.03)):
    if not nbrs:
        continue
    nbrs = np.array(nbrs)
    c = crosses(X[P[i, 0]], X[P[i, 1]], S[nbrs])
    if c.any():
        wmax[i] = W[nbrs][c].max()
diff2 = (v[P[:, 0]] - v[P[:, 1]]) ** 2
same = nb[P[:, 0]] == nb[P[:, 1]]
for lo, hi in [(0.01, 0.1), (0.1, 0.2)]:
    m = (d >= lo) & (d < hi)
    for lab, c in [
        ("no street", wmax == 0),
        ("narrow <=40 ft", (wmax > 0) & (wmax <= 40)),
        ("mid 41-70 ft", (wmax > 40) & (wmax <= 70)),
        ("wide >70 ft", wmax > 70),
    ]:
        for sl, sm in [("same nb", same), ("cross nb", ~same)]:
            k = m & c & sm
            if k.sum() > 200:
                print(
                    f"{int(lo * 1000)}-{int(hi * 1000)} m, crossing {lab}, {sl}: pairs {k.sum()}, rms {np.sqrt(diff2[k].mean()):.3f}"
                )
