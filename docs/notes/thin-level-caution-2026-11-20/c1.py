import json, numpy as np, pandas as pd

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
o["low"] = o.cdf < 0.05
RULES = {
    "hi4": o.level > 0.4,
    "hi3_thin5": (o.level > 0.3) & (o.n_bld <= 5),
    "hi3_other5": (o.level > 0.3) & (o.n_other <= 5),
    "hi15_other5": (o.level > 0.15) & (o.n_other <= 5),
    "hi3_6to20": (o.level > 0.3) & (o.n_bld > 5) & (o.n_bld <= 20),
    "hi4_21plus": (o.level > 0.4) & (o.n_bld > 20),
    "hi4_le20": (o.level > 0.4) & (o.n_bld <= 20),
    "hi3to4_le5": (o.level > 0.3) & (o.level <= 0.4) & (o.n_bld <= 5),
}
print("== l2bt: within-rule, days by low or not, by half")
for k, m in RULES.items():
    for hf in (0, 1):
        x = o[m & (o.half == hf)]
        lo = x[x.low & x.days.notna()]
        hi = x[~x.low & x.days.notna()]
        print(
            f"{k:12s} half {'AB'[hf]} ads {len(x):5d} bld {x.building.nunique():4d} below5 {x.low.mean():.3f} above95 {(x.cdf > 0.95).mean():.3f} gap {x.gap.mean():+.3f} med {x.gap.median():+.3f} | low n {len(lo):3d} d14 {(lo.days <= 14).mean():.2f} med {lo.days.median():5.1f} | not low d14 {(hi.days <= 14).mean():.2f} med {hi.days.median():5.1f}"
        )
rest = o[~RULES["hi4"]]
for hf in (0, 1):
    x = rest[rest.half == hf]
    lo = x[x.low & x.days.notna()]
    hi = x[~x.low & x.days.notna()]
    print(
        f"rest(not hi4) half {'AB'[hf]} ads {len(x)} below5 {x.low.mean():.3f} gap {x.gap.mean():+.3f} low d14 {(lo.days <= 14).mean():.2f} med {lo.days.median()} | not low d14 {(hi.days <= 14).mean():.2f} med {hi.days.median()}"
    )
# concentration of hi4
x = o[RULES["hi4"]]
g = (
    x.groupby("building")
    .agg(
        n=("gap", "size"),
        gap=("gap", "mean"),
        low=("low", "sum"),
        level=("level", "first"),
        ntr=("n_bld", "first"),
    )
    .sort_values("n", ascending=False)
)
print(g.head(15).round(3).to_string())
print(
    "hi4 buildings",
    len(g),
    "building-mean gap (equal weight)",
    g.gap.mean().round(3),
    "share of buildings with mean gap<0",
    (g.gap < 0).mean().round(3),
)
# equal weight per building for thin rule
for k in ("hi3_thin5", "hi4_le20", "hi4_21plus"):
    x = o[RULES[k]]
    g = (
        x.groupby(["half", "building"])
        .gap.mean()
        .groupby("half")
        .agg(["size", "mean", "median"])
    )
    print(k, g.round(3).to_dict("index"))
# worst-10 examples thin rule
print(
    o[RULES["hi3_thin5"]]
    .sort_values("gap")
    .head(25)[
        [
            "listing_id",
            "building",
            "year",
            "bedrooms",
            "latest_ask",
            "level",
            "n_bld",
            "n_other",
            "gap",
            "cdf",
            "days",
            "half",
        ]
    ]
    .round(3)
    .to_string()
)
# backtest
b = pd.read_parquet("back_ads.parquet")
BR = {
    "hi4": b.level > 0.4,
    "hi3_thin5": (b.level > 0.3) & (b.n_bld <= 5),
    "hi3_other5": (b.level > 0.3) & (b.n_other <= 5),
    "hi3": (b.level > 0.3),
    "hi3_le20": (b.level > 0.3) & (b.n_bld <= 20),
}
print("== backtest range-j")
for k, m in BR.items():
    for hf in (0, 1, 2):
        mm = m & ((b.half == hf) | (hf == 2))
        x = b[mm]
        r = b[~m & ((b.half == hf) | (hf == 2))]
        lo = x[x.ok & (x.place < 0.1)]
        rl = r[r.ok & (r.place < 0.1)]
        print(
            f"{k:11s} half {'AB*'[hf]} ads {len(x):4d} bld {x.building.nunique():3d} below5 {(x.cdf < 0.05).mean():.3f} vs {(r.cdf < 0.05).mean():.3f} gap {x.gap.mean():+.3f} vs {r.gap.mean():+.3f} | lowest tenth n {len(lo):2d} d14 {(lo.days <= 14).mean():.2f} vs {(rl.days <= 14).mean():.2f} meddays {lo.days.median()} vs {rl.days.median()} cut {(lo.change < -0.001).mean():.2f} vs {(rl.change < -0.001).mean():.2f} raised {(lo.change > 0.001).mean():.2f} vs {(rl.change > 0.001).mean():.2f} | all d14 {(x.days <= 14).mean():.2f} meddays {x.days.median()}"
        )
# live
L = pd.read_parquet("/data1/apartments/tmp/po-bldmodes/levels_live.parquet").set_index(
    "building"
)
D = pd.DataFrame(json.load(open("/data1/apartments/site/deals/deals.json")))
D["rank"] = np.arange(1, len(D) + 1)
D["unc"] = D.cautions.map(len) == 0
D["urank"] = np.where(D.unc, D.unc.cumsum(), np.nan)
D["level"] = D.building.map(L.level)
D["ntr"] = D.building.map(L.n_train)
print("== live deals", len(D), "uncautioned", D.unc.sum())
for k, m in {
    "hi4": D.level > 0.4,
    "hi3_thin5": (D.level > 0.3) & (D.ntr <= 5),
    "hi5": D.level > 0.5,
    "hi3": D.level > 0.3,
    "hi3_le20": (D.level > 0.3) & (D.ntr <= 20),
}.items():
    print(
        k,
        "ads",
        m.sum(),
        "bld",
        D[m].building.nunique(),
        "first300",
        (m & (D["rank"] <= 300)).sum(),
        "first300 uncautioned",
        (m & (D.urank <= 300)).sum(),
        "already cautioned",
        (m & ~D.unc).sum(),
    )
