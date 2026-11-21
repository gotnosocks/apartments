"""Held-out ads of the latest-split run (l2bt) with the fields the note needs.

One row per held-out ad: the gap (log ask less the model's median), the building's half, the
unit's count of training ads, the building's first ad day, the unit label's line and floor,
the stated size, the floor plan images and the ad's text. Nothing here is computed from a
rent except the gap itself.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import drift_score, unit_features
from rentfrontier import run as R

OUT = Path("/data1/apartments/tmp/po-plan-type")
SEED = "plan-type-2026-11-20"
RUN = R.RUNS / "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"
TEXTS = "/data1/apartments/tmp/history-scan/texts-b9.parquet"


def half(building: str) -> str:
    """Half A is read, half B is kept for checks."""
    return "AB"[hashlib.sha1((SEED + building).encode()).digest()[0] & 1]


def label_parts(page: pd.Series) -> pd.DataFrame:
    """The unit label of each ad URL with its floor and line (`unit_features`)."""
    lab = unit_features.unit_label(page)
    fl = [unit_features.floor_and_line(x) for x in lab]
    return pd.DataFrame(
        {
            "label": lab.to_numpy(),
            "lab_floor": [f for f, _ in fl],
            "line": [ln for _, ln in fl],
        },
        index=page.index,
    )


def ad_fields(ads_path: str) -> pd.DataFrame:
    a = pd.read_parquet(
        ads_path,
        columns=[
            "listing_id",
            "page",
            "first_day",
            "square_feet",
            "label_floor",
            "floor_plans",
            "building",
        ],
    )
    a["listing_id"] = a.listing_id.astype(str)
    a["first_day"] = pd.to_datetime(a.first_day)
    a["plan"] = [x[0] if x is not None and len(x) else None for x in a.floor_plans]
    a["n_plans"] = [0 if x is None else len(x) for x in a.floor_plans]
    born = a.groupby("building").first_day.min().rename("bld_first_day")
    a = a.join(label_parts(a.page)).drop(columns=["floor_plans", "page"])
    return a.drop(columns="building"), born


if __name__ == "__main__":
    ds = drift_score.dataset_dir(RUN)
    man = json.loads((ds / "manifest.json").read_text())
    frame = pd.read_parquet(
        ds / "rows.parquet",
        columns=[
            "listing_id",
            "building",
            "unit_id",
            "neighbourhood",
            "price_at",
            "bedrooms",
            "full_baths",
            "half_baths",
        ],
    )
    s = np.load(RUN / "pred_scores.npz")
    held = s["heldout"]
    b = frame.building.astype(str)
    uk = b + "|" + frame.unit_id.astype(str)
    nu = uk[~held & frame.unit_id.notna().to_numpy()].value_counts()
    nb = b[~held].value_counts()
    h = frame[held].reset_index(drop=True)
    h["listing_id"] = h.listing_id.astype(str)
    assert (h.listing_id.to_numpy() == s["listing"].astype(str)).all()
    h["building"] = h.building.astype(str)
    h["pred"] = s["pred"]
    h["gap"] = s["y"] - s["pred"]
    h["cdf"] = s["cdf"]
    h["n_unit"] = nu.reindex(uk[held].to_numpy()).fillna(0).astype(int).to_numpy()
    h["n_bld"] = nb.reindex(h.building).fillna(0).astype(int).to_numpy()
    h["half"] = h.building.map(half)
    h["day"] = pd.to_datetime(h.price_at, utc=True).dt.tz_localize(None)
    a, born = ad_fields(man["build"]["ads"]["path"])
    h = h.merge(a, on="listing_id", how="left")
    h["bld_first_day"] = born.reindex(h.building).to_numpy()
    h["bld_age"] = (h.day - h.bld_first_day).dt.days / 365.25
    t = pd.read_parquet(TEXTS, columns=["listing_id", "description"])
    t["listing_id"] = t.listing_id.astype(str)
    h = h.merge(t, on="listing_id", how="left")
    assert len(h) == held.sum()
    h.to_parquet(OUT / "l2_held.parquet")
    print("held-out ads", len(h), "buildings", h.building.nunique())
    print("by half", h.half.value_counts().to_dict())
    print(
        "with a text", h.description.notna().sum(), "with a line", h.line.notna().sum()
    )
    print(
        "with a floor plan",
        (h.n_plans > 0).sum(),
        "stated size",
        h.square_feet.notna().sum(),
    )
    print("unit new to training", (h.n_unit == 0).sum())
    print("ads per unit key", uk[held].value_counts().describe().round(2).to_dict())
    print(h.bld_age.describe().round(2).to_dict())
