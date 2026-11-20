import numpy as np, pandas as pd

o = pd.read_parquet("l2_ads.parquet")
for k, m in {
    "lo3_thin5": (o.level < -0.3) & (o.n_bld <= 5),
    "lo3_le20": (o.level < -0.3) & (o.n_bld <= 20),
    "lo2_le5": (o.level < -0.2) & (o.n_bld <= 5),
    "lo3_any": o.level < -0.3,
}.items():
    x = o[m]
    print(
        k,
        len(x),
        x.building.nunique(),
        "below5",
        round((x.cdf < 0.05).mean(), 3),
        "above95",
        round((x.cdf > 0.95).mean(), 3),
        "gap",
        round(x.gap.mean(), 3),
        round(x.gap.median(), 3),
    )
# by year for hi3_thin5 and hi4_le20 both halves
o["per"] = pd.cut(
    o.year,
    [0, 2019, 2022, 2024, 2030],
    labels=["to2019", "2020-22", "2023-24", "2025-26"],
)
for k, m in {
    "hi3_thin5": (o.level > 0.3) & (o.n_bld <= 5),
    "hi4_le20": (o.level > 0.4) & (o.n_bld <= 20),
    "hi4": o.level > 0.4,
}.items():
    x = o[m]
    print(k)
    print(
        x.groupby(["per", "half"], observed=True)
        .apply(
            lambda v: pd.Series(
                dict(ads=len(v), below5=(v.cdf < 0.05).mean(), gap=v.gap.mean())
            )
        )
        .round(3)
        .unstack()
        .to_string()
    )
print(
    o.groupby("per", observed=True)
    .apply(
        lambda v: pd.Series(
            dict(ads=len(v), below5=(v.cdf < 0.05).mean(), gap=v.gap.mean())
        )
    )
    .round(3)
)
