"""Paired held-out comparisons and interval coverage from the per-ad scores of score.py.

    python compare.py DIR

DIR holds floor-latest.npz, mundlak-latest.npz and age-latest.npz. For each pair the
script prints the summed elpd difference with three standard errors:
    row: the plain sd of per-ad differences times sqrt(n),
    building: the sum of differences clustered by building,
    two-way: clustered by building and by listing week (Cameron, Gelbach and Miller 2011),
        V = V_building + V_week - V_building-week.
"""

import sys

import numpy as np

d = {n: np.load(f"{sys.argv[1]}/{n}-latest.npz") for n in ("floor", "mundlak", "age")}


def cluster_var(x, g):
    _, inv = np.unique(g, return_inverse=True)
    s = np.bincount(inv, weights=x - x.mean())
    return (s * s).sum()


def ses(x, building, week):
    bw = np.char.add(np.char.add(building, "|"), week.astype(str))
    vb, vw, vbw = (cluster_var(x, g) for g in (building, week, bw))
    return np.sqrt(len(x) * x.var()), np.sqrt(vb), np.sqrt(max(vb + vw - vbw, vb))


f = d["floor"]
for a, b in (("mundlak", "floor"), ("floor", "age")):
    x = d[a]["elpd"] - d[b]["elpd"]
    r, cb, cw = ses(x, f["building"], f["week"])
    print(
        f"{a} - {b}: elpd {x.sum():.0f}  SE row {r:.0f} building {cb:.0f} two-way {cw:.0f}"
    )
for n, z in d.items():
    y, q = z["y"], z["q"]
    rmse = np.sqrt(np.mean((z["pred"] - y) ** 2))
    cov = []
    for lo, hi in ((3, 4), (2, 5), (1, 6), (0, 7)):
        cov.append(np.mean((y >= q[:, lo]) & (y <= q[:, hi])))
    print(
        f"{n}: elpd {z['elpd'].sum():.0f} RMSE {rmse:.4f} coverage 50/80/90/95",
        " ".join(f"{c:.3f}" for c in cov),
    )
