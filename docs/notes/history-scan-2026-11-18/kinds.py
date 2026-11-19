"""The Deals model's backtest by its own count marks: what is left after the level terms.

For each held-out ad of the backtest run the script rebuilds the model's marks against the
apartment's previous training ad (`drift_building_bedtext_layout.changes`) and against the
range of its earlier training ads (`drift_building_bedtext_layout_range.marks`), then prints
the error, its spread in normal scores and the tail shares by mark. Scores come from the
frame `backtest.py` saved.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from rentfrontier import drift_building_bedtext_layout as lay
from rentfrontier import drift_building_bedtext_layout_range as rng
from rentfrontier import drift_deals

run = Path("/data1/apartments/frontier/runs") / sys.argv[1]
frame, h, held = drift_deals._held_frame(run)
held = np.asarray(held, bool)
prev = pd.DataFrame(
    lay.changes(frame, ~held)[held],
    columns=["bed_up", "bed_down", "bath_up", "bath_down"],
).astype(bool)
span = pd.DataFrame(
    rng.marks(frame, ~held)[held],
    columns=["bed_above", "bed_below", "bath_above", "bath_below"],
).astype(bool)
s = pd.read_parquet(sys.argv[2])[
    ["listing_id", "cdf", "res", "z", "half", "kind", "fb"]
]
h = pd.concat(
    [h[["listing_id", "building"]].reset_index(drop=True), prev, span], axis=1
).merge(s, on="listing_id", validate="1:1")
LOW = norm.ppf(0.05)
pd.set_option("display.width", 220)


def cell(g):
    bm = g.groupby("building").res.agg(["sum", "size"])
    se = np.sqrt(((bm["sum"] - bm["size"] * g.res.mean()) ** 2).sum()) / len(g)
    return pd.Series(
        {
            "n": len(g),
            "bld": g.building.nunique(),
            "res": g.res.mean(),
            "se": se,
            "sdz": g.z.std(),
            "low": (g.z < LOW).mean(),
            "high": (g.z > -LOW).mean(),
            "absres": g.res.abs().median(),
        }
    )


def tab(name, d, key):
    print(f"\n{name}")
    print(
        d.groupby(key, observed=True)
        .apply(cell, include_groups=False)
        .round(4)
        .to_string()
    )


anyprev = prev.any(axis=1).to_numpy()
anyspan = span.any(axis=1).to_numpy()
h["mark"] = np.select(
    [
        anyprev,
        anyspan,
        (h.kind == "counts as before").to_numpy(),
        (h.kind == "no unit history").to_numpy(),
    ],
    [
        "differs from the previous ad",
        "range mark only",
        "no mark, unit seen",
        "no unit history",
    ],
    "no mark, other",
)
print(
    "held",
    len(h),
    "previous-ad mark",
    int(anyprev.sum()),
    "range mark only",
    int((anyspan & ~anyprev).sum()),
)
tab("by mark", h, "mark")
tab("by mark and half of buildings", h, ["mark", "half"])
for c in prev.columns:
    tab(f"previous-ad mark {c}", h[h[c]], "half")
    tab(f"previous-ad mark {c}, all", h[h[c]], c)
only = h[~anyprev]
for c in span.columns:
    tab(f"range mark {c}, no previous-ad mark", only[only[c]], c)
tab("previous-ad mark, by full baths", h[anyprev], "fb")
tab("range mark only, by full baths", h[anyspan & ~anyprev], "fb")
