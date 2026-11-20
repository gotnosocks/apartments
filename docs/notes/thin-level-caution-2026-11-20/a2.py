import numpy as np, pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)
o = pd.read_parquet("back_ads.parquet")
LB = [-9, 0, 0.1, 0.2, 0.3, 9]
LL = ["<0", "0-.1", ".1-.2", ".2-.3", ">.3"]
SB = [-1, 0, 2, 5, 20, 1e9]
SL = ["0", "1-2", "3-5", "6-20", "21+"]
o["lb"] = pd.cut(o.level, LB, labels=LL)


def summ(x):
    lo = x[x.ok & (x.place < 0.1)]
    return pd.Series(
        dict(
            ads=len(x),
            bld=x.building.nunique(),
            below5=(x.cdf < 0.05).mean(),
            place_lt10=(x.place < 0.1).mean(),
            gap=x.gap.mean(),
            gap_med=x.gap.median(),
            gap_first=x.gap_first.mean(),
            n_low=len(lo),
            low_d14=(lo.days <= 14).mean() if len(lo) else np.nan,
            low_meddays=lo.days.median() if len(lo) else np.nan,
            low_cut=(lo.change < -0.001).mean() if len(lo) else np.nan,
            low_raised=(lo.change > 0.001).mean() if len(lo) else np.nan,
            low_chg=100 * lo.change.mean() if len(lo) else np.nan,
            all_d14=(x.days <= 14).mean(),
            all_cut=(x.change < -0.001).mean(),
            all_meddays=x.days.median(),
        )
    )


for sup in ("n_bld", "n_other"):
    o["sb"] = pd.cut(o[sup], SB, labels=SL)
    print("== support =", sup)
    print(o.groupby(["lb", "sb"], observed=True).apply(summ).round(3).to_string())
print(o.groupby("lb", observed=True).apply(summ).round(3).to_string())
o["sb"] = pd.cut(o.n_bld, SB, labels=SL)
print(o.groupby("sb", observed=True).apply(summ).round(3).to_string())
# candidate group
for L in (0.15, 0.2, 0.3):
    for N in (2, 5, 10, 20):
        for sup in ("n_bld", "n_other"):
            m = (o.level > L) & (o[sup] <= N)
            x = o[m]
            r = o[~m]
            print(
                f"L>{L} {sup}<={N}: ads {m.sum()} bld {x.building.nunique()} below5 {(x.cdf < 0.05).mean():.3f} vs {(r.cdf < 0.05).mean():.3f}  gap {x.gap.mean():+.3f} vs {r.gap.mean():+.3f}  inLowestTenth(place) {(x.place < 0.1).sum()} cdf<.1 {(x.cdf < 0.1).sum()}"
            )
m = (o.level > 0.3) & (o.n_bld <= 5)
print(
    o[m | ((o.level > 0.2) & (o.n_bld <= 5))]
    .sort_values("level", ascending=False)[
        [
            "listing_id",
            "building",
            "bedrooms",
            "ask",
            "level",
            "level_sd",
            "n_bld",
            "n_other",
            "gap",
            "cdf",
            "place",
            "days",
            "change",
            "caut",
        ]
    ]
    .round(3)
    .to_string()
)
print(
    "lowest tenth overall",
    (o.place < 0.1).sum(),
    (o.cdf < 0.1).sum(),
    (o.cdf < 0.05).sum(),
)
