"""Every ad of the live build with its area-median ratio, ledger status and run membership.

The universe is the ads file of the live Deals run's dataset (every ad the pipeline saw,
kept or not). Each ad gets:
- `ratio`: its ask over the median ask of the same neighbourhood, year and bedrooms in the
  live dataset's rows (the median of `building-level-read-2026-11-20/s4.py`);
- `status`: `ledger` when an active ledger exclude names it (in this build's `ledger_entries`,
  or in a ledger file decided after the build), `rule` when another pipeline rule dropped it,
  `train` when it is a training row of the live run, `live` when it is one of the run's
  held-out market ads (the Deals ads);
- `l2bt_held`: whether it is a held-out ad of the l2bt latest-split run.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from rentfrontier import drift_score
from rentfrontier import run as R

OUT = Path("/data1/apartments/tmp/commercial-sweep")
LEDGER = Path("/data1/apartments/tmp/pi-review/wt-commercial-sweep/pipeline/ledger")
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
LIVE = R.RUNS / "drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3"
L2 = R.RUNS / "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"


def ledger_excludes():
    """Active excludes by entry id: id -> (listing_id, reason, file)."""
    ex, retracted = {}, set()
    for p in sorted(LEDGER.glob("*.ndjson"), key=lambda p: p.name):
        for text in p.read_text(encoding="utf-8").split("\n"):
            if not text.strip():
                continue
            e = hashlib.sha256(text.encode()).hexdigest()[:16]
            j = json.loads(text)
            if j["change"] == "retract":
                retracted.add(j["entry"])
            elif j["change"] == "exclude":
                ex[e] = (str(j["listing_id"]), j["reason"], p.name)
    return {k: v for k, v in ex.items() if k not in retracted}


ex = ledger_excludes()
print("active ledger excludes", len(ex))
cols = [
    "listing_id",
    "unit_id",
    "building",
    "neighbourhood",
    "page",
    "bedrooms",
    "full_baths",
    "half_baths",
    "square_feet",
    "latest_ask",
    "first_day",
    "off_day",
    "fetched",
    "fate",
    "in_rows",
    "exclusion_reasons",
    "ledger_entries",
]
A = pd.read_parquet(ADS, columns=cols)
by_entry = {k: v[1] for k, v in ex.items()}
A["ledger_reason"] = [
    next((by_entry[e] for e in (es if es is not None else []) if e in by_entry), None)
    for es in A.ledger_entries
]
by_listing = {}
for lid, reason, _ in ex.values():
    by_listing.setdefault(lid, reason)
late = A.ledger_reason.isna() & A.listing_id.isin(by_listing)
A.loc[late, "ledger_reason"] = A.listing_id[late].map(by_listing)
A["ledger_late"] = late
print(
    "ads with a ledger exclude",
    A.ledger_reason.notna().sum(),
    "of them late",
    late.sum(),
)
A["rule_reasons"] = A.exclusion_reasons.map(
    lambda r: ",".join(r) if r is not None else ""
)
A = A.drop(columns=["ledger_entries", "exclusion_reasons"])

ds = drift_score.dataset_dir(LIVE)
f = pd.read_parquet(
    ds / "rows.parquet",
    columns=["listing_id", "neighbourhood", "bedrooms", "latest_ask", "latest_day"],
)
held = np.load(LIVE / "posterior.npz")["heldout"]
f["live_held"] = held
f["listing_id"] = f.listing_id.astype(str)
print("live rows", len(f), "unique listings", f.listing_id.nunique())
f["year"] = pd.to_datetime(f.latest_day).dt.year
med = (
    f.groupby(["neighbourhood", "year", "bedrooms"])
    .latest_ask.agg(["median", "size"])
    .reset_index()
    .rename(columns={"median": "nb_median", "size": "nb_n"})
)
g = (
    f.sort_values("latest_day")
    .groupby("listing_id")
    .agg(
        r_bed=("bedrooms", "last"),
        r_ask=("latest_ask", "last"),
        r_day=("latest_day", "last"),
        r_nb=("neighbourhood", "last"),
        live_held=("live_held", "max"),
        live_rows=("live_held", "size"),
    )
    .reset_index()
)
A = A.merge(g, on="listing_id", how="left")
A["in_live"] = A.r_bed.notna()
A["bed"] = A.r_bed.where(A.in_live, A.bedrooms)
A["ask"] = A.r_ask.where(A.in_live, A.latest_ask)
A["nb"] = A.r_nb.where(A.in_live, A.neighbourhood)
day = pd.to_datetime(A.r_day).where(
    A.in_live, pd.to_datetime(A.off_day).fillna(A.fetched.dt.tz_localize(None))
)
A["year"] = day.dt.year
A = A.merge(
    med.rename(columns={"neighbourhood": "nb", "bedrooms": "bed"}),
    on=["nb", "year", "bed"],
    how="left",
)
A["ratio"] = A.ask / A.nb_median
A["status"] = np.select(
    [
        A.ledger_reason.notna(),
        ~A.in_live,
        A.live_held.fillna(False).astype(bool),
    ],
    ["ledger", "rule", "live"],
    "train",
)
l2 = drift_score.dataset_dir(L2)
f2 = pd.read_parquet(l2 / "rows.parquet", columns=["listing_id"])
f2["h"] = np.load(L2 / "pred_scores.npz")["heldout"]
f2["listing_id"] = f2.listing_id.astype(str)
A["l2bt_held"] = A.listing_id.isin(set(f2.listing_id[f2.h]))
A["in_l2bt"] = A.listing_id.isin(set(f2.listing_id))
print(A.status.value_counts().to_dict())
print("ratio missing", A.ratio.isna().sum(), "l2bt held", A.l2bt_held.sum())
print(pd.crosstab(A.status, A.ledger_late))
A.drop(columns=["r_bed", "r_ask", "r_day", "r_nb"]).to_parquet(OUT / "ads.parquet")
