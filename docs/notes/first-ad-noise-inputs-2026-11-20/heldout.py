"""Calibrated scale factors of the backtest's held-out ads, by input known on the first day.

Usage: heldout.py TAG (scores-TAG.parquet from score.py). The method of
docs/notes/history-scan-2026-11-18/calib2.py: each predictive is approximated by a
Student-t centred on its median with the scale from its quartiles, and a group's
distributions are widened m times. `m` is the factor of greatest likelihood within the half
(SE from 200 bootstrap draws of buildings); `gain` is the log density gained on the half
with m picked on the other half (SE clustered by building).
"""

import sys

import numpy as np
import pandas as pd
from common import OUT, bins, half
from scipy.stats import norm
from scipy.stats import t as student

h = pd.read_parquet(f"{OUT}/scores-{sys.argv[1]}.parquet")
t = pd.read_parquet(f"{OUT}/inputs.parquet")
h = h.merge(t[t.held], on="listing_id", validate="1:1", suffixes=("", "_t"))
h["half"] = half(h.building)
h["res"] = h.y - h.pred
h["z"] = norm.ppf(h.cdf.clip(1e-6, 1 - 1e-6))
iqr = (h.q750 - h.q250).to_numpy()
best = None
for df in (2, 2.5, 3, 4, 5, 7, 10, 30):
    s = iqr / (2 * student.ppf(0.75, df))
    lp = student.logpdf(h.res / s, df) - np.log(s)
    if best is None or abs(lp.mean() - h.elpd.mean()) < best[0]:
        best = (abs(lp.mean() - h.elpd.mean()), df, s, lp.mean())
_, df, s, lpm = best
print(sys.argv[1], "held-out ads", len(h), "t df", df)
print("approx mean log density", round(lpm, 4), "stored", round(h.elpd.mean(), 4))
MS = np.round(np.arange(0.5, 3.001, 0.01), 2)
res = h.res.to_numpy()
ll = np.stack([student.logpdf(res / (s * m), df) - np.log(s * m) for m in MS], 1)
ll -= ll[:, [np.flatnonzero(MS == 1.0)[0]]]
first = h.no_unit.to_numpy()
rs = lambda x: 1.4826 * np.median(np.abs(x - np.median(x)))  # noqa: E731
yard, mid = rs(res[first]), np.median(res[first])
print("first-ad ads: robust scale of the gap", round(yard, 4), "median", round(mid, 4))
print(
    "mean width of the 80% interval, first-ad",
    round((h.q900 - h.q100)[first].mean(), 3),
)
print(
    "mean width of the 80% interval, others", round((h.q900 - h.q100)[~first].mean(), 3)
)
rng = np.random.default_rng(20261120)
hf, bld, cdf, z = (
    h.half.to_numpy(),
    h.building.to_numpy(),
    h.cdf.to_numpy(),
    h.z.to_numpy(),
)


def fit(idx):
    """Factor of greatest likelihood on rows idx, with a building-bootstrap SE."""
    g = pd.DataFrame(ll[idx]).groupby(bld[idx]).sum().to_numpy()
    m = MS[g.sum(0).argmax()]
    draws = rng.integers(0, len(g), (200, len(g)))
    return m, np.std([MS[g[d].sum(0).argmax()] for d in draws]), len(g)


def line(name, mask):
    picked = {}
    for f in (0, 1):
        idx = np.flatnonzero(mask & (hf == f))
        picked[f] = fit(idx) if len(idx) >= 40 else None
    for f in (0, 1):
        idx = np.flatnonzero(mask & (hf == f))
        if picked[f] is None:
            print(f"{name:20} h{f} {len(idx):5}")
            continue
        m, se, nb = picked[f]
        c = cdf[idx]
        out = f"{name:20} h{f} {len(idx):5} {nb:5} {np.std(z[idx]):5.2f}"
        out += f" {100 * ((c > 0.1) & (c < 0.9)).mean():5.1f}"
        out += f" {100 * ((c > 0.025) & (c < 0.975)).mean():5.1f}"
        out += f" {100 * (np.abs(res[idx] - mid) > 6 * yard).mean():5.2f}"
        out += f" {m:5.2f} ({se:.2f})"
        if picked[1 - f] is not None:
            per = ll[idx, np.flatnonzero(MS == picked[1 - f][0])[0]]
            g = pd.Series(per).groupby(bld[idx]).sum()
            se = np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum())
            out += f" {per.sum():7.1f} ({se:.1f})"
        print(out)


print(
    "columns: group, half, ads, buildings, sd z, 80% cover, 95% cover, far6 %, m (SE),"
)
print("gain with the other half's m (SE)")
line("all held-out", np.ones(len(h), bool))
line("unit has earlier ad", ~first)
line("first-ad units", first)
b = bins(h)
for col in b:
    print(col + " (first-ad units)")
    for v in sorted(b[col].unique()):
        line("  " + v, first & (b[col] == v).to_numpy())
