"""Free check: a predictive width by ad source on l2bt's stored held-out predictions.

See docs/notes/source-width-2026-11-21.md. The scoring and marks of
docs/notes/year-scale-2026-11-21/y2_followup.py, with marks for feed and owner ads (StreetEasy's
source type on the ad's latest stored record; no ask is read). Run from this folder.
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

sys.path.insert(0, "../first-page-read-2026-11-18")
from source import sources  # noqa: E402

CACHE = "/data1/apartments/tmp/first-page-read-2026-11-18/source-b9.parquet"
src = pd.read_parquet(CACHE).source
src.index = src.index.astype(str)
miss = sorted(set(h.listing_id) - set(src.index))
print("held-out ads without a cached source:", len(miss))
if miss:
    extra = sources(miss).source
    extra.index = extra.index.astype(str)
    src = pd.concat([src, extra])
h["source"] = h.listing_id.map(src).fillna("none").to_numpy()
print(h.source.value_counts().to_string())
print("feed share by year:")
print(h.groupby("year").source.apply(lambda s: (s == "FEED").mean()).round(3).to_dict())
T["feed"] = (h.source == "FEED").astype(float)
T["owner"] = (h.source == "OWNER").astype(float)
SRC = ["feed", "owner"]
if (h.source == "none").any():
    T["no source"] = (h.source == "none").astype(float)
    SRC.append("no source")
ALL = pd.concat([X, T], axis=1)
res, half, bld = h.res.to_numpy(), h.half.to_numpy(), h.building.to_numpy()
year, source = h.year.to_numpy(), h.source.to_numpy()
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
    s = pd.Series(d[sel]).groupby(source[sel]).sum().round(1)
    print("    by source:", s.to_dict())


def show(th, cols, k0):
    # thetas[f] is fitted on half != f: thetas[1] on half A (0), thetas[0] on half B (1)
    for i, c in enumerate(cols):
        j = k0 + 1 + i
        n = len(th[1]) // 2
        print(
            f"    {c:10} scale (fit on A, on B) {np.exp(th[1][j]):.3f} {np.exp(th[0][j]):.3f};"
            f" shift {th[1][n + j]:+.4f} {th[0][n + j]:+.4f}"
        )


def coverage(c0, c1, sel, label):
    t = pd.DataFrame({"source": source[sel], "before": c0[sel], "after": c1[sel]})
    print(f"  80% coverage by source, {label}:")
    print(t.groupby("source").mean().round(3).to_string())


xc = list(X.columns)
everyone = np.ones(len(h), bool)
late = year >= 2022
LY = ["2022", "2023", "2025", "2026"]

if "--late-only" not in sys.argv:
    setdf(everyone, "all years")
    py, _, cy = crossfit(xc + YR, "all years: base + year marks", everyone)
    ps, ths, cs = crossfit(xc + YR + SRC, "all years: + source marks", everyone)
    over(ps, py, "source marks over the base and year marks, all years", everyone)
    show(ths, SRC, len(xc) + len(YR))
    coverage(cy, cs, everyone, "all years")

setdf(late, "ads from 2022")
core = xc + GAP + CNT + LY
pg, _, cg = crossfit(core, "from 2022: base + gap bins + counts + year marks", late)
pgs, thgs, cgs = crossfit(core + SRC, "from 2022: + source marks", late)
over(pgs, pg, "source marks over the base, gap, counts and years, from 2022", late)
show(thgs, SRC, len(core))
coverage(cg, cgs, late, "from 2022")
pf, thf, _ = crossfit(core + ["feed"], "from 2022: + feed mark alone", late)
over(pf, pg, "feed mark alone, from 2022", late)
