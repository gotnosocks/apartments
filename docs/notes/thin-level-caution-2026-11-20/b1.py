"""l2bt latest-split run: per held-out ad, building level, support, gap."""

import json, hashlib
from pathlib import Path
import numpy as np, pandas as pd, pyarrow.parquet as pq
from rentfrontier import run as R, drift_score, drift_diagnostics

OUT = Path("/data1/apartments/tmp/po-thinlevel")
SEED = "thin-level-2026-11-20"


def half(b):
    return hashlib.sha1((SEED + b).encode()).digest()[0] & 1


d = R.RUNS / "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"
ds = drift_score.dataset_dir(d)
rec = json.loads((d / "result.json").read_text())
man = json.loads((ds / "manifest.json").read_text())
print(ds, man["build"]["ads"]["path"])
print(pq.read_schema(ds / "rows.parquet").names)
cols = [
    c
    for c in [
        "listing_id",
        "building",
        "unit_id",
        "neighbourhood",
        "bedrooms",
        "latest_ask",
        "latest_day",
        "first_day",
        "first_ask",
        "off_day",
        "description_known",
    ]
    if c in pq.read_schema(ds / "rows.parquet").names
]
frame = pd.read_parquet(ds / "rows.parquet", columns=cols)
s = np.load(d / "pred_scores.npz")
held = s["heldout"]
lv, why = drift_diagnostics.levels(d, rec, frame.building.astype(str).to_numpy())
assert lv is not None, why
b = frame.building.astype(str)
uk = b + "|" + frame.unit_id.astype(str)
tr = ~held
nb = b[tr].value_counts()
nu = uk[tr & frame.unit_id.notna().to_numpy()].value_counts()
lv["n_train"] = nb.reindex(lv.index).fillna(0).astype(int)
lv.reset_index().to_parquet(OUT / "l2_levels.parquet")
h = frame[held].reset_index(drop=True)
assert (h.listing_id.astype(str).to_numpy() == s["listing"]).all()
hb = h.building.astype(str).to_numpy()
hu = uk[held].to_numpy()
o = h.copy()
o["listing_id"] = o.listing_id.astype(str)
o["building"] = hb
o["unit_id"] = o.unit_id.astype(str)
o["pred"] = s["pred"]
o["y"] = s["y"]
o["cdf"] = s["cdf"]
o["gap"] = o.y - o.pred
o["unit_sd"] = s["unit_sd"]
o["level"] = lv.level.reindex(hb).to_numpy()
o["level_sd"] = lv.level_sd.reindex(hb).to_numpy()
o["zone"] = lv.zone.reindex(hb).to_numpy()
o["n_bld"] = nb.reindex(hb).fillna(0).astype(int).to_numpy()
o["n_unit"] = nu.reindex(hu).fillna(0).astype(int).to_numpy()
o["n_other"] = o.n_bld - o.n_unit
o["year"] = pd.to_datetime(o.latest_day).dt.year
o["half"] = [half(x) for x in hb]
o.to_parquet(OUT / "l2_ads.parquet")
print(len(o), o.level.isna().sum())
print(o[["gap", "cdf", "level", "level_sd", "n_bld", "n_other"]].describe().T.round(3))
# all training rows (both), slim, for later proxies
frame["heldout"] = held
frame[["listing_id", "building", "heldout"]].to_parquet(OUT / "l2_rows_slim.parquet")
