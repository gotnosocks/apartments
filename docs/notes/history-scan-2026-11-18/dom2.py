"""Days on the market against the place of the FIRST ask, by class of ad, and a scan of ad
words among low-place ads for those tied to slow or fast closings.

The first ask's place comes from the Student-t approximation of calib2.py. For each class,
`gradient` is the mean log days of its ads whose first ask is below the 5% point less that
of its ads between the 25% and 75% points. Ordinary ads show a clear negative gradient
(asks far below prediction close faster). A class with a gradient near zero is one where a
low place does not act like a low price: the model over-predicts those ads."""

import pickle
import sys

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import t as student

sys.path.insert(0, "/data1/apartments/tmp/history-scan")
from rentfrontier.drift_deals import first_net
from scan import stats

ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
DUP = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse/rows.parquet"
run, tag, y0 = sys.argv[1], sys.argv[2], int(sys.argv[3])
DF = 7
h = pd.read_parquet(f"baths-{tag}.parquet")
p = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
q = p["q"].astype(float)
h = h.merge(
    pd.DataFrame(
        {
            "listing_id": p["listing"],
            "pred": p["pred"],
            "y": p["y"],
            "s": (q[:, 4] - q[:, 3]) / (2 * student.ppf(0.75, DF)),
        }
    ),
    on="listing_id",
    validate="1:1",
)
a = pd.read_parquet(
    ADS,
    columns=[
        "listing_id",
        "label_floor",
        "status",
        "first_day",
        "off_day",
        "first_ask",
        "page_price",
        "months_free",
        "latest_ask",
    ],
).drop_duplicates("listing_id")
h = h.merge(a, on="listing_id", how="left")
d = pd.read_parquet(DUP, columns=["listing_id", "duplex"]).drop_duplicates("listing_id")
h = h.merge(d, on="listing_id", how="left")
h = h[h.year >= y0].copy()
h["dom"] = (pd.to_datetime(h.off_day) - pd.to_datetime(h.first_day)).dt.days
free = np.nan_to_num(h.months_free.to_numpy(float)) > 0
final = np.exp(h.y.to_numpy())
first = first_net(
    h.first_ask.to_numpy(float), h.latest_ask.to_numpy(float), h.page_price, free
)
ok = np.isfinite(first) & (first > 0)
print(
    "ads",
    len(h),
    "first ask usable",
    ok.mean().round(3),
    "median final/exp(y)",
    np.nanmedian(h.latest_ask / final).round(4),
)
ratio = np.where(ok, first / h.latest_ask.to_numpy(float), 1.0)
h["cut"] = ratio > 1.001
h["raise_"] = ratio < 0.999
h["zf"] = (h.y + np.log(ratio) - h.pred) / h.s
h["pf"] = student.cdf(h.zf, DF)
h = h[
    h.dom.notna()
    & (h.dom >= 0)
    & (h.dom < 400)
    & h.status.isin(["RENTED", "NO_LONGER_AVAILABLE", "DELISTED"])
].copy()
h["ld"] = np.log1p(h.dom)
print(
    "closed ads",
    len(h),
    "cut",
    h.cut.mean().round(3),
    "raised",
    h.raise_.mean().round(3),
    "first ask below 5%",
    (h.pf < 0.05).mean().round(4),
)
pd.set_option("display.width", 250)
h["p4"] = pd.cut(
    h.pf, [0, 0.05, 0.25, 0.75, 1.0], labels=["low", "5-25", "mid", "high"]
)


def grad(g):
    lo, mid = g[g.p4 == "low"], g[g.p4 == "mid"]
    out = {
        "n": len(g),
        "n low": len(lo),
        "low share": len(lo) / max(len(g), 1),
        "days mid": mid.dom.median(),
        "days low": lo.dom.median(),
        "gradient": lo.ld.mean() - mid.ld.mean(),
        "7d mid": (mid.dom <= 7).mean(),
        "7d low": (lo.dom <= 7).mean(),
        "cut low": lo.cut.mean(),
        "cut mid": mid.cut.mean(),
        "rented low": (lo.status == "RENTED").mean(),
        "rented mid": (mid.status == "RENTED").mean(),
    }
    bl = lo.groupby("building").ld.agg(["sum", "size"])
    out["se"] = np.sqrt(((bl["sum"] - bl["size"] * lo.ld.mean()) ** 2).sum()) / max(
        len(lo), 1
    )
    return pd.Series(out)


h["floor1"] = h.label_floor == 1
h["dup"] = h.duplex.fillna(False).astype(bool)
h["up"] = (h.bedrooms > h.bed_lo) | (h.baths > h.bath_lo)
h["down"] = (h.bedrooms < h.bed_hi) | (h.baths < h.bath_hi)
h["tier"] = h.groupby("year").pred.transform(
    lambda x: pd.qcut(x, [0, 0.25, 0.5, 0.75, 0.9, 0.97, 1], labels=False)
)
plain = h.same & (h.fb == 1) & ~h.floor1 & ~h.dup & (h.tier < 5) & (h.bd < 4)
classes = {
    "all": h.fb >= 0,
    "ordinary": plain,
    "counts above the unit's low": h.up,
    "counts below the unit's high": h.down & ~h.up,
    "2 baths, counts as before": h.same & (h.fb == 2),
    "3+ baths": h.fb >= 3,
    "4+ bedrooms": h.bd >= 4,
    "floor 1": h.floor1,
    "duplex wording": h.dup,
    "top 3% tier": h.tier == 5,
    "months free coded": pd.Series(
        np.nan_to_num(h.months_free.to_numpy(float)) > 0, index=h.index
    ),
    "studio": h.bd == 0,
    "1 bedroom": h.bd == 1,
    "2 bedrooms": h.bd == 2,
    "3 bedrooms": h.bd == 3,
}
rows = {
    f"{k} / half {hf}": grad(h[m & (h.half == hf)])
    for k, m in classes.items()
    for hf in (0, 1)
}
print(pd.DataFrame(rows).T.round(3).to_string())

# Words among low-place ads: log days less the mean of the ad's bedroom group and year.
ads = pd.read_parquet("ads.parquet", columns=["listing_id"])
X = sparse.load_npz("X.npz").tocsr()
terms = pd.read_parquet("terms.parquet", columns=["term"]).term.to_numpy()
pos = pd.Series(np.arange(len(ads)), index=ads.listing_id.astype(str))
low = h[(h.pf < 0.10)].copy()
low["row"] = pos.reindex(low.listing_id.astype(str)).to_numpy()
low = low[low.row.notna()]
low["r"] = low.ld - low.groupby(["bd", "year"]).ld.transform("mean")
out = pd.DataFrame({"term": terms})
for hf, nm in ((0, "a"), (1, "b")):
    g = low[low.half == hf]
    Xg = X[g.row.to_numpy(int)].tocsc()
    n, nb, m, tt, _ = stats(
        Xg, g.r.to_numpy(), np.zeros(len(g), bool), pd.factorize(g.building)[0]
    )
    for c, v in (("n", n), ("bld", nb), ("d", m), ("t", tt)):
        out[f"{c}_{nm}"] = v
    print(f"low-place ads with text, half {nm}: {len(g)}")
out.to_parquet(f"dom-terms-{tag}.parquet")
okk = out[(out.n_a >= 60) & (out.bld_a >= 25)]
for label, asc in (
    ("slow among low-place ads", False),
    ("fast among low-place ads", True),
):
    top = okk.sort_values("t_a", ascending=asc).head(45)
    rep = top[(np.sign(top.t_b) == np.sign(top.t_a)) & (top.t_b.abs() > 2)]
    print(f"\n== {label}: top 45 on half A, {len(rep)} repeat on half B (|t| > 2)")
    print(rep.round(3).to_string(index=False))

# The same gradient for ads holding a word: does a low place act like a low price there?
h["row"] = pos.reindex(h.listing_id.astype(str)).to_numpy()
ht = h[h.row.notna()].copy()
col = {t: i for i, t in enumerate(terms)}
Xc = X.tocsc()
WORDS = [
    "condominium",
    "refundable",
    "processing fee",
    "full service",
    "doorman",
    "concierge",
    "sub zero",
    "miele",
    "rent stabilized",
    "walk up",
    "flights",
    "laundromat",
    "deal",
    "nice",
    "williamsburg",
    "park slope",
]
rows = {}
for w in WORDS:
    if w not in col:
        continue
    has = np.zeros(X.shape[0], bool)
    has[Xc[:, col[w]].indices] = True
    m = has[ht.row.to_numpy(int)]
    for hf in (0, 1):
        g = ht[m & (ht.half == hf)]
        s = grad(g)
        s["res"] = g.res.mean()
        s["final low"] = (g.cdf < 0.05).mean()
        rows[f"{w} / half {hf}"] = s
print("\n== gradient by word (ads with a text)")
print(pd.DataFrame(rows).T.round(3).to_string())
