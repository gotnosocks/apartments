"""Outcomes of held-out ads by their place in the predictive distribution: days on the market
and cuts, by class of ad. A class whose low-place ads sit as long as ordinary ads is one the
model over-predicts; a class whose low-place ads go fast holds deals."""

import sys

import numpy as np
import pandas as pd

ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
tag, y0 = sys.argv[1], int(sys.argv[2])
h = pd.read_parquet(f"baths-{tag}.parquet")
a = pd.read_parquet(
    ADS,
    columns=[
        "listing_id",
        "label_floor",
        "elevator",
        "days_on_market",
        "status",
        "first_day",
        "off_day",
        "first_ask",
        "page_price",
        "months_free",
    ],
).drop_duplicates("listing_id")
h = h.merge(a, on="listing_id", how="left")
h = h[h.year >= y0].copy()
print("status", h.status.value_counts(dropna=False).head(8).to_dict())
days = (pd.to_datetime(h.off_day) - pd.to_datetime(h.first_day)).dt.days
print(
    "off_day known",
    days.notna().mean().round(3),
    "days_on_market known",
    h.days_on_market.notna().mean().round(3),
)
h["dom"] = days
h = h[h.dom.notna() & (h.dom >= 0) & (h.dom < 400)].copy()
h["cut"] = h.latest_ask < h.first_ask * 0.999 if "latest_ask" in h else np.nan
h["place"] = pd.cut(h.cdf, [0, 0.02, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0])
pd.set_option("display.width", 250)


def cell(g):
    return pd.Series(
        {
            "n": len(g),
            "median days": g.dom.median(),
            "mean log days": np.log1p(g.dom).mean(),
            "within 7": (g.dom <= 7).mean(),
            "within 14": (g.dom <= 14).mean(),
            "over 60": (g.dom > 60).mean(),
        }
    )


print("\nall, by place")
print(
    h.groupby("place", observed=True)
    .apply(cell, include_groups=False)
    .round(3)
    .to_string()
)
h["floor1"] = h.label_floor == 1
classes = {
    "ordinary (1 bath, counts as before, floor 2+)": h.same & (h.fb == 1) & ~h.floor1,
    "counts changed": ~h.same,
    "2 baths, counts as before": h.same & (h.fb == 2),
    "3+ baths": h.fb >= 3,
    "floor 1": h.floor1,
    "4+ bedrooms": h.bd >= 4,
}
h["p3"] = pd.cut(
    h.cdf,
    [0, 0.05, 0.25, 0.75, 1.0],
    labels=["below 5%", "5-25%", "25-75%", "above 75%"],
)
for name, m in classes.items():
    print("\n" + name)
    print(
        h[m]
        .groupby("p3", observed=True)
        .apply(cell, include_groups=False)
        .round(3)
        .to_string()
    )
