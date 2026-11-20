"""l2bt held-out ads: gap by support of the building x level band, and the slope of the gap
on the level within each support band, by half of the buildings."""

import sys

import numpy as np
import pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 400)
P = "/data1/apartments/tmp/po-thinlevel/"
o = pd.read_parquet(P + "l2_ads_flags.parquet")
cls = pd.read_csv(
    "/data1/apartments/serve/master/docs/notes/building-level-read-2026-11-20/classes.csv"
)
DATA = ["commercial", "placeholder", "wrong_ask", "two_buildings", "real_difference"]
print(cls["class"].value_counts().to_string())
o["read_class"] = o.building.map(cls.set_index("b")["class"])
# odd: the building's training ads hold a commercial ad, or a placeholder ad over 1.5x the
# area median, or the building is one of the 96 read and not classed as model shape
o["odd"] = (
    (o.com > 0)
    | (o.ph15 > 0)
    | (o.sh15 > 0)
    | o.read_class.notna() & (o.read_class != "model_shape")
)
o["own_odd"] = o.own_ph | o.own_com
SB = [-1, 0, 1, 2, 5, 10, 1e9]
SL = ["0", "1", "2", "3-5", "6-10", "11+"]
LB = [-9, -0.3, -0.1, 0.1, 0.3, 9]
LL = ["<-.3", "-.3:-.1", "mid", ".1:.3", ">.3"]
o["sb"] = pd.cut(o.n_bld, SB, labels=SL)
o["lb"] = pd.cut(o.level, LB, labels=LL)
o.to_parquet("d1_ads.parquet")


def summ(x):
    return pd.Series(
        dict(
            ads=len(x),
            bld=x.building.nunique(),
            gap=x.gap.mean(),
            gap_med=x.gap.median(),
            below5=(x.cdf < 0.05).mean(),
            above95=(x.cdf > 0.95).mean(),
            odd=x.odd.mean(),
        )
    )


def slope(x, col="level"):
    """OLS of gap on the level with an intercept; se clustered by building."""
    if len(x) < 20:
        return dict(ads=len(x))
    X = np.column_stack([np.ones(len(x)), x[col].to_numpy()])
    y = x.gap.to_numpy()
    XtXi = np.linalg.inv(X.T @ X)
    b = XtXi @ X.T @ y
    e = y - X @ b
    g = pd.DataFrame(X * e[:, None]).groupby(x.building.to_numpy()).sum().to_numpy()
    V = XtXi @ (g.T @ g) @ XtXi
    # Huber-ish: slope of medians, the gap clipped at +-0.5
    yc = np.clip(y, -0.5, 0.5)
    bc = XtXi @ X.T @ yc
    return dict(
        ads=len(x),
        bld=x.building.nunique(),
        sd_level=x[col].std(),
        slope=b[1],
        se=np.sqrt(V[1, 1]),
        slope_clip=bc[1],
        icpt=b[0],
    )


for which in ("all", "A", "B"):
    x = o if which == "all" else o[o.half == (which == "B")]
    print("\n===== half", which, len(x), x.building.nunique())
    print(x.groupby(["sb", "lb"], observed=True).apply(summ).round(3).to_string())
    for label, m in [
        ("all ads", x),
        ("not odd, own text ordinary", x[~x.odd & ~x.own_odd]),
        ("unit new to the fit (n_unit=0)", x[x.n_unit == 0]),
        ("unit seen (n_unit>0)", x[x.n_unit > 0]),
        ("abs(level) over 0.1", x[x.level.abs() > 0.1]),
        ("abs(level) at most 0.1", x[x.level.abs() <= 0.1]),
        ("level over 0", x[x.level > 0]),
        ("level under 0", x[x.level < 0]),
        ("manhattan", x[x.zone == "manhattan"]),
        ("outer", x[x.zone == "outer"]),
    ]:
        print("-- slope of gap on level:", label)
        print(
            pd.DataFrame({k: slope(v) for k, v in m.groupby("sb", observed=True)})
            .T.round(3)
            .to_string()
        )
