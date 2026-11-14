"""S16, part 5: a text or field pattern for each flagged cause, counted over L1's dataset, and
30 matches of each drawn for a precision reader.

The flagged causes and their patterns:

1. `data_error`, its subtype `beds_low`, mostly coded studios, 11 of them on units of 5 to 8 rooms:
   - `studio_rooms`: a row coded with 0 bedrooms whose ad codes 4 to 20 rooms. L1 sees the
     rooms only through `ad:extra_rooms`, which is the rooms less the bedrooms less 1, capped
     at 6;
   - `studio_text_beds`: a row coded with 0 bedrooms whose latest description names at least 1
     bedroom ("2 bed", "three bedrooms", "1BR") or at least 4 rooms ("5 room duplex").
2. `data_error`, its subtype `nonresidential`: `nonresidential`, a description naming a
   storefront, a retail or commercial space, key money, a medical or professional office, a
   community facility, a nail salon or a restaurant space, unless the only such words are
   about ground-floor retail.
3. `private_outdoor`, the overpriced side:
   - `outdoor_uncoded`: a description naming a private, own or exclusive terrace, balcony,
     patio, garden, yard, roof deck or outdoor space, or a wraparound terrace, on an ad with
     none of the private-outdoor codes L1 reads;
   - `outdoor_large`: a stated outdoor area of at least 300 square feet, from S7's match
     (`causal-screens-2026-11-13/s7_text.py`), whatever the codes say.
4. `income_restricted_program`, the underpriced side: `income_v2_new`, the rows the rewritten
   `income_restricted_v2` of the text-flags work marks and L1's `income_restricted` misses. Its
   precision was read in that work, so it gets no new reader here.

For each pattern I count the rows of L1's dataset it marks, split into training rows and
held-out ads, with their units (building and unit_id, or the row alone) and buildings. On the
held-out ads I take L1's gap, the log ask less the predictive median, with its mean and a
building-clustered SE, its median, the spread of the gap (median absolute deviation) against
all held-out ads, and the share inside L1's 80% interval. I also cross the patterns with the
400 reads. Each of the first five patterns gets 30 matches drawn with seed 20261114 from the
rows with a description over 80 characters, written to `prec/<pattern>.jsonl` with dollar
figures masked as in part 2."""

import json
import os
import re

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

OUT = "/data1/apartments/tmp/blind-spots-2026-11-14/"
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
DATA = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
)
FLAGS = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags/rows.parquet"
)
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
RECS = "/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet"
S7 = "/data1/apartments/tmp/sprint-20261113/s7_text.parquet"
SEED, N_READ, MAXLEN = 20261114, 30, 3500

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
WORDS |= {"seven": 7, "eight": 8, "nine": 9}
BEDS = (
    r"(?i)\b(?P<n>[1-6]|one|two|three|four|five|six)[\s-]*"
    r"(?:bed(?:room)?s?|br|bdrm?s?)\b"
)
ROOMS = r"(?i)\b(?P<n>[4-9]|four|five|six|seven|eight|nine)[\s-]*rooms?\b"
NONRES = (
    r"(?i)\bstore ?front\b|\b(?:retail|commercial) (?:space|unit|store|condo|property|tenant"
    r"|lease|use)\b|\bkey money\b|\bmedical (?:office|space|suite)\b|\bprofessional office\b"
    r"|\bcommunity facility\b|\bnail salon\b|\brestaurant space\b"
)
GROUND_RETAIL = r"(?i)\bground[- ]floor (?:retail|commercial)\b"
SPACE = (
    r"(?:outdoor space|terrace|balcony|patio|garden|back ?yard|yard|roof ?deck|roof ?top"
    r"|deck)"
)
OUT_PRIV = (
    r"(?i)\bprivate " + SPACE + r"\b|\b(?:own|exclusive) (?:private )?" + SPACE + r"\b"
    r"|\bwrap[- ]?around (?:terrace|balcony)\b"
)
MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?\b|\bUSD\s?\d[\d,]*"
    r"|\b\d{1,2},?\d{3}(?:\.\d{2})?(?=\s*(?:/|per|a)\s*(?:mo\b|month))",
)

# L1's rows, its held-out ads and their gaps.
d = pd.read_parquet(
    DATA,
    columns=["listing_id", "building", "unit_id", "bedrooms", "full_baths"],
)
a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
d["held"] = a["heldout"]
assert (d.listing_id[d.held].to_numpy() == a["listing"]).all()
qs = list(a["quantiles"])
d["gap"], d["in80"] = np.nan, False
d.loc[d.held, "gap"] = a["y"] - a["pred"]
d.loc[d.held, "in80"] = (a["y"] >= a["q"][:, qs.index(0.1)]) & (
    a["y"] <= a["q"][:, qs.index(0.9)]
)
d["ukey"] = np.where(
    d.unit_id.isna(),
    "row:" + d.listing_id.astype(str),
    d.building.astype(str) + "|" + d.unit_id.astype(str),
)
po = [c for c in pq.read_schema(CODES).names if c.startswith("private_outdoor:")]
codes = pd.read_parquet(
    CODES, columns=["listing_id", "rooms", "feat:PRIVATE_OUTDOOR_SPACE", *po]
)
codes["po_coded"] = codes[["feat:PRIVATE_OUTDOOR_SPACE", *po]].fillna(0).max(axis=1) > 0
d = d.merge(codes[["listing_id", "rooms", "po_coded"]], on="listing_id", how="left")
fl = pd.read_parquet(
    FLAGS, columns=["listing_id", "income_restricted", "income_restricted_v2"]
)
d = d.merge(fl, on="listing_id", how="left")
s7 = pd.read_parquet(S7, columns=["listing_id", "out_sqft"])
d = d.merge(s7, on="listing_id", how="left")


# The latest description of each listing, matched a row group at a time.
def first_n(desc, pat):
    x = pc.struct_field(pc.extract_regex(desc, pat), "n").to_numpy(zero_copy_only=False)
    s = pd.Series(x, dtype=object).str.lower()
    return pd.to_numeric(s.map(lambda v: WORDS.get(v, v)), errors="coerce").to_numpy()


f = pq.ParquetFile(RECS)
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(g, columns=["listing_id", "last_collected_at", "description"])
    desc = pc.fill_null(t["description"], "")
    nonres = pc.match_substring_regex(desc, NONRES)
    ground = pc.match_substring_regex(desc, GROUND_RETAIL)
    parts.append(
        pd.DataFrame(
            {
                "listing_id": t["listing_id"].to_numpy(zero_copy_only=False),
                "t": t["last_collected_at"].to_numpy(zero_copy_only=False),
                "text_beds": first_n(desc, BEDS),
                "text_rooms": first_n(desc, ROOMS),
                "nonres": nonres.to_numpy(zero_copy_only=False),
                "ground": ground.to_numpy(zero_copy_only=False),
                "out_priv": pc.match_substring_regex(desc, OUT_PRIV).to_numpy(
                    zero_copy_only=False
                ),
                "desc_len": pc.utf8_length(desc).to_numpy(zero_copy_only=False),
            }
        )
    )
x = pd.concat(parts).sort_values("t").drop_duplicates("listing_id", keep="last")
d = d.merge(x.drop(columns="t"), on="listing_id", how="left")
d["desc_len"] = d.desc_len.fillna(0)

studio = d.bedrooms == 0
pat = {
    "studio_rooms": studio & d.rooms.between(4, 20),
    "studio_text_beds": studio & ((d.text_beds >= 1) | (d.text_rooms >= 4)),
    "nonresidential": d.nonres.fillna(False).astype(bool),
    "outdoor_uncoded": d.out_priv.fillna(False).astype(bool)
    & ~d.po_coded.fillna(False),
    "outdoor_large": d.out_sqft >= 300,
    "income_v2_new": d.income_restricted_v2.fillna(False).astype(bool)
    & ~d.income_restricted.fillna(False).astype(bool),
}
# Ground-floor retail wording alone doesn't count: RE2 has no lookahead, so the second match
# drops the rows where the only commercial words could be that phrase.
pat["nonresidential"] &= ~(d.ground.fillna(False).astype(bool))


def cluster_mean_se(v, b):
    v = np.asarray(v, float)
    t = pd.Series(v - v.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(v))


h = d[d.held]
mad_all = float(np.median(np.abs(h.gap - h.gap.median())))
res = {
    "held_all": {
        "ads": int(len(h)),
        "mad": mad_all,
        "in80": float(h.in80.mean()),
        "mean_gap": float(h.gap.mean()),
    }
}
draw = (
    pd.read_parquet(OUT + "labels.parquet")
    .merge(pd.read_parquet(OUT + "key.parquet"), on="read_id")
    .merge(pd.read_parquet(OUT + "draw.parquet")[["listing_id", "group"]])
)
draw["category"] = np.where(
    draw.subtype.isin(["", "unclear"]),
    draw.category,
    draw.category + "/" + draw.subtype,
)
for name, m in pat.items():
    m = m.fillna(False).astype(bool)
    mh = m & d.held
    gh = d.gap[mh]
    r = {
        "rows": int(m.sum()),
        "train": int((m & ~d.held).sum()),
        "heldout": int(mh.sum()),
        "units": int(d.ukey[m].nunique()),
        "buildings": int(d.building[m].nunique()),
        "with_text": int((m & (d.desc_len > 80)).sum()),
    }
    if mh.sum() > 1:
        r |= {
            "held_mean_gap": float(gh.mean()),
            "held_mean_gap_se": cluster_mean_se(gh, d.building[mh]),
            "held_median_gap": float(gh.median()),
            "held_mad_ratio": float(np.median(np.abs(gh - gh.median())) / mad_all),
            "held_in80": float(d.in80[mh].mean()),
        }
    hit = draw.listing_id.isin(set(d.listing_id[m]))
    r["draw"] = {
        f"{g}/{c}": int(n)
        for (g, c), n in draw[hit].groupby(["group", "category"]).size().items()
    }
    r["draw_hits"] = draw[hit].group.value_counts().to_dict()
    res[name] = r
    print(name, json.dumps(r))

# The precision reads: 30 matches of each pattern with a description over 80 characters.
recs_ids = {}
rng = np.random.default_rng(SEED)
for name in list(pat)[:5]:
    m = pat[name].fillna(False).astype(bool) & (d.desc_len > 80)
    pick = d.listing_id[m].to_numpy()
    recs_ids[name] = list(rng.choice(pick, size=min(N_READ, len(pick)), replace=False))
want = {i for v in recs_ids.values() for i in v}
texts = {}
for g in range(f.num_row_groups):
    t = f.read_row_group(g, columns=["listing_id", "last_collected_at", "description"])
    t = t.filter(pc.is_in(t["listing_id"], value_set=pc.cast(list(want), "string")))
    for r in t.to_pylist():
        k = r["listing_id"]
        if k not in texts or r["last_collected_at"] > texts[k][0]:
            texts[k] = (r["last_collected_at"], r["description"])
os.makedirs(OUT + "prec", exist_ok=True)
info = d.set_index("listing_id")
for name, ids in recs_ids.items():
    with open(OUT + f"prec/{name}.jsonl", "w") as fh:
        for i, lid in enumerate(ids):
            r = info.loc[lid]
            fields = {
                "bedrooms": None if pd.isna(r.bedrooms) else int(r.bedrooms),
                "full_baths": None if pd.isna(r.full_baths) else float(r.full_baths),
                "room_count": None if pd.isna(r.rooms) else int(r.rooms),
                "private_outdoor_coded": bool(pd.notna(r.po_coded) and r.po_coded),
            }
            fh.write(
                json.dumps(
                    {
                        "read_id": i,
                        "address": r.building,
                        "coded_fields": fields,
                        "description": MONEY.sub("[amount]", texts[lid][1])[:MAXLEN],
                    }
                )
                + "\n"
            )
    pd.DataFrame({"read_id": range(len(ids)), "listing_id": ids}).to_parquet(
        OUT + f"prec/{name}_key.parquet"
    )
json.dump(res, open(OUT + "patterns.json", "w"), indent=1)
