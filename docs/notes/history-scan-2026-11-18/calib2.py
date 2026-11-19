"""Free check: a wider predictive, and a shift, for groups of held-out ads by counts and rent tier.

The method of docs/notes/duplex-scale-2026-11-18/calib.py: each held-out predictive is
approximated by a Student-t centred on its median with the scale from its quartiles; the
group's distributions are widened m times (and moved by d), with m and d picked on one half
of the buildings and scored on the other, both ways.
"""

import sys

import numpy as np
import pandas as pd
from scipy.stats import t as student

run, tag, y0 = sys.argv[1], sys.argv[2], int(sys.argv[3])
h = pd.read_parquet(f"baths-{tag}.parquet")
p = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
q = p["q"].astype(float)
sc = pd.DataFrame(
    {
        "listing_id": p["listing"],
        "elpd": p["elpd"],
        "pred": p["pred"],
        "iqr": q[:, 4] - q[:, 3],
    }
)
h = h.merge(sc, on="listing_id", validate="1:1")
h = h[h.year >= y0].reset_index(drop=True)
h["tier"] = h.groupby("year").pred.transform(
    lambda x: pd.qcut(x, [0, 0.25, 0.5, 0.75, 0.9, 0.97, 1], labels=False)
)
best = None
for df in (2, 2.5, 3, 4, 5, 7, 10, 30):
    s = h.iqr / (2 * student.ppf(0.75, df))
    lp = student.logpdf(h.res / s, df) - np.log(s)
    if best is None or abs(lp.mean() - h.elpd.mean()) < best[0]:
        best = (abs(lp.mean() - h.elpd.mean()), df, s.to_numpy(), lp.mean())
_, df, s, lpm = best
print(
    run,
    "from",
    y0,
    "ads",
    len(h),
    "df",
    df,
    "approx mean log density",
    round(lpm, 4),
    "stored",
    round(h.elpd.mean(), 4),
)
MS = np.round(np.arange(0.8, 1.81, 0.05), 2)
DS = np.round(np.arange(-0.04, 0.0401, 0.005), 3)
res, cdf, bld, half = (
    h.res.to_numpy(),
    h.cdf.to_numpy(),
    h.building.to_numpy(),
    h.half.to_numpy(),
)
base = student.logpdf(res / s, df) - np.log(s)


def cluster_se(x, cluster):
    g = pd.Series(x).groupby(np.asarray(cluster)).sum()
    return float(np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum()))


def search(name, idx, shifts):
    gains = {
        (m, d): student.logpdf((res[idx] - d) / (s[idx] * m), df)
        - np.log(s[idx] * m)
        - base[idx]
        for m in MS
        for d in shifts
    }
    picked, per = {}, np.zeros(len(idx))
    for f in (0, 1):
        tot = {k: g[half[idx] != f].sum() for k, g in gains.items()}
        picked[f] = max(tot, key=tot.get)
        per[half[idx] == f] = gains[picked[f]][half[idx] == f]
    c = cdf[idx]
    print(
        f"{name:34} n {len(idx):6}  low {100 * (c < 0.05).mean():5.1f}%  high {100 * (c > 0.95).mean():5.1f}%  80% covers {100 * ((c > 0.1) & (c < 0.9)).mean():5.1f}%  picked {picked[0]} {picked[1]}  gain {per.sum():7.1f} (SE {cluster_se(per, bld[idx]):5.1f})"
    )


same = h.same.to_numpy(bool)
rng = np.random.default_rng(20261118)
plain = np.flatnonzero(same & (h.fb == 1) & (h.bd <= 3) & (h.tier < 5))
groups = {
    "control: 1 bath, counts as before": np.sort(
        rng.choice(plain, min(20_000, len(plain)), replace=False)
    ),
    "2 baths, counts as before": np.flatnonzero(same & (h.fb == 2)),
    "3+ baths, counts as before": np.flatnonzero(same & (h.fb >= 3)),
    "4+ bedrooms, counts as before": np.flatnonzero(same & (h.bd >= 4)),
    "top 3% tier, counts as before": np.flatnonzero(same & (h.tier == 5)),
    "tier 4 (90-97%), counts as before": np.flatnonzero(same & (h.tier == 4)),
    "3+ baths or top 3%, as before": np.flatnonzero(
        same & ((h.fb >= 3) | (h.tier == 5))
    ),
    "counts changed, 1 bath": np.flatnonzero(~same & (h.fb == 1)),
    "counts changed, 2 baths": np.flatnonzero(~same & (h.fb == 2)),
    "counts changed, 3+ baths": np.flatnonzero(~same & (h.fb >= 3)),
    "all 3+ baths": np.flatnonzero(h.fb >= 3),
    "all 2 baths": np.flatnonzero(h.fb == 2),
}
for label, shifts in (("scale only", (0.0,)), ("scale and shift", DS)):
    print("\n" + label)
    for name, idx in groups.items():
        search(name, idx, shifts)
