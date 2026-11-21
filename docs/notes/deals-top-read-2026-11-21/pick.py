"""Pick the read's ads from the published Deals page: the top 60 of its default view
(cautious saving, no cautions, no peer caution, not suspect, unit or building basis) and
60 controls from the middle of the same list. Writes picks.csv to the scratch folder."""

import sys
from pathlib import Path

import pandas as pd

from apartments.site import deals

SITE = Path("/data1/apartments/site")
OUT = Path(sys.argv[1])

data = deals.load(SITE)
rows = deals.choose(data["rows"])
print("default view", len(rows), "of", len(data["rows"]))
keep = [
    "listing_id",
    "building",
    "unit",
    "neighbourhood",
    "bedrooms",
    "baths",
    "square_feet",
    "floor",
    "ask",
    "model_median",
    "cautious_saving",
    "gap_pct",
    "below_share",
    "basis",
    "unit_ads",
    "building_ads",
    "days_on_market",
]
frame = pd.DataFrame([{k: r.get(k) for k in keep} for r in rows])
frame["rank"] = range(1, len(frame) + 1)
mid = len(frame) // 2
top = frame.head(60).assign(group="top")
ctrl = frame.iloc[mid - 30 : mid + 30].assign(group="middle")
pd.concat([top, ctrl]).to_csv(OUT / "picks.csv", index=False)
print(top[["rank", "ask", "model_median", "cautious_saving", "basis"]].describe())
print(ctrl[["rank", "cautious_saving"]].describe())
