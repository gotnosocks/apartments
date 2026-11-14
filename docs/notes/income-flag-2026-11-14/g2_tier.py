"""S15b, steps 3 to 5: a level by AMI tier against a wider spread on the held-out ads the
guarded `income_restricted_v2` marks, from L1's saved draws.

Each marked held-out ad goes in a bin by `ami_pct_text` and `ami_tiers_text` (bins fixed in
the note before any tier was read). For each bin and each level on GRID the script adds the
level to L1's location in every draw for the bin's ads and rescores them with
`common.Draws`. Each half of the buildings takes each bin's level with the largest total gain
over the other half's ads in that bin, or 0 if the other half has none, and is scored with it.

The script then:

- reruns S15's spread search on the same ads: m multiplies L1's noise scale and unit sd, on
  SCALES, picked by halves the same way;
- runs the spread search with the tier levels in place: for each half, the levels and then m
  are picked on the other half's ads, and the half is scored with both;
- compares the mean squared gap from L1's median before and after the cross-fit levels (a
  constant shift in every draw moves the median by the same amount);
- compares the mean gap of ads with a tier of 80 or less with that of ads above 130.

SEs are clustered by building over all held-out ads, as in `f1_screen.py`: per-ad gains,
zeros included, are demeaned over the held-out ads, summed by building, and
se = sqrt(G / (G - 1) * sum(t^2)). A difference of two gains takes the difference per ad.
Results go to `OUT/g2_tier.json`.

    systemd-run --user --scope -q -p MemoryMax=3G python g2_tier.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

COPY = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags"
)
OUT = Path("/data1/apartments/tmp/income-flag-2026-11-14")
GRID = np.round(np.arange(-1.00, 0.3001, 0.02), 2)
SCALES = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0, 2.5, 3.0)
BINS = ["50 or less", "51 to 80", "81 to 100", "101 to 130", "above 130"]
ORDER = BINS + ["several, none tied", "none stated"]


def tier_bin(pct, tiers):
    """S15b's bin for an ad with tier `pct` (NaN if none is tied) stating `tiers` tiers."""
    if tiers == 0:
        return "none stated"
    if pct != pct:
        return "several, none tied"
    return BINS[int(np.searchsorted([50, 80, 100, 130], pct, side="left"))]


def se_sum(x, b):
    """Building-clustered SE of sum(x), with x demeaned over all its entries."""
    x = np.asarray(x, float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    g = len(t)
    return float(np.sqrt(g / (g - 1) * (t**2).sum()))


def pick_levels(gains, bins, train):
    """Each bin's level with the largest total gain over the ads `train` in that bin."""
    out = {}
    for name in ORDER:
        on = (bins == name) & train
        if not on.any():
            out[name] = 0.0
            continue
        tot = {lv: float(g[on].sum()) for lv, g in gains.items()}
        out[name] = max(tot, key=tot.get)
    return out


d = pd.read_parquet(
    COPY / "rows.parquet",
    columns=[
        "listing_id",
        "building",
        "income_restricted_v2",
        "ami_pct_text",
        "ami_tiers_text",
    ],
)
d["listing_id"] = d.listing_id.astype(str)
d["held"] = np.load(c.RUN + "pred_scores.npz", allow_pickle=True)["heldout"]
h = c.heldout(d)
idx = np.flatnonzero(h.income_restricted_v2.to_numpy().astype(bool))
x = h.iloc[idx]
bins = np.array([tier_bin(p, t) for p, t in zip(x.ami_pct_text, x.ami_tiers_text)])
fold = x.fold.to_numpy()
b_all = h.building.to_numpy()
gap = x.gap.to_numpy()
dr = c.Draws()
n = len(h)


def spread(m):
    s = np.ones(n, dtype=np.float32)
    s[idx] = m
    return s


def shift(levels_of):
    """Per-ad shifts over all held-out ads, from a level per bin for each ad's half."""
    s = np.zeros(n, dtype=np.float32)
    s[idx] = [levels_of[f][b] for f, b in zip(fold, bins)]
    return s


def full(per):
    """Per-ad gains on `idx` as an array over all held-out ads, zeros elsewhere."""
    out = np.zeros(n)
    out[idx] = per
    return out


res = {
    "ads": len(idx),
    "buildings": int(pd.Series(x.building).nunique()),
    "in80": float(x.in80.mean()),
    "bins": {b: int((bins == b).sum()) for b in ORDER},
    "bins_by_half": {
        str(f): {b: int(((bins == b) & (fold == f)).sum()) for b in ORDER}
        for f in (0, 1)
    },
}

# The tier levels.
lvl_gain = {}
for lv in GRID:
    delta = np.full(n, lv, dtype=np.float32)
    lvl_gain[float(lv)] = dr.gain(idx, delta=delta)
levels = {f: pick_levels(lvl_gain, bins, fold != f) for f in (0, 1)}
per_tier = np.zeros(len(idx))
for f in (0, 1):
    for name in ORDER:
        on = (bins == name) & (fold == f)
        per_tier[on] = lvl_gain[levels[f][name]][on]
res["levels_by_half"] = {str(f): levels[f] for f in (0, 1)}
res["levels_all_ads"] = pick_levels(lvl_gain, bins, np.ones(len(idx), bool))
res["tier"] = {
    "gain": float(per_tier.sum()),
    "se": se_sum(full(per_tier), b_all),
    "by_bin": {},
}
for name in ORDER:
    on = bins == name
    res["tier"]["by_bin"][name] = {
        "ads": int(on.sum()),
        "mean_gap": float(gap[on].mean()) if on.any() else None,
        "in80": float(x.in80.to_numpy()[on].mean()) if on.any() else None,
        "gain": float(per_tier[on].sum()),
        "se": se_sum(full(np.where(on, per_tier, 0.0)), b_all),
    }
print("tier", json.dumps(res["tier"]), flush=True)

# The spread alone.
sc_gain = {m: dr.gain(idx, scale=spread(m)) for m in SCALES}
picked, per_sc = {}, np.zeros(len(idx))
for f in (0, 1):
    tot = {m: float(g[fold != f].sum()) for m, g in sc_gain.items()}
    picked[f] = max(tot, key=tot.get)
    per_sc[fold == f] = sc_gain[picked[f]][fold == f]
res["spread"] = {
    "picked": {str(f): picked[f] for f in (0, 1)},
    "grid_total": {str(m): float(g.sum()) for m, g in sc_gain.items()},
    "gain": float(per_sc.sum()),
    "se": se_sum(full(per_sc), b_all),
    "by_bin": {
        name: float(per_sc[bins == name].sum())
        for name in ORDER
        if (bins == name).any()
    },
}
print("spread", json.dumps(res["spread"]), flush=True)

# Both: the levels from the other half, then m on the other half with those levels.
per_both, m_both = np.zeros(len(idx)), {}
for f in (0, 1):
    train = fold != f
    delta = shift({0: levels[f], 1: levels[f]})
    g = {m: dr.gain(idx, delta=delta, scale=spread(m)) for m in SCALES}
    tot = {m: float(v[train].sum()) for m, v in g.items()}
    m_both[f] = max(tot, key=tot.get)
    per_both[fold == f] = g[m_both[f]][fold == f]
res["both"] = {
    "picked": {str(f): m_both[f] for f in (0, 1)},
    "gain": float(per_both.sum()),
    "se": se_sum(full(per_both), b_all),
    "over_spread": float((per_both - per_sc).sum()),
    "over_spread_se": se_sum(full(per_both - per_sc), b_all),
}
res["tier_less_spread"] = {
    "gain": float((per_tier - per_sc).sum()),
    "se": se_sum(full(per_tier - per_sc), b_all),
}
print("both", json.dumps(res["both"]), flush=True)

# The squared gap from L1's median before and after the cross-fit levels.
moved = gap - shift(levels)[idx]
res["squared_gap"] = {
    "before": float((gap**2).mean()),
    "after": float((moved**2).mean()),
    "narrowed": float(1 - (moved**2).mean() / (gap**2).mean()),
}
low = np.isin(bins, BINS[:2])
high = bins == "above 130"
res["low_vs_high"] = {"low_ads": int(low.sum()), "high_ads": int(high.sum())}
if low.any() and high.any():
    on = low | high
    diff, se = c.cluster_mean_diff(gap[on], low[on], x.building.to_numpy()[on])
    res["low_vs_high"] |= {
        "low_mean_gap": float(gap[low].mean()),
        "high_mean_gap": float(gap[high].mean()),
        "diff": diff,
        "se": se,
    }
print(json.dumps({k: res[k] for k in ("squared_gap", "low_vs_high")}), flush=True)
json.dump(res, open(OUT / "g2_tier.json", "w"), indent=1, default=str)
