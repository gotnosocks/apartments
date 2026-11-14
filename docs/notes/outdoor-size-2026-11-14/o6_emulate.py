"""Outdoor size, step 6: a level, a slope and a noise factor for the stated area, emulated
on L1's exact predictive.

This step asks how much of the screen's excess a fit could take back. I rescore
L1's held-out ads from its 272 kept draws with `Draws` of the causal screens
(`causal-screens-2026-11-13/common.py`), as S15 and S15b did for income ads: each draw's
location moves by a shift, or its noise scale and unit sd grow by a factor, and the ad's
gain is its log predictive density after the change less before it, on the same grid. Ads
with no area gain 0. The buildings fall in two halves by `common.heldout`'s fold; each half
takes the change picked on the other half's marked ads, and the two halves' gains add up.

The shifts come from least squares on the picking half, fit to the gap less the mean gap of
the kept held-out ads with no area, for three specs:

1. a level;
2. a level and log2 of the area over 500 sq ft;
3. those two and an indicator for ads the listing codes give no private outdoor space.

I fit each spec twice: plain, as the screen does, and weighted by 1/s^2, where s is L1's
80% interval width over 2 x 1.2816, since the likelihood gives the narrow ads more weight.
The gaps by quartile of s show where the excess falls.

L1's predictive has heavy tails, so a fit would set the coefficients closer to a robust
center than to a mean. For that I also pick each spec's coefficients from GRID, the point
with the largest gain over the picking half, as S15 picked its shift.

Then a factor k from FACTORS on the noise scale and unit sd: for all marked ads, and for
those of 300 sq ft or more. The picking half takes the k with the largest gain, alone and
after spec 3's grid-picked shift. SEs are clustered by building over the marked ads.

    python o6_emulate.py   # inside systemd-run --user --scope -p MemoryMax=3G
"""

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

RUN = Path(c.RUN)
DRAW = "/data1/apartments/tmp/blind-spots-2026-11-14/draw.parquet"
OUT = Path("/data1/apartments/tmp/outdoor-size-2026-11-14/")
CENTER = 500.0
SPECS = {"level": [0], "level_slope": [0, 1], "level_slope_uncoded": [0, 1, 2]}
FACTORS = np.round(np.arange(1.0, 2.01, 0.05), 2)
# Each spec's grid: the level at CENTER sq ft, the slope per doubling, the uncoded step.
GRID = {
    "level": (np.arange(-0.02, 0.0501, 0.0025), [0.0], [0.0]),
    "level_slope": (
        np.arange(-0.01, 0.0401, 0.005),
        np.arange(-0.004, 0.0161, 0.002),
        [0.0],
    ),
    "level_slope_uncoded": (
        np.arange(-0.01, 0.0401, 0.005),
        np.arange(-0.004, 0.0161, 0.002),
        np.arange(0.0, 0.0501, 0.01),
    ),
}

# o2_counts.py writes the areas, the held-out mask and po_coded in the order of L1's rows.
d = pd.read_parquet(OUT / "o2_areas.parquet")
a = np.load(RUN / "pred_scores.npz", allow_pickle=True)
qs = list(a["quantiles"])
h = d[d.held].reset_index(drop=True)
assert (h.listing_id.to_numpy() == a["listing"]).all()
h["gap"] = a["y"] - a["pred"]
h["s"] = (a["q"][:, qs.index(0.9)] - a["q"][:, qs.index(0.1)]) / (2 * norm.ppf(0.9))
h["fold"] = (pd.util.hash_array(h.building.astype(str).to_numpy()) % 2).astype(int)
drawn = h.listing_id.isin(set(pd.read_parquet(DRAW, columns=["listing_id"]).listing_id))
base = float(h.gap[~drawn & h.outdoor_sqft.isna()].mean())
idx = np.flatnonzero(~drawn & h.outdoor_sqft.notna())
m = h.iloc[idx]
X = np.column_stack(
    [np.ones(len(m)), np.log2(m.outdoor_sqft / CENTER), (~m.po_coded).astype(float)]
)
g = m.gap.to_numpy() - base
s = m.s.to_numpy()
fold = m.fold.to_numpy()
big = (m.outdoor_sqft >= 300).to_numpy()
buildings = m.building.to_numpy()
draws = c.Draws()


def solve(X, y, w):
    r = np.sqrt(w)
    return np.linalg.lstsq(X * r[:, None], y * r, rcond=None)[0]


def full(v):
    """`v` over the marked ads as an array over all held-out ads, 0 elsewhere."""
    out = np.zeros(len(h))
    out[idx] = v
    return out


def gains(shift=None, factor=None):
    """Each marked ad's gain with its location moved by `shift` and its noise and unit sd
    multiplied by `factor`, both arrays over the marked ads."""
    delta = None if shift is None else full(shift)
    scale = None if factor is None else full(factor - 1) + 1
    return draws.gain(idx, delta, scale)


def result(gain, **extra):
    return {
        "gain": float(gain.sum()),
        "gain_se": c.cluster_se(gain, buildings),
        **extra,
    }


out = {
    "ads": len(m),
    "buildings": int(m.building.nunique()),
    "base_gap": base,
    "median_s_marked": float(np.median(s)),
    "median_s_all": float(h.s[~drawn].median()),
    "plain_mean_gap": float(g.mean()),
    "weighted_mean_gap": float((g / s**2).sum() / (1 / s**2).sum()),
    "by_s_quartile": [
        {"s": str(k), "ads": int(len(v)), "gap": float(v.gap.mean() - base)}
        for k, v in m.groupby(pd.qcut(m.s, 4), observed=True)
    ],
}
for weights, w in (("plain", np.ones(len(m))), ("weighted", 1 / s**2)):
    for spec, cols in SPECS.items():
        shift, betas = np.zeros(len(m)), []
        for half in (0, 1):
            beta = solve(X[fold != half][:, cols], g[fold != half], w[fold != half])
            shift[fold == half] = X[fold == half][:, cols] @ beta
            betas.append([float(b) for b in beta])
        out[f"{weights}_{spec}"] = result(gains(shift), betas=betas)
    print(weights, "done", flush=True)

for spec, axes in GRID.items():
    points = [np.array(p) for p in itertools.product(*axes)]
    by_p = [gains(X @ p) for p in points]
    gain, shift3, picked = np.zeros(len(m)), np.zeros(len(m)), []
    for half in (0, 1):
        best = max(range(len(points)), key=lambda i: by_p[i][fold != half].sum())
        picked.append([round(float(b), 4) for b in points[best]])
        gain[fold == half] = by_p[best][fold == half]
        shift3[fold == half] = (X @ points[best])[fold == half]
    out[f"grid_{spec}"] = result(gain, picked=picked)
    print(spec, "grid done", flush=True)

for after in (False, True):
    shift = shift3 if after else np.zeros(len(m))
    for group, on in (("all", np.ones(len(m), bool)), ("300", big)):
        by_k = {k: gains(shift, np.where(on, k, 1.0)) for k in FACTORS}
        gain, picked = np.zeros(len(m)), []
        for half in (0, 1):
            pick = (fold != half) & on
            k = max(FACTORS, key=lambda k: by_k[k][pick].sum())
            picked.append(float(k))
            gain[fold == half] = by_k[k][fold == half]
        name = f"factor_{group}" + ("_after_shift" if after else "")
        out[name] = result(gain, ads=int(on.sum()), factors_picked=picked)
        print(name, "done", flush=True)

(OUT / "o6_emulate.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
