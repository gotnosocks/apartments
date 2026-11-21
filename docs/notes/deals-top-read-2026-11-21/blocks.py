"""Build one reading block per picked ad: coded fields from the pipeline ads file, the
whole ad text and unit details from the stored API record (the last one collected), and
for the top group the ask with the model's median and 90% interval.

Writes to the scratch folder:
  blocks_top/batch_N.txt   top ads with ask and model range, about 15 per batch
  blocks_blind/batch_N.txt top and middle ads shuffled, no ask, no model, no group
  fields.csv               the coded fields of every picked ad (kept in the repo)
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

S = Path(sys.argv[1])
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
FIELDS = [
    "listing_id",
    "building",
    "neighbourhood",
    "bedrooms",
    "full_baths",
    "half_baths",
    "square_feet",
    "advertised_floor",
    "physical_floor",
    "floors_above_ground",
    "elevator",
    "laundry_type",
    "doorman_type",
    "hvac_type",
    "pet_policy",
    "view_exposures",
    "window_exposures",
    "furnished",
    "short_term",
    "concession",
    "months_free",
    "lease_term",
    "page_price",
    "first_ask",
    "latest_ask",
    "from_text",
]

picks = pd.read_csv(S / "picks.csv", dtype={"listing_id": str})
q = pd.read_csv(S / "q90.csv", dtype={"listing_id": str})
ads = pd.read_parquet(
    ADS, columns=FIELDS, filters=[("listing_id", "in", list(picks.listing_id))]
)
ads = ads.drop_duplicates("listing_id").set_index("listing_id")
rec = pd.read_parquet(S / "records.parquet")
rec = rec[rec.outcome == "record"].sort_values("fetched")
rec["listing_id"] = rec.listing_id.astype(str)
last = rec.groupby("listing_id").record.last()


def unit_bits(j: dict) -> dict:
    pd_ = j.get("propertyDetails") or {}
    am = pd_.get("amenities") or {}
    pr = j.get("pricing") or {}
    addr = pd_.get("address") or {}
    return {
        "address": f"{addr.get('street')} {addr.get('displayUnit') or ''}".strip(),
        "unit_amenities": ", ".join(
            (am.get("list") or [])
            + [f"outdoor:{x}" for x in am.get("sharedOutdoorSpaceTypes") or []]
            + [f"doorman:{x}" for x in am.get("doormanTypes") or []]
        ),
        "rooms": pd_.get("roomCount"),
        "living_area": pd_.get("livingAreaSize"),
        "lease_months": pr.get("leaseTermMonths"),
        "net_effective": pr.get("netEffectiveRent"),
        "furnished_rent": pr.get("furnishedRent"),
        "fees": "; ".join(
            f"{f.get('typeLabel')} {(f.get('calculation') or {}).get('feeQuantifier')}"
            f" {(f.get('calculation') or {}).get('calculationType')}"
            for f in (pr.get("moveInFees") or []) + (pr.get("monthlyFees") or [])
        )[:300],
        "deposit": next(
            (
                (f.get("calculation") or {}).get("feeQuantifier")
                for f in pr.get("moveInFees") or []
                if f.get("typeLabel") == "Security deposit"
                and (f.get("calculation") or {}).get("calculationType") == "FLAT_FEE"
            ),
            None,
        ),
        "source_type": (j.get("listingSource") or {}).get("sourceType"),
        "floor_plans": len((j.get("media") or {}).get("floorPlans") or []),
        "photos": len((j.get("media") or {}).get("photos") or []),
        "available": j.get("availableAt"),
        "source": (j.get("legacy") or {}).get("sourceGroupLabel"),
        "description": j.get("description") or "",
    }


rows = []
for _, p in picks.iterrows():
    a = ads.loc[p.listing_id].to_dict() if p.listing_id in ads.index else {}
    j = json.loads(last[p.listing_id]) if p.listing_id in last.index else {}
    u = unit_bits(j)
    qq = q.set_index("listing_id").loc[p.listing_id]
    rows.append(
        {
            **p.to_dict(),
            **{k: a.get(k) for k in FIELDS[1:]},
            **u,
            "q05": qq.q05,
            "q95": qq.q95,
        }
    )
df = pd.DataFrame(rows)


def fmt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    if isinstance(v, (list, np.ndarray)):
        return ", ".join(map(str, v)) or "-"
    return str(v)


def block(r, key, priced):
    lines = [f"=== AD {key} ==="]
    lines.append(f"Address: {r.address} ({r.building}), {r.neighbourhood}")
    lines.append(
        f"Beds {fmt(r.bedrooms)}, full baths {fmt(r.full_baths)}, half baths "
        f"{fmt(r.half_baths)}, rooms {fmt(r.rooms)}, sq ft {fmt(r.square_feet)}"
    )
    lines.append(
        f"Floor (Deals page {fmt(r.floor)}, advertised {fmt(r.advertised_floor)}, "
        f"physical {fmt(r.physical_floor)}) "
        f"of {fmt(r.floors_above_ground)} floors; elevator {fmt(r.elevator)}; "
        f"doorman {fmt(r.doorman_type)}; laundry {fmt(r.laundry_type)}; "
        f"hvac {fmt(r.hvac_type)}; pets {fmt(r.pet_policy)}"
    )
    lines.append(
        f"Views {fmt(r.view_exposures)}; windows {fmt(r.window_exposures)}; "
        f"furnished {fmt(r.furnished)}; short term {fmt(r.short_term)}; lease months "
        f"{fmt(r.lease_months)}; months free {fmt(r.months_free)}"
    )
    lines.append(f"Unit amenities: {fmt(r.unit_amenities)}")
    fees = f"Fees: {fmt(r.fees)}; " if priced else ""
    lines.append(
        f"{fees}floor plans {r.floor_plans}; photos {r.photos}; available "
        f"{fmt(r.available)}; listed by {fmt(r.source)} ({fmt(r.source_type)})"
    )
    if priced:
        net = f"; page price {fmt(r.page_price)}; net effective {fmt(r.net_effective)}"
        lines.append(
            f"ASK ${r.ask:,.0f}/month{net}. MODEL median ${r.model_median:,.0f}, "
            f"90% interval ${r.q05:,.0f} to ${r.q95:,.0f} "
            f"(ask is {r.gap_pct:.0f}% under the median)"
        )
    lines.append("Ad text:")
    text = r.description.strip() or "(no text)"
    if not priced:
        text = re.sub(r"\$\s?[\d,.]+[kK]?", "$[amount]", text)
    lines.append(text)
    return "\n".join(lines) + "\n"


(S / "blocks_top").mkdir(exist_ok=True)
(S / "blocks_blind").mkdir(exist_ok=True)
top = df[df.group == "top"].reset_index(drop=True)
top["key"] = [f"T{i:02d}" for i in top["rank"]]
for b in range(4):
    part = top.iloc[b * 15 : (b + 1) * 15]
    (S / "blocks_top" / f"batch_{b + 1}.txt").write_text(
        "\n".join(block(r, r.key, True) for r in part.itertuples())
    )
rng = np.random.default_rng(20261121)
blind = df.iloc[rng.permutation(len(df))].reset_index(drop=True)
blind["key"] = [f"B{i:03d}" for i in range(len(blind))]
for b in range(8):
    part = blind.iloc[b * 15 : (b + 1) * 15]
    (S / "blocks_blind" / f"batch_{b + 1}.txt").write_text(
        "\n".join(block(r, r.key, False) for r in part.itertuples())
    )
blind[["key", "listing_id", "group"]].to_csv(S / "blind_key.csv", index=False)
keep = [c for c in df.columns if c not in ("description", "address")]
df[keep].to_csv(S / "fields.csv", index=False)
print(df.groupby("group").description.apply(lambda s: (s.str.len() > 0).sum()))
print(df.description.str.len().describe())
