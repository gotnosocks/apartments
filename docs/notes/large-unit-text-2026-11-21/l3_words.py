"""Large held-out ads (3+ bedrooms): share of each wording among high, low and mid, by half."""

import re
import duckdb, pandas as pd, pyarrow.parquet as pq

D = "/data1/apartments/tmp/any-unit/"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
h = pq.read_table(D + "heldout.parquet").to_pandas()
a = (
    pq.read_table(
        ADS,
        columns=["listing_id", "bedrooms"],
        filters=[("listing_id", "in", sorted(set(h.listing_id)))],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
x = h.merge(a, on="listing_id")
x = x[x.bedrooms >= 3].copy()
x["grp"] = "mid"
x.loc[x.low, "grp"] = "low"
x.loc[~x.cover90 & ~x.low, "grp"] = "high"
t = (
    pq.read_table(
        D + "texts.parquet",
        columns=["listing_id", "description"],
        filters=[("listing_id", "in", sorted(set(x.listing_id)))],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
P = {
    "full_floor": r"\b(?:full|entire|whole)[- ]floor\b|\bfloor[- ]through\b|\bone (?:unit|apartment) per floor\b",
    "gut_reno": r"\bgut[- ]?renovat|\bnewly renovated\b|\bbrand[- ]new (?:renovation|kitchen|apartment)|\bjust renovated\b|\bcompletely renovated\b",
    "reno_any": r"\brenovat",
    "private_elev": r"\b(?:private|keyed|key[- ]locked) elevator\b|\belevator (?:opens|opening) (?:directly )?in",
    "duplex": r"\b(?:duplex|triplex|two[- ]level|2[- ]level|multi[- ]level|bi[- ]level)\b",
    "townhouse": r"\btown ?house\b|\bbrownstone\b",
    "outdoor": r"\bprivate (?:terrace|balcony|roof|garden|patio|deck|outdoor)|\b(?:terrace|balcony|patio)\b",
    "wd": r"\bwasher\b|\bw/d\b|\bwasher[/ ]dryer\b",
    "corner": r"\bcorner (?:unit|apartment)\b|\bexposures?\b",
    "luxury": r"\bluxury\b|\bmarble\b|\bchef'?s kitchen\b|\bsub[- ]?zero\b|\bmiele\b|\bwine (?:fridge|cooler|refrigerator)\b",
    "share": r"\broommates?\b|\bshares? (?:ok|welcome|friendly)\b|\bstudents?\b|\bby the room\b|\bper room\b|\bfor rent by room\b",
    "flex": r"\bflex\b|\bconvertible\b|\bpressuri[sz]ed wall\b|\btemporary wall\b",
    "furnished": r"\bfurnished\b",
    "no_fee": r"\bno[- ]fee\b|\bno broker\b",
    "fee": r"\bbroker(?:'s)? fee\b|\bone month fee\b|\b(?:15|12)% fee\b",
    "house": r"\b(?:single[- ]family|entire house|whole house|detached|backyard|driveway)\b",
    "sqft": r"\b\d{1,2},?\d{3} ?(?:sq|square)",
}
low = t.description.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
for k, p in P.items():
    r = re.compile(p)
    t[k] = [bool(r.search(s)) for s in low]
x = x.merge(t.drop(columns="description"), on="listing_id", how="left").fillna(
    {k: False for k in P}
)
print({g: (x.grp == g).sum() for g in ["high", "low", "mid"]})
rows = []
for k in P:
    for half in "AB":
        y = x[x.half == half]
        s = y.groupby("grp")[k].mean()
        rows.append(
            (
                k,
                half,
                round(s.get("high", 0), 3),
                round(s.get("mid", 0), 3),
                round(s.get("low", 0), 3),
            )
        )
print(pd.DataFrame(rows, columns=["word", "half", "high", "mid", "low"]).to_string())
x.to_parquet("l3_marks.parquet")
