"""Paired held-out comparisons and interval coverage from the per-ad scores of score.py.

    python compare.py DIR [A:B ...]

DIR holds NAME-latest.npz for each named run. With no pairs given, the script compares
mundlak:floor and floor:age. For each pair A:B it keeps the held-out ads both files list,
which are all of them when both runs come from the same build, then prints the summed elpd difference with three standard errors:
    row: the plain sd of per-ad differences times sqrt(n),
    building: the sum of differences clustered by building,
    two-way: clustered by building and by listing week (Cameron, Gelbach and Miller 2011),
        V = V_building + V_week - V_building-week, floored at V_building when the
        difference comes out smaller.
"""

import sys

import numpy as np

pairs = [a.split(":") for a in sys.argv[2:]] or [["mundlak", "floor"], ["floor", "age"]]
names = dict.fromkeys(n for pair in pairs for n in pair)
d = {n: np.load(f"{sys.argv[1]}/{n}-latest.npz") for n in names}


def cluster_var(x, g):
    _, inv = np.unique(g, return_inverse=True)
    s = np.bincount(inv, weights=x - x.mean())
    return (s * s).sum()


def ses(x, building, week):
    bw = np.char.add(np.char.add(building, "|"), week.astype(str))
    vb, vw, vbw = (cluster_var(x, g) for g in (building, week, bw))
    return np.sqrt(len(x) * x.var()), np.sqrt(vb), np.sqrt(max(vb + vw - vbw, vb))


for a, b in pairs:
    la, lb = d[a]["listing"], d[b]["listing"]
    assert len(np.unique(la)) == len(la) and len(np.unique(lb)) == len(lb)
    _, ia, ib = np.intersect1d(la, lb, assume_unique=True, return_indices=True)
    x = d[a]["elpd"][ia] - d[b]["elpd"][ib]
    r, cb, cw = ses(x, d[b]["building"][ib], d[b]["week"][ib])
    print(
        f"{a} - {b}: elpd {x.sum():.0f}  SE row {r:.0f} building {cb:.0f} two-way {cw:.0f}"
        f"  on {len(x)} shared ads ({len(la) - len(x)} only in {a}, {len(lb) - len(x)} only in {b})"
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
