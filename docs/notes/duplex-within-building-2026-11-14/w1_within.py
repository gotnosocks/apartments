"""S7's within-building duplex contrast with the (n-1)/n correction, and the sprint figures built
the same way.

`s7c_unitkey.py` squared each held-out ad's clipped gap less its building's mean, a mean that
includes the ad. With n held-out ads in a building that square carries (n-1)/n of the ad's
variance about the building's center, and an ad alone in its building gets zero. `u2_scatter.py`
corrected it: buildings with at least 2 held-out ads, the square times n/(n-1), and for the gap
the mean of the building's other held-out ads. This script reads L1's held-out ads of the latest
split with the loaders s7c and u2 use and computes:

1. s7c's uncorrected figures on every held-out ad, to check the loading against S7 part C;
2. on the buildings with 2 or more held-out ads, the duplex ads' excess in the clipped squared
   gap over the rest, overall and within building, uncorrected and corrected, with the share
   within building and an interval on it from resamples of the buildings;
3. on the buildings with 3 or more, a within-building square whose expectation is the ad's own
   variance about the building's center when the ads share one: the square of the gap less the
   mean of the other ads, less the other ads' sample variance over n-1. The n/(n-1) scaling
   blends an ad's variance with the others', so it leans low where the duplex ads are wider;
4. S7 part A's level within building, from the mean of the building's other held-out ads and by
   a regression of the demeaned gap on the demeaned duplex indicator;
5. part C's table by the unit's previous ad, with the corrected within-building square;
6. the same corrections for the j9 figures of S7 parts A and B, S4's deciles of the building's
   competing ads, and S7's outdoor-size slope and bins.

SEs are clustered by building. Inputs are read only; outputs go to OUT.

    systemd-run --user --scope -q -p MemoryMax=3G python w1_within.py
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

OUT = "/data1/apartments/tmp/duplex-within-building-2026-11-14/"
os.makedirs(OUT, exist_ok=True)
FLAGS = "/data1/apartments/tmp/outlier-sprint/qual/flags.parquet"
J9 = "/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9/"
DRAWS = 2000


def n_in(b):
    """The number of ads in each ad's group `b`."""
    return pd.Series(np.asarray(b)).groupby(np.asarray(b)).transform("size").to_numpy()


def loo_scale(n):
    """n/(n-1) where a building has 2 or more ads, NaN where it has 1."""
    return np.where(n >= 2, n / np.maximum(n - 1, 1), np.nan)


def own_var(x, b):
    """For groups of 3 or more: the square of `x` less the mean of the group's other values,
    less their sample variance over n-1. NaN for smaller groups."""
    x = np.asarray(x, float)
    s = pd.Series(x).groupby(np.asarray(b))
    n = s.transform("size").to_numpy().astype(float)
    s1 = s.transform("sum").to_numpy()
    s2 = pd.Series(x * x).groupby(np.asarray(b)).transform("sum").to_numpy()
    ok = n >= 3
    k = np.where(ok, n - 1, np.nan)
    m = (s1 - x) / k
    var = ((s2 - x * x) - k * m * m) / (k - 1)
    return np.where(ok, (x - m) ** 2 - var / k, np.nan)


def mean_se(x, b):
    """Mean of `x` with its building-clustered SE."""
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    x, b = x[ok], np.asarray(b)[ok]
    t = pd.Series(x - x.mean()).groupby(b).sum()
    return float(x.mean()), float(
        np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(x)
    )


def diff(x, on, b):
    """`common.cluster_mean_diff` as a list, for JSON."""
    return list(c.cluster_mean_diff(np.asarray(x, float), np.asarray(on), b))


def share(over, within, on, b, seed):
    """The within-building excess over the overall excess of the marked ads, with the 2.5% and
    97.5% points over DRAWS resamples of the buildings. Every ad has both values finite."""
    on = np.asarray(on, bool)
    f = pd.DataFrame(
        {
            "b": np.asarray(b),
            "n1": on.astype(float),
            "n0": (~on).astype(float),
            "a1": np.where(on, over, 0.0),
            "a0": np.where(on, 0.0, over),
            "z1": np.where(on, within, 0.0),
            "z0": np.where(on, 0.0, within),
        }
    )
    m = f.groupby("b").sum().to_numpy()
    rng = np.random.default_rng(seed)

    def ratio(s):
        return (s[4] / s[0] - s[5] / s[1]) / (s[2] / s[0] - s[3] / s[1])

    boot = np.array(
        [
            ratio(np.bincount(rng.integers(0, len(m), len(m)), minlength=len(m)) @ m)
            for _ in range(DRAWS)
        ]
    )
    return {
        "share": float(ratio(m.sum(axis=0))),
        "interval": np.quantile(boot, [0.025, 0.975]).tolist(),
        "buildings": len(m),
    }


tx = pd.read_parquet(
    c.OUT + "s7_text.parquet", columns=["listing_id", "dup_unit", "out_sqft"]
)
tx["listing_id"] = tx.listing_id.astype(str)
fl = pd.read_parquet(FLAGS, columns=["listing_id", "private_outdoor"])
fl["listing_id"] = fl.listing_id.astype(str)
d = c.rows()
d["listing_id"] = d.listing_id.astype(str)
n_rows = len(d)
d = d.merge(tx, on="listing_id", how="left").merge(fl, on="listing_id", how="left")
assert len(d) == n_rows
d["dup"] = d.dup_unit.fillna(False).astype(bool)
d = d.sort_values(["ukey", "priced", "listing_id"])
g = d.groupby("ukey")
d["prev_dup"] = g.dup.shift(1)
d["prev_beds"] = g.bedrooms.shift(1)
d = d.sort_index()
h = c.heldout(d)
del d
assert h.building.notna().all()
b = h.building.to_numpy()
on = h.dup.to_numpy()
h["cg"] = h.gap.clip(-0.4, 0.4)
h["sq"] = h.cg**2
h["n_b"] = n_in(b)
scale = loo_scale(h.n_b.to_numpy())
h["wsq_raw"] = c.within(h.cg, b) ** 2
h["wsq"] = h.wsq_raw * scale
h["wsq_own"] = own_var(h.cg, b)
h["wgap_raw"] = c.within(h.gap, b)
h["wgap"] = h.wgap_raw * scale
res = {
    "heldout": len(h),
    "dup": int(on.sum()),
    "alone_dup": float((h.n_b[on] == 1).mean()),
    "alone_rest": float((h.n_b[~on] == 1).mean()),
}

# 1. s7c as it ran
r = {
    "sq_diff": diff(h.sq, on, b),
    "within_sq_diff": diff(h.wsq_raw, on, b),
}
r["share"] = r["within_sq_diff"][0] / r["sq_diff"][0]
res["s7c_as_run"] = r

# 2. buildings with 2 or more held-out ads, and 3. with 3 or more
for k, lo in (("two_plus", 2), ("three_plus", 3)):
    m = h.n_b.to_numpy() >= lo
    x, o, bb = h[m], on[m], b[m]
    r = {
        "ads": int(m.sum()),
        "dup": int(o.sum()),
        "buildings": int(len(np.unique(bb))),
        "sq_on": float(x.sq[o].mean()),
        "sq_off": float(x.sq[~o].mean()),
        "sq_diff": diff(x.sq, o, bb),
        "within_raw_diff": diff(x.wsq_raw, o, bb),
        "within_diff": diff(x.wsq, o, bb),
        "within_on": float(x.wsq[o].mean()),
        "within_off": float(x.wsq[~o].mean()),
    }
    r["share_raw"] = r["within_raw_diff"][0] / r["sq_diff"][0]
    r["share"] = share(x.sq, x.wsq, o, bb, 20261114)
    if lo == 3:
        r["own_diff"] = diff(x.wsq_own, o, bb)
        r["own_on"] = float(x.wsq_own[o].mean())
        r["own_off"] = float(x.wsq_own[~o].mean())
        r["own_share"] = share(x.sq, x.wsq_own, o, bb, 20261115)
    res[k] = r
print(json.dumps(res, indent=1), flush=True)

# 4. part A's level within building
sized = h.square_feet.notna().to_numpy()
res["level"] = {}
for k, m in (("all", np.ones(len(h), bool)), ("sized", sized), ("unsized", ~sized)):
    x, o, bb = h[m], on[m], b[m]
    two = x.n_b.to_numpy() >= 2
    res["level"][k] = {
        "dup": int(o.sum()),
        "dup_in_two_plus": int((o & two).sum()),
        "diff": diff(x.gap, o, bb),
        "within_as_run": diff(x.wgap_raw, o, bb),
        "within_loo": diff(x.wgap, o, bb),
        "within_fe": list(
            c.wls_slope(c.within(x.gap, bb), c.within(o.astype(float), bb), bb)[:2]
        ),
    }
print(json.dumps(res["level"], indent=1), flush=True)

# 5. part C's table by the unit's previous ad
h["prev"] = np.where(
    h.prev_dup.fillna(False).astype(bool),
    "previous ad duplex",
    "previous ad not duplex",
)
h["beds"] = np.where(h.bedrooms.eq(h.prev_beds), "same bedrooms", "other bedrooms")


def cells(x, by):
    out = []
    for key, v in x.groupby(by):
        t = v[v.n_b >= 2]
        out.append(
            {
                "key": " | ".join(np.atleast_1d(key).astype(str)),
                "n": len(v),
                "sq": float(v.sq.mean()),
                "in80": float(v.in80.mean()),
                "n_two_plus": len(t),
                "sq_two_plus": float(t.sq.mean()),
                "within": float(t.wsq.mean()),
                "within_se": mean_se(t.wsq, t.building)[1],
            }
        )
    return out


res["by_previous"] = cells(h[on], ["prev", "beds"]) + cells(h[~on], "beds")
print(pd.DataFrame(res["by_previous"]).round(4).to_string(), flush=True)

# 6a. S7's outdoor size among held-out ads with the private outdoor flag
po = h[h.private_outdoor.fillna(False).astype(bool)].copy()
pb = po.building.to_numpy()
po["wgap_raw"] = c.within(po.gap, pb)
po["n_po"] = n_in(pb)
po["wgap"] = po.wgap_raw * loo_scale(po.n_po.to_numpy())
po["bin"] = pd.cut(
    po.out_sqft, [0, 100, 300, 700, 5000], labels=["<100", "100-300", "300-700", "700+"]
).astype(str)
st = po[po.out_sqft.notna()].copy()
sb = st.building.to_numpy()
lx = np.log2(st.out_sqft.to_numpy())
st_n = n_in(sb)
res["outdoor"] = {
    "ads": len(st),
    "alone_among_flagged": float((st.n_po == 1).mean()),
    "slope_as_run": list(c.wls_slope(st.wgap_raw, lx, sb)[:2]),
    "slope_gap": list(c.wls_slope(st.gap, lx, sb)[:2]),
    "slope_fe": list(c.wls_slope(c.within(st.gap, sb), c.within(lx, sb), sb)[:2]),
    "fe_ads": int((st_n >= 2).sum()),
    "fe_buildings": int(len(np.unique(sb[st_n >= 2]))),
    "bins": [
        {
            "bin": k,
            "n": len(v),
            "gap": float(v.gap.mean()),
            "within_as_run": float(v.wgap_raw.mean()),
            "n_loo": int(v.wgap.notna().sum()),
            "within_loo": mean_se(v.wgap, v.building)[0],
            "within_loo_se": mean_se(v.wgap, v.building)[1],
        }
        for k, v in st.groupby("bin")
    ],
}
print(json.dumps(res["outdoor"], indent=1), flush=True)

# 6b. S4's deciles of the building's competing ads per residential unit
s4 = pd.read_parquet(c.OUT + "s4_counts.parquet", columns=["listing_id", "bld60_per"])
s4["listing_id"] = s4.listing_id.astype(str)
assert s4.listing_id.is_unique
x = h[["listing_id"]].merge(s4, on="listing_id", how="left").bld60_per
assert len(x) == len(h)
ok = x.notna()
pos = ok & (x > 0)
lab = pd.Series("none", index=x.index).where(ok, "missing")
lab[pos] = pd.qcut(x[pos].rank(method="first"), 10, labels=False).astype(str)
lab = lab.to_numpy()
res["s4"] = []
for k in sorted(set(lab)):
    m = lab == k
    xt = c.within(m.astype(float), b)
    # a bin set by the building alone, like "missing", has no contrast within building
    fe = list(c.wls_slope(h.wgap_raw, xt, b)[:2]) if np.abs(xt).max() > 1e-9 else None
    res["s4"].append(
        {
            "bin": k,
            "n": int(m.sum()),
            "gap": float(h.gap[m].mean()),
            "within_as_run": float(h.wgap_raw[m].mean()),
            "n_loo": int((m & (h.n_b.to_numpy() >= 2)).sum()),
            "within_loo": mean_se(h.wgap[m], b[m])[0],
            "within_loo_se": mean_se(h.wgap[m], b[m])[1],
            "fe_vs_rest": fe,
        }
    )
print(pd.DataFrame(res["s4"]).to_string(), flush=True)

# 6c. j9's new units, S7 parts A and B
r9 = json.load(open(J9 + "result.json"))
z9 = np.load(J9 + "posterior.npz")
d9 = pd.read_parquet(
    r9["dataset"] + "/rows.parquet", columns=["listing_id", "building", "latest_ask"]
)
h9 = d9[z9["heldout"]].reset_index(drop=True)
del d9
y9 = z9["kept/pred_y"]
assert np.allclose(np.log(h9.latest_ask.to_numpy(float)), y9, atol=1e-6)
h9["gap"] = y9 - z9["kept/pred_loc"].reshape(-1, len(y9)).mean(axis=0)
del z9
h9["listing_id"] = h9.listing_id.astype(str)
h9 = h9.merge(tx[["listing_id", "dup_unit"]], on="listing_id", how="left")
o9 = h9.dup_unit.fillna(False).astype(bool).to_numpy()
b9 = h9.building.to_numpy()
cg9 = h9.gap.clip(-0.4, 0.4)
n9 = n_in(b9)
s9 = loo_scale(n9)
sq9 = (cg9**2).to_numpy()
w9_raw = c.within(cg9, b9) ** 2
two9 = n9 >= 2
res["j9"] = {
    "heldout": len(h9),
    "dup": int(o9.sum()),
    "alone_dup": float((n9[o9] == 1).mean()),
    "alone_rest": float((n9[~o9] == 1).mean()),
    "sq_diff": diff(sq9, o9, b9),
    "within_sq_as_run": diff(w9_raw, o9, b9),
    "two_plus_ads": int(two9.sum()),
    "two_plus_dup": int((o9 & two9).sum()),
    "two_plus_sq_diff": diff(sq9[two9], o9[two9], b9[two9]),
    "two_plus_within_sq": diff((w9_raw * s9)[two9], o9[two9], b9[two9]),
    "level_within_as_run": diff(c.within(h9.gap, b9), o9, b9),
    "level_within_loo": diff(c.within(h9.gap, b9) * s9, o9, b9),
    "level_within_fe": list(
        c.wls_slope(c.within(h9.gap, b9), c.within(o9.astype(float), b9), b9)[:2]
    ),
}
print(json.dumps(res["j9"], indent=1), flush=True)
json.dump(res, open(OUT + "w1_within.json", "w"), indent=1, default=float)
