"""Outdoor size, step 5: the new columns screened against L1's held-out predictions.

I load L1's `pred_scores.npz`, check that its held-out ads are the dataset copy's `heldout`
rows in the same order, and leave out S16's 400 drawn ads, as S16 did. For each kept
held-out ad I take:

- the gap, the log ask less L1's median;
- `in80`, whether the ask falls inside L1's 10% and 90% quantiles;
- z, the standard normal quantile of L1's predictive CDF at the ask, clipped to 1e-6 from
  either end.

Then, over the ads with an `outdoor_sqft`, by size bin and by whether the listing codes give
the unit private outdoor space (`po_coded`, as in `b5_patterns.py`), I report:

- the mean gap, with an SE clustered by building;
- the gap relative to the mean gap of the building's other kept held-out ads, for ads in a
  building with at least one, again with a clustered SE;
- the sd of z over its sd for all kept ads, and the MAD of the gap over its MAD for all kept
  ads, S16's measure of spread;
- the share inside L1's 80% interval.

Within the marked ads I fit the gap on log2 of the area by least squares, with SEs clustered
by building, for all marked ads and for each side of `po_coded`, and the gap on an uncoded
indicator for the difference between the sides. Last come the comparison groups: coded ads
with no stated area, ads whose only areas were implausible, and S16's `outdoor_large` ads
split by whether the new column gives 300 sq ft or more.

    python o5_screen.py   # inside systemd-run --user --scope -p MemoryMax=3G
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import norm

DATA = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-outdoorsize/rows.parquet"
)
RUN = Path(
    "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
)
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
S7 = "/data1/apartments/tmp/sprint-20261113/s7_text.parquet"
DRAW = "/data1/apartments/tmp/blind-spots-2026-11-14/draw.parquet"
OUT = Path("/data1/apartments/tmp/outdoor-size-2026-11-14/")
BINS = [20, 100, 200, 300, 500, 1000, 5000]

d = pd.read_parquet(
    DATA, columns=["listing_id", "building", "outdoor_sqft", "outdoor_sqft_src"]
)
a = np.load(RUN / "pred_scores.npz", allow_pickle=True)
d["held"] = a["heldout"]
assert (d.listing_id[d.held].to_numpy() == a["listing"]).all()
qs = list(a["quantiles"])
d["gap"], d["in80"], d["z"] = np.nan, False, np.nan
d.loc[d.held, "gap"] = a["y"] - a["pred"]
d.loc[d.held, "in80"] = (a["y"] >= a["q"][:, qs.index(0.1)]) & (
    a["y"] <= a["q"][:, qs.index(0.9)]
)
d.loc[d.held, "z"] = norm.ppf(np.clip(a["cdf"], 1e-6, 1 - 1e-6))

po = [c for c in pq.read_schema(CODES).names if c.startswith("private_outdoor:")]
codes = pd.read_parquet(
    CODES, columns=["listing_id", "feat:PRIVATE_OUTDOOR_SPACE", *po]
)
codes["po_coded"] = codes[["feat:PRIVATE_OUTDOOR_SPACE", *po]].fillna(0).max(axis=1) > 0
codes["listing_id"] = codes.listing_id.astype(str)
s7 = pd.read_parquet(S7, columns=["listing_id", "out_sqft"])
s7["listing_id"] = s7.listing_id.astype(str)
n = len(d)
d = d.merge(codes[["listing_id", "po_coded"]], on="listing_id", how="left").merge(
    s7, on="listing_id", how="left"
)
assert len(d) == n
d["po_coded"] = d.po_coded.fillna(False).astype(bool)

drawn = d.listing_id.isin(set(pd.read_parquet(DRAW, columns=["listing_id"]).listing_id))
k = d[d.held & ~drawn].copy()
# The mean gap of the building's other kept held-out ads.
s = k.groupby("building").gap.agg(["sum", "count"])
tot, cnt = k.building.map(s["sum"]), k.building.map(s["count"])
k["rel"] = np.where(cnt > 1, k.gap - (tot - k.gap) / (cnt - 1).clip(lower=1), np.nan)


def cluster_mean_se(v, b):
    v = np.asarray(v, float)
    t = pd.Series(v - v.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(v))


def mad(v):
    return float(np.median(np.abs(v - np.median(v))))


def cluster_ols(y, x, b):
    """Least squares of y on [1, x], with CR1 standard errors clustered by b."""
    X = np.column_stack([np.ones(len(x)), np.asarray(x, float)])
    y = np.asarray(y, float)
    bread = np.linalg.inv(X.T @ X)
    beta = bread @ X.T @ y
    e = y - X @ beta
    s = pd.DataFrame(X * e[:, None]).groupby(np.asarray(b)).sum().to_numpy()
    g, nobs = len(s), len(y)
    v = bread @ (s.T @ s) @ bread * g / (g - 1) * (nobs - 1) / (nobs - 2)
    return {
        "ads": nobs,
        "buildings": g,
        "intercept": float(beta[0]),
        "slope": float(beta[1]),
        "slope_se": float(np.sqrt(v[1, 1])),
    }


base = {
    "ads": len(k),
    "mean_gap": float(k.gap.mean()),
    "z_sd": float(k.z.std()),
    "mad": mad(k.gap),
    "in80": float(k.in80.mean()),
}


def stats(g):
    r = g.rel.dropna()
    return {
        "ads": len(g),
        "buildings": int(g.building.nunique()),
        "mean_gap": float(g.gap.mean()),
        "mean_gap_se": cluster_mean_se(g.gap, g.building) if len(g) > 1 else np.nan,
        "rel_ads": len(r),
        "rel_gap": float(r.mean()) if len(r) else np.nan,
        "rel_gap_se": cluster_mean_se(r, g.building[r.index]) if len(r) > 1 else np.nan,
        "z_sd_ratio": float(g.z.std() / base["z_sd"]),
        "mad_ratio": mad(g.gap) / base["mad"],
        "in80": float(g.in80.mean()),
    }


m = k[k.outdoor_sqft.notna()].copy()
m["bin"] = pd.cut(m.outdoor_sqft, BINS, include_lowest=True).astype(str)
m["side"] = np.where(m.po_coded, "coded", "uncoded")
res = {"base": base, "marked": stats(m), "by_side": {}, "by_bin": {}, "by_bin_side": {}}
for side, g in m.groupby("side"):
    res["by_side"][side] = stats(g)
for b in pd.cut(pd.Series(BINS[1:]), BINS, include_lowest=True).astype(str):
    res["by_bin"][b] = stats(m[m.bin == b])
    for side in ("coded", "uncoded"):
        res["by_bin_side"][f"{b} {side}"] = stats(m[(m.bin == b) & (m.side == side)])
res["by_300"] = {
    f"{lo} {side}": stats(g)
    for (lo, side), g in m.groupby(
        [np.where(m.outdoor_sqft >= 300, ">=300", "<300"), "side"]
    )
}
res["slope_per_doubling"] = {
    "all": cluster_ols(m.gap, np.log2(m.outdoor_sqft), m.building),
    "coded": cluster_ols(
        m.gap[m.po_coded], np.log2(m.outdoor_sqft[m.po_coded]), m.building[m.po_coded]
    ),
    "uncoded": cluster_ols(
        m.gap[~m.po_coded],
        np.log2(m.outdoor_sqft[~m.po_coded]),
        m.building[~m.po_coded],
    ),
    "all_300": cluster_ols(
        m.gap[m.outdoor_sqft >= 300],
        np.log2(m.outdoor_sqft[m.outdoor_sqft >= 300]),
        m.building[m.outdoor_sqft >= 300],
    ),
}
res["uncoded_minus_coded"] = cluster_ols(m.gap, (~m.po_coded).astype(float), m.building)
res["uncoded_minus_coded_300"] = cluster_ols(
    m.gap[m.outdoor_sqft >= 300],
    (~m.po_coded[m.outdoor_sqft >= 300]).astype(float),
    m.building[m.outdoor_sqft >= 300],
)
large = k.out_sqft >= 300
mine300 = k.outdoor_sqft >= 300
res["compare"] = {
    "coded_no_area": stats(k[k.po_coded & k.outdoor_sqft.isna()]),
    "uncoded_no_area": stats(k[~k.po_coded & k.outdoor_sqft.isna()]),
    "implausible_only": stats(k[k.outdoor_sqft_src == "implausible"]),
    "s16_large": stats(k[large]),
    "s16_large_and_mine_300": stats(k[large & mine300]),
    "s16_large_not_mine_300": stats(k[large & ~mine300]),
    "mine_300_not_s16_large": stats(k[~large & mine300]),
}
(OUT / "o5_screen.json").write_text(json.dumps(res, indent=1))

cols = ["ads", "mean_gap", "mean_gap_se", "rel_gap", "rel_gap_se"]
cols += ["z_sd_ratio", "mad_ratio", "in80"]
print("base", json.dumps(base))
for part in ("by_side", "by_bin", "by_bin_side", "by_300", "compare"):
    t = pd.DataFrame(res[part]).T[cols]
    with pd.option_context("display.width", 200):
        print(t.round(4).to_string())
print("marked", json.dumps(res["marked"]))
for name, r in res["slope_per_doubling"].items():
    print(f"slope {name}: {r['slope']:+.4f} ± {r['slope_se']:.4f} ({r['ads']} ads)")
for name in ("uncoded_minus_coded", "uncoded_minus_coded_300"):
    r = res[name]
    print(f"{name}: {r['slope']:+.4f} ± {r['slope_se']:.4f} ({r['ads']} ads)")
