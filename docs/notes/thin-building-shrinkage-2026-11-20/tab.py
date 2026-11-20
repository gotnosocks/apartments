"""The note's table: support of the building by level band, both halves."""

import pandas as pd

o = pd.read_parquet("d1_ads.parquet")
o = o[o.n_bld >= 1]
o["sb"] = pd.cut(
    o.n_bld, [0, 1, 2, 5, 10, 1e9], labels=["1", "2", "3-5", "6-10", "11+"]
)
names = dict(
    zip(
        ["<-.3", "-.3:-.1", "mid", ".1:.3", ">.3"],
        ["under -0.3", "-0.3 to -0.1", "middle", "0.1 to 0.3", "over 0.3"],
    )
)
print(
    "| training ads | level | ads | buildings | gap | gap A | gap B | below 5% | above 95% |"
)
print("|---|---|---|---|---|---|---|---|---|")
for (s, l), x in o.groupby(["sb", "lb"], observed=True):
    a, b = x[x.half == 0], x[x.half == 1]
    print(
        f"| {s} | {names[l]} | {len(x):,} | {x.building.nunique():,} | {x.gap.mean():+.3f} | "
        f"{a.gap.mean():+.3f} | {b.gap.mean():+.3f} | {(x.cdf < 0.05).mean():.1%} | "
        f"{(x.cdf > 0.95).mean():.1%} |"
    )
print(len(o), (o.cdf < 0.05).mean(), (o.cdf > 0.95).mean(), o.gap.mean())
