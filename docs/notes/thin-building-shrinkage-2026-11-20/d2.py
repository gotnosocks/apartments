"""Pooled slopes for thin buildings by half, the tail form, what a shrink factor chosen on
half A does on half B, the backtest by whether the unit is new, and the levels' spread."""

import numpy as np
import pandas as pd
from scipy import stats

pd.set_option("display.width", 250)
P = "/data1/apartments/tmp/po-thinlevel/"
o = pd.read_parquet("d1_ads.parquet")


def slope(x, col="level", ycol="gap"):
    X = np.column_stack([np.ones(len(x)), x[col].to_numpy()])
    y = x[ycol].to_numpy()
    XtXi = np.linalg.inv(X.T @ X)
    b = XtXi @ X.T @ y
    e = y - X @ b
    g = pd.DataFrame(X * e[:, None]).groupby(x.building.to_numpy()).sum().to_numpy()
    V = XtXi @ (g.T @ g) @ XtXi
    return dict(
        ads=len(x), bld=x.building.nunique(), slope=b[1], se=np.sqrt(V[1, 1]), icpt=b[0]
    )


def tab(d):
    return pd.DataFrame(d).T.round(3).to_string()


o["thin"] = pd.cut(o.n_bld, [0, 5, 10, 1e9], labels=["1-5", "6-10", "11+"])
o["far"] = o.level.abs() > 0.1
# the part of the level beyond 0.1 either side
o["excess"] = np.sign(o.level) * np.clip(o.level.abs() - 0.1, 0, None)
clean = ~o.odd & ~o.own_odd
print("thin ads", (o.n_bld <= 5).sum(), o[o.n_bld <= 5].building.nunique())
print(
    "thin and far",
    ((o.n_bld <= 5) & o.far).sum(),
    o[(o.n_bld <= 5) & o.far].building.nunique(),
)
print("thin, far, odd", ((o.n_bld <= 5) & o.far & ~clean).sum())
print(
    "thin, over .3",
    ((o.n_bld <= 5) & (o.level.abs() > 0.3)).sum(),
    "odd",
    ((o.n_bld <= 5) & (o.level.abs() > 0.3) & ~clean).sum(),
)
for h, hn in ((0, "A"), (1, "B"), (None, "all")):
    x = o if h is None else o[o.half == h]
    out = {}
    for t, v in x.groupby("thin", observed=True):
        out[f"{t} all"] = slope(v)
        out[f"{t} clean"] = slope(v[clean.loc[v.index]])
        out[f"{t} far"] = slope(v[v.far])
        out[f"{t} far clean"] = slope(v[v.far & clean.loc[v.index]])
        out[f"{t} near"] = slope(v[~v.far])
        out[f"{t} excess"] = slope(v, "excess")
        out[f"{t} excess clean"] = slope(v[clean.loc[v.index]], "excess")
    print("== half", hn)
    print(tab(out))

# shrink factors from half A applied to half B (and the reverse): pred' = pred - k * level
print("== a factor fitted on one half, scored on the other; thin = 5 or fewer")
for fit_h, test_h in ((0, 1), (1, 0)):
    a = o[(o.half == fit_h) & (o.n_bld <= 5)]
    b = o[(o.half == test_h) & (o.n_bld <= 5)]
    for name, col in (("level", "level"), ("excess", "excess")):
        k = -slope(a, col)["slope"]
        g2 = b.gap + k * b[col]
        far = b.far
        hi = b.level > 0.3
        print(
            f"fit {'AB'[fit_h]} k={k:.3f} on {name}; test {'AB'[test_h]}: "
            f"mae all {b.gap.abs().mean():.4f}->{g2.abs().mean():.4f}, "
            f"median abs {b.gap.abs().median():.4f}->{g2.abs().median():.4f}, "
            f"rmse {np.sqrt((b.gap**2).mean()):.4f}->{np.sqrt((g2**2).mean()):.4f}; "
            f"far ({far.sum()}) mae {b.gap[far].abs().mean():.4f}->{g2[far].abs().mean():.4f} "
            f"gap {b.gap[far].mean():.4f}->{g2[far].mean():.4f}; "
            f"over .3 ({hi.sum()}) gap {b.gap[hi].mean():.4f}->{g2[hi].mean():.4f} "
            f"mae {b.gap[hi].abs().mean():.4f}->{g2[hi].abs().mean():.4f}"
        )

# backtest: units new to the fit against units seen
bk = pd.read_parquet(P + "back_ads.parquet")
bk = bk[bk.level.notna()]
bk["thin"] = pd.cut(bk.n_bld, [-1, 0, 5, 10, 1e9], labels=["0", "1-5", "6-10", "11+"])
bk["new"] = bk.n_unit == 0
bk["excess"] = np.sign(bk.level) * np.clip(bk.level.abs() - 0.1, 0, None)
print("== backtest range-j", len(bk), "new units", bk.new.sum())
print(
    bk.groupby(["thin", "new"], observed=True)
    .agg(
        ads=("gap", "size"),
        bld=("building", "nunique"),
        gap=("gap", "mean"),
        sdlev=("level", "std"),
        b5=("cdf", lambda s: (s < 0.05).mean()),
        a95=("cdf", lambda s: (s > 0.95).mean()),
    )
    .round(3)
    .to_string()
)
out = {}
for (t, nw), v in bk.groupby(["thin", "new"], observed=True):
    if len(v) > 30 and v.level.std() > 0.02:
        out[f"{t} new={nw}"] = slope(v)
        out[f"{t} new={nw} excess"] = slope(v, "excess")
print(tab(out))

# the spread of levels against the prior
lv = pd.read_parquet(P + "l2_levels.parquet")
bsd = {"manhattan": 0.1132, "outer": 0.0680}
print(
    "== levels by support and zone: sd, robust sd (MAD*1.4826), shares beyond k prior scales"
)
rows = []
for z, b in bsd.items():
    for lo, hi in ((1, 1), (2, 2), (3, 5), (6, 10), (11, 29), (30, 99), (100, 10**6)):
        v = lv[(lv.zone == z) & lv.n_train.between(lo, hi)]
        x = v.level / b
        rows.append(
            dict(
                zone=z,
                n=f"{lo}-{hi}",
                bld=len(v),
                sd=v.level.std(),
                rsd=stats.median_abs_deviation(v.level) * 1.4826,
                post_sd=v.level_sd.mean(),
                over2=(x.abs() > 2).mean(),
                over3=(x.abs() > 3).mean(),
                over4=(x.abs() > 4).mean(),
                over5=(x.abs() > 5).mean(),
                kurt=stats.kurtosis(v.level),
            )
        )
print(pd.DataFrame(rows).round(4).to_string())
t4 = stats.t(4)
print(
    "t4: sd/scale",
    np.sqrt(2),
    "robust sd/scale",
    t4.ppf(0.75) * 1.4826,
    "beyond 2,3,4,5:",
    [round(2 * t4.sf(k), 4) for k in (2, 3, 4, 5)],
)
print("normal beyond 2,3,4,5:", [round(2 * stats.norm.sf(k), 5) for k in (2, 3, 4, 5)])
