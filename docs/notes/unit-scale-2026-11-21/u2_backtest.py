"""Free check, part B: bedroom and size scales (U4, U1) on the served design's backtest.

Read with docs/notes/unit-scale-2026-11-21.md ("Amendment"). The final asks of the 9,346 ads
open on 2025-11-10, scored by drift_score.score_run (exact). Each predictive is read as a
Student-t on its median with the scale from its quartiles, the degrees of freedom picked on
the stored elpd; marks scale it by exp(a . x) and shift it by b . x, fitted on one half of
the buildings and scored on the other. Needs rentfrontier (the serve-frontier venv).
"""

import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import minimize
from scipy.stats import t as student

from rentfrontier import drift_deals, drift_score

RUN = Path(
    "/data1/apartments/frontier/runs/"
    "drift-building-bedtext-layout-range-b0-market-d9028c57-range-j"
)
UF = "/data1/apartments/external/unit-features/20261110-ddd2fe8/unit_features.parquet"

frame, h, held = drift_deals._held_frame(RUN)
r = drift_score.score_run(RUN, exact=True)
assert (r["listing"] == h.listing_id.astype(str).to_numpy()).all()
unit_key = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
train_units = set(unit_key[~held & frame.unit_id.notna().to_numpy()])
key = h.building.astype(str) + "|" + h.unit_id.astype(str)
new = (~key.isin(train_units) | h.unit_id.isna()).to_numpy()

ids = sorted(set(h.listing_id.astype(str)))
sz = pq.read_table(
    UF,
    columns=["listing_id", "sqft", "size_source"],
    filters=[("listing_id", "in", ids)],
).to_pandas()
sz["listing_id"] = sz.listing_id.astype(str)
sz = sz.drop_duplicates("listing_id").set_index("listing_id")
sqft = h.listing_id.astype(str).map(sz.sqft).to_numpy(float)
known = (
    h.listing_id.astype(str).map(sz.size_source).fillna("none").ne("none").to_numpy()
)
known = known & np.isfinite(sqft)
Lsz = np.where(known, np.maximum(0, np.log(np.where(known, sqft, 1000) / 1000)), 0.0)

bd = h.bedrooms.to_numpy(float)
res = r["y"] - r["pred"]
q = r["q"].astype(float)
iqr = q[:, 4] - q[:, 3]
elpd = r["elpd"]
bld = h.building.astype(str).to_numpy()
half = np.array([zlib.crc32(b.encode()) % 2 for b in bld])
print("ads", len(h), "; new units", int(new.sum()), "; with a size", int(known.sum()))
print(
    "ads with L > 0:",
    int((Lsz > 0).sum()),
    "; new with L > 0:",
    int((new & (Lsz > 0)).sum()),
)
print("by half:", np.bincount(half).tolist(), "; stored elpd", round(elpd.sum(), 1))

best = None
for dfree in (2, 2.5, 3, 4, 5, 7, 10, 30):
    s0 = iqr / (2 * student.ppf(0.75, dfree))
    gap = abs((student.logpdf(res / s0, dfree) - np.log(s0)).mean() - elpd.mean())
    if best is None or gap < best[0]:
        best = (gap, dfree, s0)
_, DF, S = best
base = student.logpdf(res / S, DF) - np.log(S)
Q90 = student.ppf(0.9, DF)
print("t df, picked on the backtest:", DF, "; t elpd", round(base.sum(), 1))

M = pd.DataFrame(
    {
        "new": new,
        "new, 2 bd": new & (bd == 2),
        "new, 3+ bd": new & (bd >= 3),
        "2 bd": bd == 2,
        "3+ bd": bd >= 3,
        "L": Lsz,
        "new x L": new * Lsz,
    }
).astype(float)
group = np.where(new, "new", "repeat")
group = np.char.add(
    group, np.where(bd >= 3, " 3+ bd", np.where(bd == 2, " 2 bd", " 0-1 bd"))
)


def lp(theta, Z, idx):
    k = Z.shape[1]
    m = np.exp(Z[idx] @ theta[:k])
    d = Z[idx] @ theta[k:]
    return student.logpdf((res[idx] - d) / (S[idx] * m), DF) - np.log(S[idx] * m)


def cluster_se(x):
    g = pd.Series(x).groupby(bld).sum()
    return float(np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum()))


def crossfit(cols, label):
    Z = np.column_stack([np.ones(len(h))] + [M[c].to_numpy() for c in cols])
    per, thetas, cov = np.zeros(len(h)), {}, np.zeros(len(h), bool)
    k = Z.shape[1]
    for f in (0, 1):
        tr, te = np.flatnonzero(half != f), np.flatnonzero(half == f)
        fit = minimize(
            lambda t: -lp(t, Z, tr).sum(), np.zeros(2 * k), method="L-BFGS-B"
        )
        thetas[f] = fit.x
        per[te] = lp(fit.x, Z, te) - base[te]
        m, d = np.exp(Z[te] @ fit.x[:k]), Z[te] @ fit.x[k:]
        cov[te] = np.abs(res[te] - d) < Q90 * S[te] * m
    print(f"\n{label}: cross-fit gain {per.sum():7.1f} (SE {cluster_se(per):5.1f})")
    return per, thetas, cov


def over(per, ref, label):
    d = per - ref
    by = [round(d[half == f].sum(), 1) for f in (0, 1)]
    print(f"  {label}: {d.sum():6.1f} (SE {cluster_se(d):5.1f}); by half", by)
    print("    by group:", pd.Series(d).groupby(group).sum().round(1).to_dict())


def show(th, cols, all_cols):
    # thetas[f] is fitted on half != f: thetas[1] on half 0 (A), thetas[0] on half 1 (B)
    n = len(th[1]) // 2
    for c in cols:
        j = 1 + all_cols.index(c)
        print(
            f"    {c:10} scale (fit on A, on B) {np.exp(th[1][j]):.3f} {np.exp(th[0][j]):.3f};"
            f" shift {th[1][n + j]:+.4f} {th[0][n + j]:+.4f}"
        )


U4 = ["new, 2 bd", "new, 3+ bd"]
BD = ["2 bd", "3+ bd"]
U1 = ["L", "new x L"]
p0, _, c0 = crossfit([], "intercept only")
pr, thr, cr = crossfit(["new"], "reference: intercept + new")
over(pr, p0, "new mark")
show(thr, ["new"], ["new"])
p4, th4, c4 = crossfit(["new"] + U4, "+ U4")
over(p4, pr, "U4 over the reference")
show(th4, U4, ["new"] + U4)
pb, thb, _ = crossfit(["new"] + U4 + BD, "+ U4 + bedroom marks for every ad")
over(pb, p4, "bedroom marks for every ad beside U4")
show(thb, BD, ["new"] + U4 + BD)
p1, th1, c1 = crossfit(["new"] + U4 + U1, "+ U4 + U1")
over(p1, p4, "U1 over U4")
show(th1, U1, ["new"] + U4 + U1)
own = (r["y"] > q[:, 2]) & (r["y"] < q[:, 5])
t = pd.DataFrame(
    {"group": group, "own": own, "t": c0, "ref": cr, "U4": c4, "U4+U1": c1}
)
print("\n80% coverage by group (own: the stored predictive's 10% and 90% quantiles):")
out = t.groupby("group").mean().round(3)
out["ads"] = t.groupby("group").size()
print(out.to_string())
