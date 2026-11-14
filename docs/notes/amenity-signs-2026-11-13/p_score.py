"""S12's photo pilot, the scores: the raters' ratings against each ad's group and L1's gap.

argv: DIR. The script joins the ratings in `DIR/ratings/*.jsonl` to `DIR/blind.parquet` and
`DIR/targets.parquet`. On the first rating of each ad it takes each group's mean of the
kitchen, the bath, their mean ("kb", over whichever of the two the ad has), the floors and
the building age, and the over-predicted less control gap with its two-sample SE, overall and
for each code. It takes the correlation of kb with L1's gap and the gap's slope on kb, the
rank correlation of the building age with PLUTO's era, and the agreement of the repeat
batch's ratings with the first ones. It writes `DIR/scores.json`."""

import glob
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats

ITEMS = ["kitchen", "bath", "kb", "floors", "building_age"]
# PLUTO's era bins in `b_between.py` (before 1900, 1900-39, 1940-79, 1980-99, 2000-09,
# 2010 on), on the raters' building age scale.
ERA_SCALE = {"0": 1, "1": 2, "2": 3, "3": 4, "4": 4, "5": 5}


def gap(v):
    """Over-predicted less control mean of `v` with its two-sample SE, and the counts."""
    o, c = v[v.group == "over"].iloc[:, 0].dropna(), v[v.group == "control"].iloc[:, 0]
    c = c.dropna()
    if len(o) < 2 or len(c) < 2:
        return None
    se = np.sqrt(o.var(ddof=1) / len(o) + c.var(ddof=1) / len(c))
    return {
        "over": round(float(o.mean()), 3),
        "control": round(float(c.mean()), 3),
        "diff": round(float(o.mean() - c.mean()), 3),
        "se": round(float(se), 3),
        "n": [len(o), len(c)],
    }


out = sys.argv[1]
r = pd.concat(
    [pd.read_json(f, lines=True) for f in sorted(glob.glob(f"{out}/ratings/*.jsonl"))],
    ignore_index=True,
)
r = r.drop_duplicates("label", keep="last")
b = pd.read_parquet(f"{out}/blind.parquet")
t = pd.read_parquet(f"{out}/targets.parquet")
t["listing_id"] = t.listing_id.astype(str)
r = r.merge(b, on="label", how="right")
for k in ITEMS[:2] + ITEMS[3:]:
    r[k] = pd.to_numeric(r[k], errors="coerce")
r["kb"] = r[["kitchen", "bath"]].mean(axis=1)
first = r[~r.repeat].merge(t, on="listing_id")
res = {
    "ads": len(first),
    "rated": int(first.photos.notna().sum()),
    "shown": {k: int(first[k].notna().sum()) for k in ITEMS},
}
codes = ["all", *sorted(first.code.unique())]
for code in codes:
    v = first if code == "all" else first[first.code == code]
    res[code] = {k: gap(v[[k, "group"]]) for k in ITEMS}
ok = first.kb.notna()
rho = stats.pearsonr(first.kb[ok], first.gap[ok])
slope = stats.linregress(first.kb[ok], first.gap[ok])
res["kb_gap"] = {
    "n": int(ok.sum()),
    "r": round(float(rho.statistic), 3),
    "slope_pct_per_point": [
        round(100 * float(slope.slope), 2),
        round(100 * float(slope.stderr), 2),
    ],
}
era = first.era_zone.str.split("|").str[0].map(ERA_SCALE)
ok = era.notna() & first.building_age.notna()
s = stats.spearmanr(first.building_age[ok], era[ok])
res["age_vs_pluto"] = {
    "n": int(ok.sum()),
    "rho": round(float(s.statistic), 3),
    "exact": round(float((first.building_age[ok] == era[ok]).mean()), 3),
}
again = r[r.repeat].merge(
    r[~r.repeat][["listing_id", *ITEMS]], on="listing_id", suffixes=("", "_1")
)
res["repeat"] = {}
for k in ITEMS:
    both = again[k].notna() & again[k + "_1"].notna()
    d = (again[k] - again[k + "_1"])[both].abs()
    res["repeat"][k] = {
        "n": int(both.sum()),
        "within_1": round(float((d <= 1).mean()), 3) if both.any() else None,
        "mean_abs": round(float(d.mean()), 3) if both.any() else None,
    }
json.dump(res, open(f"{out}/scores.json", "w"), indent=1)
print(json.dumps(res, indent=1))
