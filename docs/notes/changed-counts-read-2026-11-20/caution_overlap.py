"""Whether a caution for ads whose bedroom and bath counts are new to the unit would add
to the cautions the Deals page already has, on the Deals backtest. Run from the repo root
with PYTHONPATH=frontier/src. The mark is coded from counts and dates only, no ask."""

import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

N = Path(__file__).resolve().parent
sys.path.insert(0, str(N))
from build import half
from mark import BT
from newseen import cell, tvalue

from rentfrontier import drift_deals, drift_score

RUNS = Path("/data1/apartments/frontier/runs")
pd.set_option("display.width", 250)


def mark(run):
    ds = drift_score.dataset_dir(run)
    f = pd.read_parquet(
        ds / "rows.parquet",
        columns=[
            "listing_id",
            "building",
            "unit_id",
            "bedrooms",
            "full_baths",
            "half_baths",
            "price_at",
        ],
    )
    held = np.load(run / "posterior.npz")["heldout"].astype(bool)
    day = pd.to_datetime(f.price_at, utc=True)
    hb = f.half_baths.astype(float).to_numpy()
    baths = f.full_baths.astype(float).to_numpy() + 0.5 * np.where(np.isnan(hb), 0, hb)
    beds = f.bedrooms.astype(float).to_numpy()
    hist = defaultdict(list)
    for i in np.flatnonzero(~held):
        u = f.unit_id.iat[i]
        if u is None or (isinstance(u, float) and math.isnan(u)):
            continue
        hist[(f.building.iat[i], u)].append((day.iat[i], beds[i], baths[i]))
    out = []
    stats = defaultdict(int)
    for i in np.flatnonzero(held):
        u = f.unit_id.iat[i]
        if u is None or (isinstance(u, float) and math.isnan(u)):
            stats["unknown unit"] += 1
            out.append(False)
            continue
        if math.isnan(beds[i]) or math.isnan(baths[i]):
            stats["held missing count"] += 1
            out.append(False)
            continue
        e = [r for r in hist.get((f.building.iat[i], u), []) if r[0] < day.iat[i]]
        same_day = [
            r for r in hist.get((f.building.iat[i], u), []) if r[0] >= day.iat[i]
        ]
        if same_day:
            stats["has unit train row on/after"] += 1
        if not e:
            out.append(False)
            continue
        m = not any(r[1] == beds[i] and r[2] == baths[i] for r in e)
        if m and all(math.isnan(r[1]) or math.isnan(r[2]) for r in e):
            stats["marked only because earlier counts missing"] += 1
        if m and "~" in str(u):
            stats["marked with ~ piece"] += 1
        out.append(m)
    out = np.array(out)
    h = f[held].reset_index(drop=True)
    tl = set(f.listing_id[~held].astype(str))
    stats["held listing also a training row"] = int(
        h.listing_id.astype(str).isin(tl).sum()
    )
    stats["marked & listing also training"] = int(
        (h.listing_id.astype(str).isin(tl) & out).sum()
    )
    stats["held"] = len(h)
    stats["held days"] = str(sorted(set(day[held].dt.date.astype(str)))[:3]) + str(
        day[held].dt.date.nunique()
    )
    stats["train max day"] = str(day[~held].max())
    return f, h, held, out, dict(stats)


run = RUNS / BT
frame, h, held, mine, stats = mark(run)
print(stats)
frame, h, held = drift_deals._held_frame(run)
key = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
res = drift_score.score_run(run)
h = h.copy()
h["cdf"] = res["cdf"]
h["gap"] = np.log(h.latest_ask.to_numpy(float)) - res["pred"]
h["u"] = tvalue(h.cdf)
h["half"] = h.building.map(half)
market = drift_deals._manifest(run)
ads = Path(market["ads"])
a = drift_deals._ads(ads, h.listing_id)
codes, _ = drift_deals._run_cautions(run, frame, h, held, a, ads, None)
other = np.array([bool(c) for c in codes])
ru = np.array([bool({"rooms_up", "beds"} & set(c)) for c in codes])
h["grp"] = np.where(
    mine,
    np.where(other, "marked, other caution", "marked, no other caution"),
    np.where(other, "unmarked, cautioned", "unmarked, uncautioned"),
)
print(h.groupby("grp").apply(cell, include_groups=False).round(3).to_string())
g = h[mine & ~other]
print(
    "marked uncautioned: low n",
    int((g.cdf < 0.05).sum()),
    "high n",
    int((g.cdf > 0.95).sum()),
    "buildings",
    g.building.nunique(),
)
print(g.groupby("half").apply(cell, include_groups=False).round(3).to_string())
h["grp2"] = np.where(
    mine, np.where(ru, "marked, rooms_up/beds", "marked, neither"), "x"
)
print(h[mine].groupby("grp2").apply(cell, include_groups=False).round(3).to_string())
print(
    "marked with ~", int(pd.Series(key[held].to_numpy())[mine].str.contains("~").sum())
)
