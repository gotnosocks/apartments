"""Fit 4's within-unit and between-unit coefficients, its scales against fit 8's, and the
coefficients both runs share.

    python unit_coefs.py RUN4 RUN8 OUT.json

For each unit column with a unit mean (`umean:` plus its name) the within coefficient is the
column's own and the between coefficient is the column's plus its mean's, both from the saved
draws of every chain. Binary columns come out as percent premiums, 100 (exp(b) - 1), and the
size term as an elasticity, with each chain's median beside the pooled median.
"""

import json
import sys

import numpy as np

RUNS = "/data1/apartments/frontier/runs/"
r4, r8, out = sys.argv[1:4]
z4, z8 = np.load(RUNS + r4 + "/posterior.npz"), np.load(RUNS + r8 + "/posterior.npz")
n4, n8 = [str(n) for n in z4["names"]], [str(n) for n in z8["names"]]
b4, b8 = z4["kept/beta"].astype(float), z8["kept/beta"].astype(float)


def summ(x, pct):
    """Median and 90% interval over every draw, and each chain's median, of draws (chains, n)."""
    f = (lambda v: 100 * np.expm1(v)) if pct else (lambda v: v)
    q = np.quantile(f(x), [0.05, 0.5, 0.95])
    return {
        "median": q[1],
        "lo": q[0],
        "hi": q[2],
        "chains": np.median(f(x), 1).round(3).tolist(),
    }


res = {"pairs": {}, "shared": {}, "scales": {}}
for c in [n[6:] for n in n4 if n.startswith("umean:")]:
    w, m = b4[..., n4.index(c)], b4[..., n4.index("umean:" + c)]
    pct = c != "unit:log_size_rel"
    res["pairs"][c] = {"within": summ(w, pct), "between": summ(w + m, pct)}
for c in n4:
    if c in n8 and not c.startswith("umean:"):
        a, b = np.median(b4[..., n4.index(c)]), np.median(b8[..., n8.index(c)])
        res["shared"][c] = {"fit4": 100 * a, "fit8": 100 * b, "change": 100 * (a - b)}
for s in ("sigma", "bld_sd", "unit_sd", "nu", "amp", "gp_amp", "gp_ls"):
    if "kept/" + s in z4:
        x4 = z4["kept/" + s].astype(float).reshape(-1, *z4["kept/" + s].shape[2:])
        e = {"fit4": np.median(x4, 0).ravel().tolist()}
        if "kept/" + s in z8:
            x8 = z8["kept/" + s].astype(float).reshape(-1, *z8["kept/" + s].shape[2:])
            e["fit8"] = np.median(x8, 0).ravel().tolist()
        if s == "unit_sd":
            e["q05_q95"] = np.quantile(x4, [0.05, 0.95]).tolist()
        res["scales"][s] = e
json.dump(res, open(out, "w"), indent=1, default=float)
for c, p in res["pairs"].items():
    print(
        f"{c:28s} within {p['within']['median']:7.3f} ({p['within']['lo']:.3f} to {p['within']['hi']:.3f})"
        f"  between {p['between']['median']:7.3f} ({p['between']['lo']:.3f} to {p['between']['hi']:.3f})"
    )
for s, e in res["scales"].items():
    print(s, {k: np.round(v, 4).tolist() for k, v in e.items()})
big = sorted(res["shared"].items(), key=lambda kv: -abs(kv[1]["change"]))[:15]
for c, e in big:
    print(f"{c:40s} {e['fit8']:8.2f} -> {e['fit4']:8.2f} ({e['change']:+.2f})")
