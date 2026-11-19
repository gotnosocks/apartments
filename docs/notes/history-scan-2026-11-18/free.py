"""Days on the market against the place of the first ask for ads with coded free months,
split by how busy the building was (a lease-up proxy) and by the months offered.

The frame and `grad` are those of dom2.py. `bld_opened_730` counts other units' ads of the
building opened in the two years before the ad."""

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


T = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-turnover/rows.parquet"
u = pd.read_parquet(T, columns=["listing_id", "bld_opened_730", "res_units_asof"])
h = h.merge(u.drop_duplicates("listing_id"), on="listing_id", how="left")
h["free"] = np.nan_to_num(h.months_free.to_numpy(float))
h["busy"] = pd.cut(
    h.bld_opened_730, [-1, 9, 49, 199, 10**6], labels=["0-9", "10-49", "50-199", "200+"]
)
h["offer"] = pd.cut(
    h.free, [-1, 0, 1, 2, 99], labels=["none", "up to 1", "1 to 2", "over 2"]
)
print("with turnover column", h.bld_opened_730.notna().mean().round(3))
for name, mask in {"free months": h.free > 0, "no free months": h.free == 0}.items():
    print(name)
    print(h[mask].groupby("busy", observed=True).apply(grad).round(3).to_string())
print("by months offered")
print(h.groupby("offer", observed=True).apply(grad).round(3).to_string())
print("free months, by half of buildings and busy 50+")
h["big"] = h.bld_opened_730 >= 50
print(h[h.free > 0].groupby(["big", "half"]).apply(grad).round(3).to_string())

# Gross against net: rank free-month ads by the gap of the page (gross) rent and by the gap
# of the net ask, each within free-month ads, and compare the gradients.
f = h[(h.free > 0) & (h.page_price > 0)].copy()
# The ads table's latest ask is gross for these ads; the fit's target `y` is the net ask.
f["conc"] = np.log(f.page_price) - f.y
f = f[(f.conc > 0.005) & (f.conc < 0.7)].copy()
f["net_gap"] = f.zf
f["gross_gap"] = f.zf + f.conc / f.s
print(
    "free-month ads with a usable page rent",
    len(f),
    "median concession",
    f.conc.median().round(3),
)
print("corr net gap, gross gap", np.corrcoef(f.net_gap, f.gross_gap)[0, 1].round(3))


def by_rank(g, col):
    r = g[col].rank(pct=True)
    lo, mid = g[r < 0.1], g[(r > 0.25) & (r < 0.75)]
    return pd.Series(
        {
            "low": len(lo),
            "gradient": lo.ld.mean() - mid.ld.mean(),
            "7d low": (lo.dom <= 7).mean(),
            "7d mid": (mid.dom <= 7).mean(),
            "days low": lo.dom.median(),
            "days mid": mid.dom.median(),
        }
    )


for col in ["net_gap", "gross_gap", "conc"]:
    print(col, "lowest tenth against the middle half")
    print(f.groupby("half").apply(by_rank, col).round(3).to_string())


def slopes(g, cols):
    """OLS of log days on the columns, with standard errors clustered by building."""
    X = np.column_stack([np.ones(len(g))] + [g[c].to_numpy(float) for c in cols])
    y = g.ld.to_numpy(float)
    xtx = np.linalg.inv(X.T @ X)
    beta = xtx @ X.T @ y
    score = (
        pd.DataFrame(X * (y - X @ beta)[:, None])
        .groupby(g.building.to_numpy())
        .sum()
        .to_numpy()
    )
    se = np.sqrt(np.diag(xtx @ score.T @ score @ xtx))
    return {c: (round(b, 3), round(e, 3)) for c, b, e in zip(cols, beta[1:], se[1:])}


f["gross_log"] = f.gross_gap * f.s
f["net_log"] = f.net_gap * f.s
h["gap_log"] = h.zf * h.s
print(
    "free-month ads: log days on gross gap and concession",
    slopes(f, ["gross_log", "conc"]),
)
print("free-month ads: log days on net gap alone", slopes(f, ["net_log"]))
for half in (0, 1):
    print("half", half, slopes(f[f.half == half], ["gross_log", "conc"]))
print(
    "no free months: log days on gap",
    slopes(h[(h.free == 0) & np.isfinite(h.gap_log)], ["gap_log"]),
)
