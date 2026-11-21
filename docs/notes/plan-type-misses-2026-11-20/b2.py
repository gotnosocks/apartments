"""Open ads of the Deals backtest (range-j, priced on 2025-11-10) with the note's fields.

Starts from the table `docs/notes/turnover-low-asks-2026-11-18/turn_texts.py` wrote (the
backtest's held-out ads, their errors and texts) and adds the label's line and floor, the
stated size, the floor plan images and the building's first ad day from the ads table.
"""

import json

import pandas as pd

from b1 import OUT, ad_fields, half
from rentfrontier import drift_score
from rentfrontier import run as R

RUN = R.RUNS / "drift-building-bedtext-layout-range-b0-market-d9028c57-range-j"
SRC = "/data1/apartments/tmp/history-scan/backtest-range-j-texts.parquet"

if __name__ == "__main__":
    man = json.loads((drift_score.dataset_dir(RUN) / "manifest.json").read_text())
    h = pd.read_parquet(
        SRC,
        columns=[
            "listing_id",
            "building",
            "unit_id",
            "neighbourhood",
            "bedrooms",
            "full_baths",
            "half_baths",
            "cdf",
            "pred",
            "res",
            "un",
            "description",
        ],
    )
    h["listing_id"] = h.listing_id.astype(str)
    h["building"] = h.building.astype(str)
    h = h.rename(columns={"res": "gap"})
    h["n_unit"] = h.un.fillna(0).astype(int)
    h["half"] = h.building.map(half)
    h["day"] = pd.Timestamp("2025-11-10")
    a, born = ad_fields(man["build"]["ads"]["path"])
    h = h.merge(a, on="listing_id", how="left")
    h["bld_first_day"] = born.reindex(h.building).to_numpy()
    h["bld_age"] = (h.day - h.bld_first_day).dt.days / 365.25
    h.drop(columns="un").to_parquet(OUT / "bt_held.parquet")
    print("backtest ads", len(h), "buildings", h.building.nunique())
    print("by half", h.half.value_counts().to_dict())
    print("unit new to training", (h.n_unit == 0).sum())
    print(
        "with a line", h.line.notna().sum(), "with a floor plan", (h.n_plans > 0).sum()
    )
    print("building first ad within 3 years", (h.bld_age <= 3).sum())
