"""Live Deals table: where thin buildings' ads stand, and how far the order would move if
their levels were shrunk by the factors the held-out history supports."""

import json

import numpy as np
import pandas as pd
from scipy import stats

pd.set_option("display.width", 250)
d = pd.DataFrame(json.load(open("/data1/apartments/site/deals/deals.json")))
lv = pd.read_parquet("/data1/apartments/tmp/po-bldmodes/levels_live.parquet").set_index(
    "building"
)
d["level"] = d.building.map(lv.level)
d["n_bld"] = d.building.map(lv.n_train).fillna(0).astype(int)
d["rank"] = np.arange(1, len(d) + 1)
d["plain"] = d.cautions.map(len) == 0
d["urank"] = np.where(d.plain, d.plain.cumsum(), np.nan)
print("ads", len(d), "no level", d.level.isna().sum(), "uncautioned", d.plain.sum())
d["level"] = d.level.fillna(0)
d["sb"] = pd.cut(d.n_bld, [-1, 0, 5, 10, 1e9], labels=["0", "1-5", "6-10", "11+"])
d["lb"] = pd.cut(
    d.level,
    [-9, -0.3, -0.1, 0.1, 0.3, 9],
    labels=["<-.3", "-.3:-.1", "mid", ".1:.3", ">.3"],
)
d["new_unit"] = d.unit_ads.fillna(0) == 0
t = d.groupby(["sb", "lb"], observed=True).agg(
    ads=("rank", "size"),
    first300=("rank", lambda r: (r <= 300).sum()),
    ufirst300=("urank", lambda r: (r <= 300).sum()),
    new_unit=("new_unit", "mean"),
    below=("below_share", "median"),
)
print(t.round(3).to_string())
print(
    d.groupby("sb", observed=True)
    .agg(
        ads=("rank", "size"),
        first300=("rank", lambda r: (r <= 300).sum()),
        ufirst300=("urank", lambda r: (r <= 300).sum()),
        new_unit=("new_unit", "mean"),
    )
    .to_string()
)

s = (np.log(d.model_hi80) - np.log(d.model_lo80)) / 2.563
z = stats.norm.ppf(d.below_share.clip(1e-6, 1 - 1e-6))


def scenario(name, k5, k10, col="level"):
    x = (
        d[col]
        if col == "level"
        else np.sign(d.level) * np.clip(d.level.abs() - 0.1, 0, None)
    )
    k = np.where(d.n_bld <= 5, k5, np.where(d.n_bld <= 10, k10, 0.0))
    znew = z + k * x / s
    new = stats.norm.cdf(znew)
    order = np.argsort(new, kind="stable")
    nr = np.empty(len(d), int)
    nr[order] = np.arange(1, len(d) + 1)
    old300 = set(d.listing_id[d["rank"] <= 300])
    new300 = set(d.listing_id[nr <= 300])
    moved = (k * x != 0).sum()
    # uncautioned
    up = d.plain.to_numpy()
    uo = np.argsort(np.where(up, new, 9), kind="stable")[:300]
    unew300 = set(d.listing_id.to_numpy()[uo])
    uold300 = set(d.listing_id[d.urank <= 300])
    f = d["rank"] <= 300
    print(
        f"{name}: ads with a changed score {moved}, of them in the first 300 {(f & (k * x != 0)).sum()}; "
        f"leave the first 300: {len(old300 - new300)}, enter: {len(new300 - old300)}; "
        f"uncautioned first 300 leave {len(uold300 - unew300)}; "
        f"first-300 ads moving 10+ places {(np.abs(nr - d['rank'])[f] >= 10).sum()}, "
        f"25+ {(np.abs(nr - d['rank'])[f] >= 25).sum()}; median abs shift in log median, changed ads {np.median(np.abs(k * x)[k * x != 0]):.4f}"
    )


scenario("history factors on the level (0.10 thin, 0.03 for 6-10)", 0.10, 0.03)
scenario(
    "history factors on the excess over 0.1 (0.19 thin, 0.05 for 6-10)",
    0.19,
    0.05,
    "excess",
)
scenario("three times the history factor (0.30, 0.10)", 0.30, 0.10)
scenario("half of every thin level removed (0.50, 0.15)", 0.50, 0.15)
