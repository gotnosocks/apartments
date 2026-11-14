"""S16, part 1: draw L1's largest misses on its held-out ads, with random controls, and freeze
the draw before anyone reads an ad.

For each of L1's 189,647 held-out ads of the latest split I take the gap, the log ask less L1's
predictive median, and divide it by a predictive scale. `pred_scores.npz` holds the quantiles
of L1's predictive sample, drawn from its 272 kept draws by `drift_score.score_rows`. The scale
is the width between the 25% and 75% quantiles divided by 1.349, the width of a standard
Normal's middle half, so it is the standard deviation a Normal predictive with the same
quartiles would have. L1's noise is a Student-t with nu near 1.7, so a scale from the
predictive's variance would be infinite or unstable, and the quartiles stay well defined.

The groups:

1. overpriced: the 150 ads with the largest standardized gap, walking down from the top;
2. underpriced: the 150 ads with the smallest, walking up from the bottom;
3. controls: 100 ads drawn at random, with seed 20261114, from the held-out ads in neither
   miss group.

Each walk keeps an ad only while its building has fewer than three kept ads in that group, and
counts the ads it passes over. The controls walk a random order of the eligible ads the same
way. The script writes `draw.parquet` and `draw.json` with the counts and the file's SHA-256.
It refuses to overwrite an existing draw."""

import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
OUT = "/data1/apartments/tmp/blind-spots-2026-11-14/"
N_MISS, N_CTRL, CAP, SEED = 150, 100, 3, 20261114

os.makedirs(OUT, exist_ok=True)
if os.path.exists(OUT + "draw.parquet"):
    sys.exit("draw.parquet exists; the draw is frozen")

a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
qs = list(a["quantiles"])
h = pd.DataFrame(
    {
        "listing_id": a["listing"].astype(str),
        "building": a["building"].astype(str),
        "day": a["day"],
        "y": a["y"],
        "pred": a["pred"],
        "q25": a["q"][:, qs.index(0.25)],
        "q75": a["q"][:, qs.index(0.75)],
        "q10": a["q"][:, qs.index(0.1)],
        "q90": a["q"][:, qs.index(0.9)],
        "cdf": a["cdf"],
        "elpd": a["elpd"],
    }
)
h["gap"] = h.y - h.pred
h["scale"] = (h.q75 - h.q25) / 1.349
h["z"] = h.gap / h.scale
assert np.isfinite(h.z).all() and (h.scale > 0).all()


def walk(order, n):
    """The first `n` ads of `order` (row positions of `h`), at most CAP a building, and the
    count of ads passed over on the way."""
    kept, per_b, passed = [], {}, 0
    for i in order:
        b = h.building.iat[i]
        if per_b.get(b, 0) >= CAP:
            passed += 1
            continue
        per_b[b] = per_b.get(b, 0) + 1
        kept.append(i)
        if len(kept) == n:
            break
    return kept, passed


z = h.z.to_numpy()
over, p_over = walk(np.argsort(-z, kind="stable"), N_MISS)
under, p_under = walk(np.argsort(z, kind="stable"), N_MISS)
miss = set(over) | set(under)
rng = np.random.default_rng(SEED)
pool = np.array([i for i in range(len(h)) if i not in miss])
ctrl, p_ctrl = walk(rng.permutation(pool), N_CTRL)

parts = []
for name, idx in (("overpriced", over), ("underpriced", under), ("control", ctrl)):
    s = h.iloc[idx].copy()
    s["group"] = name
    s["rank"] = np.arange(1, len(s) + 1)
    parts.append(s)
draw = pd.concat(parts).reset_index(drop=True)
draw.to_parquet(OUT + "draw.parquet")
sha = hashlib.sha256(open(OUT + "draw.parquet", "rb").read()).hexdigest()


def summary(g):
    s = draw[draw.group == g]
    return {
        "ads": len(s),
        "buildings": int(s.building.nunique()),
        "buildings_at_cap": int((s.building.value_counts() == CAP).sum()),
        "z_min": float(s.z.min()),
        "z_max": float(s.z.max()),
        "gap_min": float(s.gap.min()),
        "gap_max": float(s.gap.max()),
        "scale_median": float(s.scale.median()),
    }


res = {
    "heldout": len(h),
    "scale": "(q75 - q25) / 1.349 of L1's predictive sample, from pred_scores.npz",
    "scale_median_all": float(h.scale.median()),
    "z_quantiles_all": {
        str(p): float(np.quantile(h.z, p)) for p in (0.001, 0.01, 0.5, 0.99, 0.999)
    },
    "cap": CAP,
    "passed_over": {"overpriced": p_over, "underpriced": p_under, "control": p_ctrl},
    "seed": SEED,
    "groups": {g: summary(g) for g in ("overpriced", "underpriced", "control")},
    "sha256": sha,
}
json.dump(res, open(OUT + "draw.json", "w"), indent=1)
print(json.dumps(res, indent=1))
