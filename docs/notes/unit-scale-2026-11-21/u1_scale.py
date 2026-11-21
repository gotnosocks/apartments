"""Free check, part A: bedroom and size scales (U4, U1) on l2bt's stored predictions.

Read with docs/notes/unit-scale-2026-11-21.md. The scoring and marks of
docs/notes/source-width-2026-11-21/s1_source.py, with marks by bedroom count and for size
over 1,000 sq ft. The latest split holds out re-listed units only, so no ad is of a new
unit. Run from this folder.
"""

import sys

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
FLAGS = "/data1/apartments/tmp/outlier-sprint/qual/flags.parquet"
DATA = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet"
)

h = pd.read_parquet(HS)
h["listing_id"] = h.listing_id.astype(str)
p = np.load(f"/data1/apartments/frontier/runs/{RUN}/pred_scores.npz", allow_pickle=True)
q = p["q"].astype(float)
sc = pd.DataFrame(
    {
        "listing_id": p["listing"].astype(str),
        "elpd": p["elpd"],
        "pred": p["pred"],
        "iqr": q[:, 4] - q[:, 3],
    }
)
h = h.merge(sc, on="listing_id", validate="1:1")
ids = sorted(set(h.listing_id))


def table(path, cols=None):
    t = pq.read_table(
        path, columns=cols, filters=[("listing_id", "in", ids)]
    ).to_pandas()
    t["listing_id"] = t.listing_id.astype(str)
    return t


fl = table(SNAP).drop_duplicates("listing_id")[["listing_id", "floor"]]
dup = (
    table(DUP, ["listing_id", "duplex"])
    .groupby("listing_id", as_index=False)
    .duplex.max()
)
mk = pd.read_parquet(MARKS)[["listing_id", "spec"]]
mk["listing_id"] = mk.listing_id.astype(str)
u = pd.read_parquet(DATA, columns=["listing_id", "unit_id", "price_at"])
u["listing_id"] = u.listing_id.astype(str)
FL = [c for c in pq.read_schema(FLAGS).names if c not in ("listing_id", "desc_len")]
print("text flags", len(FL))
w = pd.read_parquet(FLAGS, columns=["listing_id", "desc_len", *FL])
w["listing_id"] = w.listing_id.astype(str)
w = w.drop_duplicates("listing_id")
u = u.merge(w, on="listing_id", how="left", validate="1:1")
print("dataset ads", len(u), "; no flags row:", u.renovated.isna().sum())
u = u.sort_values(["unit_id", "price_at", "listing_id"]).reset_index(drop=True)
has = u.renovated.notna()
F = u[FL].fillna(False).astype(bool)
P = F.groupby(u.unit_id).shift(1)
prev_has = has.groupby(u.unit_id).shift(1).fillna(False).astype(bool)
ok = has & prev_has
u["nflip"] = (F != P.fillna(False).astype(bool)).sum(axis=1).where(ok)
W = F.renovated | F.gut
pW = W.groupby(u.unit_id).shift(1)
u["switch"] = W & prev_has & (pW == False)  # noqa: E712
u["gap"] = pd.to_datetime(u.price_at, utc=True).groupby(u.unit_id).diff().dt.days
u["plen"] = u.groupby("unit_id").desc_len.shift(1)
dw = P.dishwasher.fillna(True).astype(bool)
u["dishwasher on"] = F.dishwasher & ~dw & prev_has
rv = u[["listing_id", "nflip", "switch", "dishwasher on", "gap", "desc_len", "plen"]]
for t in (fl, dup, mk, rv):
    h = h.merge(t, on="listing_id", how="left")
g = h.groupby("building").spec
n, s = g.transform("size"), g.transform(lambda v: v.fillna(False).astype(int).sum())
h["share"] = ((s - h.spec.fillna(False).astype(int)) / (n - 1)).where(n >= 4)
h["tier"] = h.groupby("year").pred.transform(lambda x: x.rank(pct=True))
h = h.reset_index(drop=True)

big = h.bd >= 3
X = pd.DataFrame(
    {
        "changed counts": ~h.same,
        "changed, 2 baths": ~h.same & (h.fb == 2),
        "3+ baths": h.fb >= 3,
        "2 baths": h.fb == 2,
        "top 3% predicted": h.tier > 0.97,
        "floor 1": h.floor == 1,
        "duplex": h.duplex.fillna(False).astype(bool),
        "3+ bed, finish share": big * h.share.fillna(0),
    }
).astype(float)
YR = ["2014-19", "2020", "2021", "2022", "2023", "2025", "2026"]
T = pd.DataFrame(
    {
        "2014-19": h.year <= 2019,
        **{y: h.year == int(y) for y in YR[1:]},
        "gap 180-364 d": h.gap.between(180, 364),
        "gap 1-2 y": h.gap.between(365, 729),
        "gap 2-4 y": h.gap.between(730, 1460),
        "gap 4+ y": h.gap > 1460,
        "1 flag changed": h.nflip == 1,
        "2 changed": h.nflip == 2,
        "3+ changed": h.nflip >= 3,
    }
).astype(float)
GAP = ["gap 180-364 d", "gap 1-2 y", "gap 2-4 y", "gap 4+ y"]
CNT = ["1 flag changed", "2 changed", "3+ changed"]

UF = "/data1/apartments/external/unit-features/20261021-16cea7c/unit_features.parquet"
sz = table(UF, ["listing_id", "sqft", "size_source"]).drop_duplicates("listing_id")
h = h.merge(sz, on="listing_id", how="left", validate="m:1")
known = h.size_source.fillna("none").ne("none") & h.sqft.notna()
new = h.gap.isna()
print(
    "held-out ads",
    len(h),
    "; new units",
    int(new.sum()),
    "; with a size",
    int(known.sum()),
)
print(
    "new-unit share by year:",
    h.groupby("year").gap.apply(lambda g: g.isna().mean()).round(3).to_dict(),
)
Lsz = np.where(known, np.maximum(0, np.log(h.sqft.where(known, 1000) / 1000)), 0.0)
print(
    "ads with L > 0:",
    int((Lsz > 0).sum()),
    "; mean L there",
    round(Lsz[Lsz > 0].mean(), 3),
)
bd2, bd3 = h.bd == 2, h.bd >= 3
T["2 bd"] = bd2.astype(float)
T["3+ bd"] = bd3.astype(float)
T["L"] = Lsz
BD = ["2 bd", "3+ bd"]
ALL = pd.concat([X, T], axis=1)
res, half, bld = h.res.to_numpy(), h.half.to_numpy(), h.building.to_numpy()
year = h.year.to_numpy()
group = np.where(h.bd >= 3, "3+ bd", np.where(h.bd == 2, "2 bd", "0-1 bd"))
group = np.char.add(group.astype(str), np.where(Lsz > 0, ", over 1,000 sq ft", ""))
G = {}


def setdf(sel, label):
    best = None
    for dfree in (2, 2.5, 3, 4, 5, 7, 10, 30):
        s0 = h.iqr / (2 * student.ppf(0.75, dfree))
        lp0 = student.logpdf(h.res / s0, dfree) - np.log(s0)
        gap = abs(lp0[sel].mean() - h.elpd[sel].mean())
        if best is None or gap < best[0]:
            best = (gap, dfree, s0.to_numpy())
    _, G["DF"], G["S"] = best
    G["base"] = student.logpdf(res / G["S"], G["DF"]) - np.log(G["S"])
    G["Q90"] = student.ppf(0.9, G["DF"])
    print(f"\nt df, picked on {label}: {G['DF']}")


def lp(theta, Z, idx):
    k, S, DF = Z.shape[1], G["S"], G["DF"]
    m = np.exp(Z[idx] @ theta[:k])
    d = Z[idx] @ theta[k:]
    return student.logpdf((res[idx] - d) / (S[idx] * m), DF) - np.log(S[idx] * m)


def cluster_se(x, sel):
    g = pd.Series(x[sel]).groupby(bld[sel]).sum()
    return float(np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum()))


def crossfit(cols, label, sel):
    """Fit on one half of the buildings within sel, score on the other."""
    Z = np.column_stack([np.ones(len(h))] + [ALL[c].to_numpy() for c in cols])
    per, thetas, cov = np.zeros(len(h)), {}, np.zeros(len(h), bool)
    S, k = G["S"], Z.shape[1]
    for f in (0, 1):
        tr = np.flatnonzero(sel & (half != f))
        te = np.flatnonzero(sel & (half == f))
        r = minimize(lambda t: -lp(t, Z, tr).sum(), np.zeros(2 * k), method="L-BFGS-B")
        thetas[f] = r.x
        per[te] = lp(r.x, Z, te) - G["base"][te]
        m, d = np.exp(Z[te] @ r.x[:k]), Z[te] @ r.x[k:]
        cov[te] = np.abs(res[te] - d) < G["Q90"] * S[te] * m
    print(f"{label}: cross-fit gain {per.sum():8.1f} (SE {cluster_se(per, sel):5.1f})")
    return per, thetas, cov


def over(per, ref, label, sel):
    d = per - ref
    by = [round(d[sel & (half == f)].sum(), 1) for f in (0, 1)]
    print(f"  {label}: {d.sum():7.1f} (SE {cluster_se(d, sel):5.1f}); by half", by)
    s = pd.Series(d[sel]).groupby(group[sel]).sum().round(1)
    print("    by group:", s.to_dict())


def show(th, cols, all_cols):
    # thetas[f] is fitted on half != f: thetas[1] on half A (0), thetas[0] on half B (1)
    n = len(th[1]) // 2
    for c in cols:
        j = 1 + all_cols.index(c)
        print(
            f"    {c:10} scale (fit on A, on B) {np.exp(th[1][j]):.3f} {np.exp(th[0][j]):.3f};"
            f" shift {th[1][n + j]:+.4f} {th[0][n + j]:+.4f}"
        )


def coverage(cs, sel, label):
    t = pd.DataFrame({"group": group[sel], **{k: v[sel] for k, v in cs.items()}})
    print(f"  80% coverage by group, {label}:")
    t = t.groupby("group").mean()
    t["ads"] = pd.Series(group[sel]).value_counts()
    print(t.round(3).to_string())


def readings(core, sel, label):
    pr, _, cr = crossfit(core, f"{label}: reference", sel)
    pb, thb, cb = crossfit(core + BD, f"{label}: + bedroom marks for every ad", sel)
    over(pb, pr, f"bedroom marks over the reference, {label}", sel)
    show(thb, BD, core + BD)
    pl, thl, cl = crossfit(core + ["L"], f"{label}: + L", sel)
    over(pl, pr, f"L over the reference, {label}", sel)
    show(thl, ["L"], core + ["L"])
    coverage({"reference": cr, "+ bedrooms": cb, "+ L": cl}, sel, label)


xc = list(X.columns)
late = year >= 2022
LY = ["2022", "2023", "2025", "2026"]
setdf(late, "ads from 2022")
readings(xc + GAP + CNT + LY, late, "from 2022")
if "--late-only" not in sys.argv:
    everyone = np.ones(len(h), bool)
    setdf(everyone, "all years")
    readings(xc + YR, everyone, "all years")
