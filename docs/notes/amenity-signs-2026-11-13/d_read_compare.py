"""S12, part B's ad reading: join the readers' checklists to the key and compare each item's
rate between the over-predicted ads and the controls, over all codes and code by code."""

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "causal-screens-2026-11-13"))
import common as c  # noqa: E402

DIR = c.OUT + "s12read/"
read = pd.DataFrame(
    [
        json.loads(line)
        for p in sorted(glob.glob(DIR + "out*.jsonl"))
        for line in open(p)
    ]
).drop_duplicates("read_id")
key = pd.read_parquet(DIR + "key.parquet")
s = key.merge(read, on="read_id", how="left")
items = {
    "code_private": s.code_supported == "private",
    "code_shared_partial_absent": s.code_supported.isin(
        ["shared", "partial", "not_mentioned", "contradicted"]
    ),
    "finishes_dated": s.finishes == "dated_or_original",
    "finishes_unstated": s.finishes == "unstated",
    "finishes_new_or_updated": s.finishes.isin(["new_or_high_end", "updated"]),
    "renovation_stated": s.renovation_stated.astype(bool),
    "walkup_3plus": s.walkup_floor == "walkup_3plus",
    "light_bright": s.light == "bright",
    "size_layout_issue": s.size_layout_issue.astype(bool),
    "location_issue": s.location_issue.astype(bool),
    "seasonal_or_special": s.seasonal_or_special.astype(bool),
}
over = (s.group == "over").to_numpy()
out = {"read": int(s.code_supported.notna().sum()), "over": int(over.sum())}
rows = {}
for k, v in items.items():
    v = v.to_numpy(bool)
    p1, p0 = v[over].mean(), v[~over].mean()
    se = np.sqrt(p1 * (1 - p1) / over.sum() + p0 * (1 - p0) / (~over).sum())
    rows[k] = [
        round(100 * p1, 1),
        round(100 * p0, 1),
        round(100 * (p1 - p0), 1),
        round(100 * se, 1),
    ]
out["items"] = rows
by = {}
for code, g in s.groupby("code"):
    o = g.group == "over"
    by[code] = {
        "supported_over": g[o].code_supported.value_counts().to_dict(),
        "supported_control": g[~o].code_supported.value_counts().to_dict(),
        "finishes_over": g[o].finishes.value_counts().to_dict(),
        "finishes_control": g[~o].finishes.value_counts().to_dict(),
    }
out["by_code"] = by
out["lacks_over"] = s[over].sort_values("code")[["code", "lacks"]].values.tolist()
out["lacks_control"] = s[~over].sort_values("code")[["code", "lacks"]].values.tolist()
json.dump(out, open(c.OUT + "s12read.json", "w"), indent=1)
for k, v in rows.items():
    print(
        f"{k:30s} over {v[0]:5.1f} control {v[1]:5.1f} diff {v[2]:6.1f} se {v[3]:4.1f}"
    )
for code, v in by.items():
    print(code, v["supported_over"], v["supported_control"])
