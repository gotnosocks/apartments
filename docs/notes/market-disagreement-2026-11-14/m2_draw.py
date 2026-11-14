"""Market disagreement, part 2: the frozen draw of 4 groups of 100 ads.

The script walks each group's pool from `outcomes.parquet` in its order, taking at most 3 ads
from a building in a group and skipping ads already taken by an earlier group:

- A, cheap and slow: the lowest tenth of z, largest D first;
- B, cheap and fast: the lowest tenth of z with a RENTED ending, smallest D first;
- C, dear and fast: the highest tenth of z with a RENTED ending, smallest D first;
- R, random controls: all kept ads in a seeded random order.

A seeded random key breaks ties in D. The script refuses to overwrite `draw.parquet`, and
writes its SHA-256 beside it."""

import hashlib
import json
import os

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/market-disagreement-2026-11-14/"
SEED, N, CAP = 20261114, 100, 3

h = pd.read_parquet(OUT + "outcomes.parquet")
rng = np.random.default_rng(SEED)
h["tie"] = rng.random(len(h))
taken = set()


def walk(order):
    kept, per_b, passed = [], {}, 0
    for i in order:
        if i in taken:
            continue
        b = h.building.iat[i]
        if per_b.get(b, 0) >= CAP:
            passed += 1
            continue
        per_b[b] = per_b.get(b, 0) + 1
        kept.append(i)
        if len(kept) == N:
            break
    taken.update(kept)
    return kept, passed


pos = np.arange(len(h))
h["pos"] = pos
low, high, rented = h.tenth == 1, h.tenth == 10, h.status == "RENTED"
orders = {
    "A_cheap_slow": h[low].sort_values(["D", "tie"], ascending=[False, True]).pos,
    "B_cheap_fast": h[low & rented].sort_values(["D", "tie"]).pos,
    "C_dear_fast": h[high & rented].sort_values(["D", "tie"]).pos,
    "R_random": h.sort_values("tie").pos,
}
parts, info = [], {}
for name, order in orders.items():
    kept, passed = walk(order.to_numpy())
    g = h.iloc[kept].copy()
    g["group"] = name
    parts.append(g)
    info[name] = {
        "ads": len(g),
        "buildings": int(g.building.nunique()),
        "passed_by_cap": passed,
        "z": [float(g.z.min()), float(g.z.max())],
        "gap": [float(g.gap1.min()), float(g.gap1.median()), float(g.gap1.max())],
        "D": [float(g.D.min()), float(g.D.max())],
        "days_median": float(g.days.median()),
        "days90_mean": float(g.days90.mean()),
        "cut": float(g.cut.mean()),
        "status": g.status.value_counts().to_dict(),
        "boro": g.boro.value_counts().to_dict(),
    }
draw = pd.concat(parts).drop(columns=["tie", "pos"]).reset_index(drop=True)
assert draw.listing_id.is_unique and len(draw) == 4 * N
path = OUT + "draw.parquet"
if os.path.exists(path):
    raise SystemExit("draw.parquet exists; the draw is frozen")
draw.to_parquet(path)
info["sha256"] = hashlib.sha256(open(path, "rb").read()).hexdigest()
info["frozen_at"] = pd.Timestamp.now(tz="America/New_York").isoformat()
json.dump(info, open(OUT + "draw.json", "w"), indent=1)
print(json.dumps(info, indent=1))
