"""S17, part 1: the pool of studio-coded rows on units of 5 or more coded rooms, and a draw of 30.

I take L1's rows coded 0 bedrooms whose listing codes give 5 to 20 rooms, as S16's
`b6_studio_rooms.py` does, and mark each as held out or training with L1's gap and 80%
interval for the held-out ads. I leave S16's 400 drawn ads out of the pool, then draw 30
rows with a fixed seed, stratified by room count (5, 6, 7, 8 to 20) and by held-out against
training. Since the 7-room bin holds a single held-out ad outside S16's draw, the cells take
unequal counts (`TAKE`), and I keep each cell's size so later shares can be weighted back to
the 905.

I write `pool.parquet` (all 905 rows, with S16's drawn ones marked), `sample.parquet` (the 30)
and `draw.json` (cell sizes, takes and SHA-256s) to `OUT`."""

import hashlib
import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/studio-rooms-2026-11-14/"
S16 = "/data1/apartments/tmp/blind-spots-2026-11-14/"
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
DATA = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
)
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
SEED = 20261114
# Rows to draw from each cell, keyed by room bin and held-out (True) or training (False).
TAKE = {
    ("5", True): 5,
    ("6", True): 4,
    ("7", True): 1,
    ("8-20", True): 4,
    ("5", False): 5,
    ("6", False): 4,
    ("7", False): 3,
    ("8-20", False): 4,
}

cols = ["listing_id", "building", "unit_id", "bedrooms", "full_baths"]
d = pd.read_parquet(DATA, columns=[*cols, "latest_day", "latest_ask"])
a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
d["held"] = a["heldout"]
assert (d.listing_id[d.held].to_numpy() == a["listing"]).all()
qs = list(a["quantiles"])
d["pred"], d["gap"], d["in80"] = np.nan, np.nan, False
d.loc[d.held, "pred"] = a["pred"]
d.loc[d.held, "gap"] = a["y"] - a["pred"]
d.loc[d.held, "in80"] = (a["y"] >= a["q"][:, qs.index(0.1)]) & (
    a["y"] <= a["q"][:, qs.index(0.9)]
)
d = d.merge(
    pd.read_parquet(CODES, columns=["listing_id", "rooms"]), on="listing_id", how="left"
)
pool = d[(d.bedrooms == 0) & d.rooms.between(5, 20)].copy()
pool["bin"] = pd.cut(
    pool.rooms, [4, 5, 6, 7, 20], labels=["5", "6", "7", "8-20"]
).astype(str)
pool["s16_drawn"] = pool.listing_id.isin(
    set(pd.read_parquet(S16 + "draw.parquet").listing_id)
)
assert len(pool) == 905, len(pool)

rng = np.random.default_rng(SEED)
cells, picks = {}, []
for (b, h), n in TAKE.items():
    c = pool[(pool.bin == b) & (pool.held == h) & ~pool.s16_drawn].sort_values(
        "listing_id"
    )
    cells[f"{b}|{'held' if h else 'train'}"] = {"size": len(c), "take": n}
    picks.append(c.iloc[rng.choice(len(c), size=n, replace=False)])
sample = pd.concat(picks).reset_index(drop=True)
sample["cell"] = sample.bin + "|" + np.where(sample.held, "held", "train")
sample["weight"] = sample.cell.map({k: v["size"] / v["take"] for k, v in cells.items()})
sample.insert(0, "row_id", np.arange(len(sample)))

pool.to_parquet(OUT + "pool.parquet")
sample.to_parquet(OUT + "sample.parquet")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


info = {
    "seed": SEED,
    "pool_rows": len(pool),
    "pool_outside_s16": int((~pool.s16_drawn).sum()),
    "cells": cells,
    "sample_sha256": sha(OUT + "sample.parquet"),
    "pool_sha256": sha(OUT + "pool.parquet"),
}
json.dump(info, open(OUT + "draw.json", "w"), indent=1)
print(json.dumps(info, indent=1))
print(sample[["row_id", "listing_id", "cell", "rooms", "weight"]].to_string())
