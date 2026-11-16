"""L2 (l2kn) against served b9 on matched held-out ads. Usage: cmp.py WORKERS"""

import sys, zlib
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from rentfrontier import drift_score as ds

R = Path("/data1/apartments/frontier/runs")
L2 = R / "drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn"
B9 = R / "drift-building-b0-latest-67d14e17-b9"
OUT = Path("/data1/apartments/tmp/l2-vs-b9")
SH = Path("/data1/apartments/tmp/sprint-20261114/shift-" + L2.name + ".npy")


def shifted_b9(workers):
    f = OUT / "shift-b9.npy"
    if f.exists():
        return np.load(f)
    z = np.load(B9 / "posterior.npz")
    s = np.load(B9 / "pred_scores.npz")
    flat = lambda k: z["kept/" + k].reshape(-1, *z["kept/" + k].shape[2:])
    global G
    loc, usd, sig, nu = (
        flat("pred_loc"),
        flat("pred_unit_sd"),
        flat("sigma"),
        flat("nu"),
    )
    y, group = z["kept/pred_y"], z["kept/pred_group"]
    half = np.array([zlib.crc32(b.encode()) % 2 for b in s["building"]])
    gap = s["y"] - s["pred"]
    c = np.where(half == 0, np.median(gap[half == 1]), np.median(gap[half == 0]))
    G = (loc, usd, sig, nu, y - c, group)
    with Pool(workers) as pool:
        done = dict(pool.imap_unordered(one, range(0, len(y), ds.CHUNK), chunksize=4))
    e = np.concatenate([done[a] for a in sorted(done)])
    np.save(f, e)
    print("b9 shifts", np.unique(c))
    return e


def one(a):
    loc, usd, sig, nu, ys, group = G
    sl = slice(a, a + ds.CHUNK)
    return a, ds.score_rows(loc[:, sl], usd[:, sl], sig[:, group[sl]], nu, ys[sl], a)[
        "elpd"
    ]


def cl(d, b):
    u, inv = np.unique(b, return_inverse=True)
    t = np.bincount(inv, d)
    n = len(u)
    return d.sum(), np.sqrt(n / (n - 1) * ((t - t.mean()) ** 2).sum())


if __name__ == "__main__":
    a, b = np.load(L2 / "pred_scores.npz"), np.load(B9 / "pred_scores.npz")
    la, lb = a["listing"], b["listing"]
    print("n L2", len(la), "n b9", len(lb), "unique", len(set(la)), len(set(lb)))
    print("L2 only", len(set(la) - set(lb)), "b9 only", len(set(lb) - set(la)))
    com, ia, ib = np.intersect1d(la, lb, return_indices=True)
    print(
        "matched",
        len(com),
        "same day",
        (a["day"][ia] == b["day"][ib]).mean(),
        "same building",
        (a["building"][ia] == b["building"][ib]).mean(),
    )
    dy = a["y"][ia] - b["y"][ib]
    mm = np.abs(dy) > 1e-9
    print(
        "y mismatches",
        mm.sum(),
        "dy quantiles",
        np.quantile(dy[mm], [0, 0.1, 0.5, 0.9, 1]) if mm.any() else "",
    )
    if mm.any():
        r = np.exp(-dy[mm])
        print("b9/L2 ask ratios (top)", np.unique(np.round(r, 4), return_counts=True))
    bld = a["building"][ia]
    d = a["elpd"][ia] - b["elpd"][ib]
    for name, keep in [("all matched", np.ones(len(ia), bool)), ("y agree", ~mm)]:
        s_, se = cl(d[keep], bld[keep])
        print(name, keep.sum(), "dElpd %.1f SE %.1f z %.1f" % (s_, se, s_ / se))
    ea_s = np.load(SH)
    eb_s = shifted_b9(int(sys.argv[1]))
    ds_ = ea_s[ia] - eb_s[ib]
    for name, keep in [
        ("shifted all", np.ones(len(ia), bool)),
        ("shifted y agree", ~mm),
    ]:
        s_, se = cl(ds_[keep], bld[keep])
        print(name, "dElpd %.1f SE %.1f z %.1f" % (s_, se, s_ / se))
    print(
        "elpd sums L2 %.1f b9 %.1f; shifted L2 %.1f b9 %.1f"
        % (a["elpd"][ia].sum(), b["elpd"][ib].sum(), ea_s[ia].sum(), eb_s[ib].sum())
    )
    qs = list(a["quantiles"])
    for nm, s, ix in [("L2", a, ia), ("b9", b, ib)]:
        y, q = s["y"][ix], s["q"][ix]
        cov = lambda lo, hi: (
            (y >= q[:, qs.index(lo)]) & (y <= q[:, qs.index(hi)])
        ).mean()
        print(
            nm,
            "MAE %.4f cov80 %.4f cov95 %.4f cdf<0.01 %d"
            % (
                np.median(np.abs(y - s["pred"][ix])),
                cov(0.1, 0.9),
                cov(0.025, 0.975),
                (s["cdf"][ix] < 0.01).sum(),
            ),
        )
    print("quantiles", qs)
    ta, tb = a["cdf"][ia] < 0.01, b["cdf"][ib] < 0.01
    print(
        "cdf<0.01 overlap",
        (ta & tb).sum(),
        "L2 only",
        (ta & ~tb).sum(),
        "b9 only",
        (tb & ~ta).sum(),
    )
    print("cdf<0.01 among y mismatches: L2", (ta & mm).sum(), "b9", (tb & mm).sum())
