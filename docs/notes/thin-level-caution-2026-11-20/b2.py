"""l2bt: tables by level x support. Usage: b2.py HALF(A|B|all). Joins outcomes from the ads file."""

import sys, numpy as np, pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 400)
o = pd.read_parquet("l2_ads.parquet")
a = pd.read_parquet(
    "/data1/apartments/pipeline/datasets/ads-3775f6d9b3e028ca.parquet",
    columns=["listing_id", "first_day", "off_day", "first_ask", "latest_ask"],
).drop_duplicates("listing_id")
a["listing_id"] = a.listing_id.astype(str)
o = o.merge(a, on="listing_id", how="left", suffixes=("", "_ad"))
o["days"] = (
    pd.to_datetime(o.off_day).dt.tz_localize(None)
    - pd.to_datetime(o.first_day).dt.tz_localize(None)
).dt.days
o["chg"] = o.latest_ask_ad / o.first_ask - 1
o["gap_first"] = o.gap - np.log(o.latest_ask_ad / o.first_ask)
which = sys.argv[1]
if which != "all":
    o = o[o.half == (which == "B")]
print(
    "half",
    which,
    "ads",
    len(o),
    "buildings",
    o.building.nunique(),
    "below5",
    (o.cdf < 0.05).mean().round(4),
    "gap",
    o.gap.mean().round(4),
    "days known",
    o.days.notna().mean().round(3),
)
LB = [-9, -0.2, 0, 0.1, 0.2, 0.3, 0.5, 9]
LL = ["<-.2", "-.2-0", "0-.1", ".1-.2", ".2-.3", ".3-.5", ">.5"]
SB = [-1, 0, 2, 5, 10, 20, 1e9]
SL = ["0", "1-2", "3-5", "6-10", "11-20", "21+"]
o["lb"] = pd.cut(o.level, LB, labels=LL)
o["per"] = pd.cut(
    o.year,
    [0, 2019, 2022, 2024, 2030],
    labels=["to2019", "2020-22", "2023-24", "2025-26"],
)


def summ(x):
    lo = x[x.cdf < 0.05]
    lod = lo[lo.days.notna() & (lo.days >= 0)]
    return pd.Series(
        dict(
            ads=len(x),
            bld=x.building.nunique(),
            below5=(x.cdf < 0.05).mean(),
            above95=(x.cdf > 0.95).mean(),
            gap=x.gap.mean(),
            gap_med=x.gap.median(),
            rmse=np.sqrt((x.gap**2).mean()),
            gap_first=x.gap_first.mean(),
            n_low=len(lo),
            low_d14=(lod.days <= 14).mean() if len(lod) else np.nan,
            low_meddays=lod.days.median() if len(lod) else np.nan,
            low_raised15=(lo.chg >= 0.15).mean() if len(lo) else np.nan,
            low_gap=lo.gap.mean() if len(lo) else np.nan,
        )
    )


for sup in ("n_other", "n_bld"):
    o["sb"] = pd.cut(o[sup], SB, labels=SL)
    print("== support =", sup)
    print(o.groupby(["lb", "sb"], observed=True).apply(summ).round(3).to_string())
o["sb"] = pd.cut(o.n_other, SB, labels=SL)
print(o.groupby("lb", observed=True).apply(summ).round(3).to_string())
print(o.groupby("sb", observed=True).apply(summ).round(3).to_string())
base = (o.cdf < 0.05).mean()
rows = []
for sup in ("n_other", "n_bld"):
    for L in (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5):
        for N in (0, 1, 2, 3, 5, 10, 20, 10**9):
            m = (o.level > L) & (o[sup] <= N)
            x = o[m]
            if len(x) == 0:
                continue
            lo = x[x.cdf < 0.05]
            lod = lo[lo.days.notna()]
            rows.append(
                dict(
                    sup=sup,
                    L=L,
                    N=N,
                    ads=len(x),
                    bld=x.building.nunique(),
                    below5=(x.cdf < 0.05).mean(),
                    n_low=len(lo),
                    gap=x.gap.mean(),
                    gap_med=x.gap.median(),
                    above95=(x.cdf > 0.95).mean(),
                    low_d14=(lod.days <= 14).mean() if len(lod) else np.nan,
                )
            )
t = pd.DataFrame(rows)
print("base below5", round(base, 4))
print(t.round(3).to_string())
if which == "A":
    c = t[(t.ads >= 100) & (t.below5 >= 2 * base)].sort_values("n_low", ascending=False)
    print("CHOSEN on A (ads>=100, below5>=2x base, most low ads):")
    print(c.head(5).round(3).to_string())
if len(sys.argv) > 4:
    sup, L, N = sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    m = (o.level > L) & (o[sup] <= N)
    o["mark"] = m
    print("RULE", sup, L, N)
    print(o.groupby("mark").apply(summ).round(3).to_string())
    print(o.groupby(["per", "mark"], observed=True).apply(summ).round(3).to_string())
    lo = o[o.cdf < 0.05]
    print("share of below-5% ads marked", lo.mark.mean().round(4))
