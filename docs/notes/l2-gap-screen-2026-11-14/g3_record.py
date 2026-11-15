"""The slope of L2's held-out gap on the unit's training record `m`, by the months since the
unit's previous ad, by the count of its training ads and by the year, from `h.parquet`. A slope
growing with the months points to a unit level fading over time; a slope equal at every interval
points to a level the fit trusts too much. Also the median gap of each year among ads with `m`
near zero and one training ad or more."""

import json
import sys

import numpy as np
import pandas as pd

WT = sys.argv[1]
sys.path.insert(0, WT + "/docs/notes/causal-screens-2026-11-13")
import common as c  # noqa: E402

OUT = "/data1/apartments/tmp/sprint-20261114/gap-screen/"
h = pd.read_parquet(OUT + "h.parquet")
x = h[h.m.notna()].copy()
x["mc"] = x.m.clip(-0.4, 0.4)
res = {
    "m_sd": float(x.mc.std()),
    "with_m": int(len(x)),
    "median_gap_with_m": float(x.gap.median()),
    "median_gap_without_m": float(h.gap[h.m.isna()].median()),
}


def slopes(key):
    out = {}
    for k, v in x.groupby(key, observed=True):
        if len(v) > 200:
            s, se, a = c.wls_slope(v.gap, v.mc, v.building)
            out[str(k)] = {
                "n": int(len(v)),
                "slope": round(s, 4),
                "se": round(se, 4),
                "intercept_pct": round(100 * a, 3),
            }
    return out


res["all"] = c.wls_slope(x.gap, x.mc, x.building)
res["by_since"] = slopes("since_bin")
res["by_n_train"] = slopes("n_bin")
res["by_years"] = slopes("yrs")
res["by_sign"] = {
    "m<0": c.wls_slope(x.gap[x.m < 0], x.mc[x.m < 0], x.building[x.m < 0])[:2],
    "m>0": c.wls_slope(x.gap[x.m > 0], x.mc[x.m > 0], x.building[x.m > 0])[:2],
}
for n in ["1", "2", "3-4", "5-9"]:
    v = x[x.n_bin == n]
    res["by_since_n_" + n] = {
        k: r
        for k, r in (
            (k, c.wls_slope(g.gap, g.mc, g.building)[:2])
            for k, g in v.groupby("since_bin")
            if len(g) > 500
        )
    }
json.dump(res, open(OUT + "g3.json", "w"), indent=1)
print(json.dumps(res, indent=1))
