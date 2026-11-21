"""Held-out ads of the latest-split run (l2bt) whose counts differ from the apartment's
training ads, each with the training ad it is compared to.

"Counts changed" is the definition of `history-scan-2026-11-18/baths.py`: the apartment (the
unit id less its `~n` suffix, within a building) has training ads, and the held-out ad's
bedrooms or baths differ from at least one of them. The compared ad (`o_`) is the apartment's
most recent training ad with other counts. The previous ad (`p_`) is its most recent training
ad of any counts. The texts of the compared ads are read from the pipeline's records file.
Rents enter only as the gap columns (`gap`, `cdf`, `dlog_prev`, `dlog_other`), which no mark
and no reader is given.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import api_records, descriptions, drift_score, unit_features
from rentfrontier import run as R

OUT = Path("/data1/apartments/tmp/po-changed-counts")
SEED = "history-scan-2026-11-18"
RUN = R.RUNS / "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"
TEXTS = "/data1/apartments/tmp/history-scan/texts-b9.parquet"
COLS = ["listing_id", "building", "unit_id", "price_at", "latest_ask", "bedrooms"]
COLS += ["full_baths", "half_baths", "bed_text", "bed_text_fewer", "bed_text_more"]
COLS += ["bed_flex_at"]


def half(building: str) -> str:
    """The halves of buildings of the history scan (A is its half 0)."""
    return "AB"[hashlib.sha1((SEED + str(building)).encode()).digest()[0] % 2]


if __name__ == "__main__":
    ds = drift_score.dataset_dir(RUN)
    man = json.loads((ds / "manifest.json").read_text())
    r = pd.read_parquet(ds / "rows.parquet", columns=COLS)
    s = np.load(RUN / "pred_scores.npz")
    r["held"] = s["heldout"]
    r["listing_id"] = r.listing_id.astype(str)
    r["building"] = r.building.astype(str)
    r["day"] = pd.to_datetime(r.price_at, utc=True).dt.tz_localize(None)
    r["baths"] = r.full_baths + 0.5 * r.half_baths.fillna(0)
    r["apt"] = r.unit_id.str.replace(r"~\d+$", "", regex=True)
    r["lask"] = np.log(r.latest_ask.astype(float))
    h = r[r.held].reset_index(drop=True)
    assert (h.listing_id.to_numpy() == s["listing"].astype(str)).all()
    h["gap"] = s["y"] - s["pred"]
    h["cdf"] = s["cdf"]
    t = r[~r.held & r.apt.notna()]
    u = t.groupby(["building", "apt"]).agg(
        un=("day", "size"),
        bath_lo=("baths", "min"),
        bath_hi=("baths", "max"),
        bed_lo=("bedrooms", "min"),
        bed_hi=("bedrooms", "max"),
    )
    h = h.merge(u, left_on=["building", "apt"], right_index=True, how="left")
    same = (h.baths == h.bath_lo) & (h.baths == h.bath_hi)
    same &= (h.bedrooms == h.bed_lo) & (h.bedrooms == h.bed_hi)
    h["kind"] = np.where(
        h.un.isna(),
        "no unit history",
        np.where(same, "counts as before", "counts changed"),
    )
    h["half"] = h.building.map(half)
    h["year"] = h.day.dt.year
    print("held-out", len(h), h.kind.value_counts().to_dict())
    h.drop(columns=["price_at", "latest_ask", "lask"]).to_parquet(OUT / "held.parquet")

    c = h[h.kind == "counts changed"]
    keep = ["listing_id", "day", "bedrooms", "baths", "lask"]
    m = c[["listing_id", "building", "apt", "bedrooms", "baths", "lask"]].merge(
        t[["building", "apt", *keep]], on=["building", "apt"], suffixes=("", "_t")
    )
    m = m.sort_values("day")
    prev = m.groupby("listing_id").tail(1).set_index("listing_id")
    diff = m[(m.bedrooms != m.bedrooms_t) | (m.baths != m.baths_t)]
    oth = diff.groupby("listing_id").tail(1).set_index("listing_id")
    c = c.set_index("listing_id")
    for pre, f in (("p_", prev), ("o_", oth)):
        c[pre + "listing"] = f.listing_id_t.reindex(c.index)
        c[pre + "day"] = f.day.reindex(c.index)
        c[pre + "bedrooms"] = f.bedrooms_t.reindex(c.index)
        c[pre + "baths"] = f.baths_t.reindex(c.index)
        c[pre + "lask"] = f.lask_t.reindex(c.index)
    c["n_other"] = diff.groupby("listing_id").size().reindex(c.index)
    c = c.reset_index()
    a = pd.read_parquet(
        man["build"]["ads"]["path"],
        columns=["listing_id", "page", "square_feet", "first_day", "off_day"],
    )
    a["listing_id"] = a.listing_id.astype(str)
    a["label"] = unit_features.unit_label(a.page).to_numpy()
    a = a.drop_duplicates("listing_id").set_index("listing_id")
    for pre, key in (("", "listing_id"), ("o_", "o_listing"), ("p_", "p_listing")):
        for col in ("page", "square_feet", "label", "first_day", "off_day"):
            c[pre + col] = a[col].reindex(c[key]).to_numpy()
    tx = pd.read_parquet(TEXTS, columns=["listing_id", "description"])
    tx["listing_id"] = tx.listing_id.astype(str)
    c["text"] = tx.set_index("listing_id").description.reindex(c.listing_id).to_numpy()
    ids = set(c.o_listing.dropna())
    records = api_records.records_file()
    print("records", records["path"], "compared ads wanted", len(ids), flush=True)
    d = descriptions.record_descriptions(records, ids)
    c["o_text"] = d.description.reindex(c.o_listing).to_numpy()
    c.to_parquet(OUT / "changed.parquet")
    print("changed", len(c), "from 2022", (c.year >= 2022).sum())
    print("texts: held", c.text.notna().sum(), "compared", c.o_text.notna().sum())
    print("previous ad has other counts", (c.p_listing == c.o_listing).mean().round(3))
