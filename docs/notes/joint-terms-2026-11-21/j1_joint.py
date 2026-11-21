"""Free check: the queued base-refit terms fitted together on stored l2bt held-out predictions.

The method of `docs/notes/history-scan-2026-11-18/calib2.py`: each held-out predictive is a
Student-t on its median with the scale from its quartiles. Here every ad's scale is
multiplied by exp(a . x) and its centre moved by b . x, with x the queued marks, all at once.
a and b are fitted on one half of the buildings and scored on the other, both ways. An
intercept-only fit (one scale, one shift for every ad) is the control: the terms' gain is the
full fit's gain over it. Each mark reads coded fields or text, never the ask.
"""

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import minimize
from scipy.stats import t as student

HS = "/data1/apartments/tmp/history-scan/baths-l2bt.parquet"
RUN = "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"
SNAP = "/data1/apartments/external/unit-floor/20261021-d84914c0/floor.parquet"
DUP = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse/rows.parquet"
)
MARKS = "/data1/apartments/tmp/large-units/l8_marks.parquet"
Y0 = 2022

h = pd.read_parquet(HS)
p = np.load(f"/data1/apartments/frontier/runs/{RUN}/pred_scores.npz", allow_pickle=True)
q = p["q"].astype(float)
sc = pd.DataFrame(
    {
        "listing_id": p["listing"],
        "elpd": p["elpd"],
        "pred": p["pred"],
        "iqr": q[:, 4] - q[:, 3],
    }
)
h = h.merge(sc, on="listing_id", validate="1:1")
ids = sorted(set(h.listing_id))
fl = pq.read_table(SNAP, filters=[("listing_id", "in", ids)]).to_pandas()
fl = fl.drop_duplicates("listing_id")[["listing_id", "floor"]]
dup = pq.read_table(
    DUP, columns=["listing_id", "duplex"], filters=[("listing_id", "in", ids)]
)
dup = dup.to_pandas().groupby("listing_id", as_index=False).duplex.max()
mk = pd.read_parquet(MARKS)[["listing_id", "spec"]]
h = h.merge(fl, on="listing_id", how="left").merge(dup, on="listing_id", how="left")
h = h.merge(mk, on="listing_id", how="left")
# the building's finish share among its other held-out ads (all years), 4 or more ads
g = h.groupby("building").spec
n, s = g.transform("size"), g.transform(lambda v: v.fillna(False).astype(int).sum())
h["share"] = ((s - h.spec.fillna(False).astype(int)) / (n - 1)).where(n >= 4)
h["tier"] = h.groupby("year").pred.transform(lambda x: x.rank(pct=True))
h = h[h.year >= Y0].reset_index(drop=True)

big = h.bd >= 3
X = pd.DataFrame(
    {
        "changed counts": ~h.same,
        "changed, 2 baths": ~h.same & (h.fb == 2),
        "3+ baths": h.fb >= 3,
        "2 baths": h.fb == 2,
        "4+ bedrooms": h.bd >= 4,
        "top 3% predicted": h.tier > 0.97,
        "floor 1": h.floor == 1,
        "duplex": h.duplex.fillna(False).astype(bool),
        "3+ bed, finish share": big * h.share.fillna(0),
        "3+ bed, share 0": big & (h.share == 0),
    }
).astype(float)
print("ads", len(h), "from", Y0, "; marked shares:")
print(X.mean().round(4).to_string())

best = None
for dfree in (2, 2.5, 3, 4, 5, 7, 10, 30):
    s0 = h.iqr / (2 * student.ppf(0.75, dfree))
    lp = student.logpdf(h.res / s0, dfree) - np.log(s0)
    if best is None or abs(lp.mean() - h.elpd.mean()) < best[0]:
        best = (abs(lp.mean() - h.elpd.mean()), dfree, s0.to_numpy())
_, DF, S = best
print("t df", DF)
res, cdf, half, bld = (
    h.res.to_numpy(),
    h.cdf.to_numpy(),
    h.half.to_numpy(),
    h.building.to_numpy(),
)
base = student.logpdf(res / S, DF) - np.log(S)


def lp(theta, Z, idx):
    k = Z.shape[1]
    a, b = theta[:k], theta[k:]
    m = np.exp(Z[idx] @ a)
    d = Z[idx] @ b
    return student.logpdf((res[idx] - d) / (S[idx] * m), DF) - np.log(S[idx] * m)


def crossfit(cols, label):
    Z = np.column_stack([np.ones(len(h))] + [X[c].to_numpy() for c in cols])
    per, thetas = np.zeros(len(h)), {}
    for f in (0, 1):
        tr, te = np.flatnonzero(half != f), np.flatnonzero(half == f)
        r = minimize(
            lambda t: -lp(t, Z, tr).sum(), np.zeros(2 * Z.shape[1]), method="L-BFGS-B"
        )
        thetas[f] = r.x
        per[te] = lp(r.x, Z, te) - base[te]
    g = pd.Series(per).groupby(bld).sum()
    se = float(np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum()))
    print(f"\n{label}: cross-fit gain {per.sum():8.1f} (SE {se:5.1f})")
    return per, thetas, Z


per0, _, _ = crossfit([], "intercept only (one scale, one shift)")
cols = list(X.columns)
per1, th, Z = crossfit(cols, "all terms")
d = per1 - per0
g = pd.Series(d).groupby(bld).sum()
se = float(np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum()))
print(
    f"terms over intercept: {d.sum():8.1f} (SE {se:5.1f}); by half",
    [round(d[half == f].sum(), 1) for f in (0, 1)],
)
k = Z.shape[1]
tab = pd.DataFrame(
    {
        "scale x (fit on B)": np.exp(th[1][:k]),
        "scale x (fit on A)": np.exp(th[0][:k]),
        "shift (fit on B)": th[1][k:],
        "shift (fit on A)": th[0][k:],
    },
    index=["intercept"] + cols,
).round(3)
print(tab.to_string())

# leave one term out: what each adds beside the others
print("\nleave one out (gain lost when the term is dropped):")
for c in cols:
    pl, _, _ = crossfit([x for x in cols if x != c], f"  without {c}")
    print(f"    lost {(per1 - pl).sum():7.1f}")

# the low tail after the joint adjustment, each ad scored with the other half's fit
mz = np.empty(len(h))
dz = np.empty(len(h))
for f in (0, 1):
    te = half == f
    mz[te] = np.exp(Z[te] @ th[1 - f][:k])
    dz[te] = Z[te] @ th[1 - f][k:]
mz0 = np.empty(len(h))
dz0 = np.empty(len(h))
Z0 = np.ones((len(h), 1))
for f in (0, 1):
    tr = np.flatnonzero(half != f)
    r = minimize(lambda t: -lp(t, Z0, tr).sum(), np.zeros(2), method="L-BFGS-B")
    te = half == f
    mz0[te], dz0[te] = np.exp(r.x[0]), r.x[1]
c0 = student.cdf((res - dz0) / (S * mz0), DF)
c1 = student.cdf((res - dz) / (S * mz), DF)
low0, low1 = c0 < 0.05, c1 < 0.05
print(
    f"\nlow tail (below 5%), intercept-only {low0.sum()}, all terms {low1.sum()}, "
    f"left {(low0 & ~low1).sum()}, joined {(~low0 & low1).sum()}"
)
for c in cols:
    on = X[c].to_numpy() > 0
    print(
        f"  {c:22} marked {on.sum():6}  low {low0[on].sum():5} -> {low1[on].sum():5}"
        f"  ({100 * low0[on].mean():4.1f}% -> {100 * low1[on].mean():4.1f}%)"
    )
