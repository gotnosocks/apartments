"""S7, part 1: match each listing's last description for a duplex unit and for a stated
outdoor size, and draw the ads for the Sonnet readers.

The duplex match takes `duplex` or `triplex` unless the same description calls a building a
duplex ("duplex building", "duplex house", "two-family"), or wording for an apartment on
two levels ("spans two floors", "bi-level", "internal staircase"). The outdoor size takes a
number of square feet next to a terrace, balcony, patio, garden, yard, deck or outdoor space,
either way round. pyarrow's RE2 has no lookahead, so the exclusion runs as a second match.

The readers get 200 ads with a duplex match, 50 unmatched ads drawn at random and 50 unmatched
ads with weaker wording ("upper level", "lower level", "stairs", "loft"), plus 100 ads with an
outdoor size, all drawn from L1's dataset rows."""

import json
import os

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

import common as c

DUP = r"(?i)\b(?:duplex|triplex)"
DUP_BLD = r"(?i)\b(?:duplex|triplex)\s+(?:building|house|townhouse|brownstone|walk-?up)|two[- ]family"
STRUCT = (
    r"(?i)\bbi-?level\b|\btwo[- ]level (?:apartment|unit|home|loft|penthouse|residence|layout)"
    r"|\bspans? (?:over )?(?:two|2|three|3) (?:full )?(?:floors|levels|stories)"
    r"|\bspread (?:out )?(?:over|across) (?:two|2|three|3) (?:full )?(?:floors|levels|stories)"
    r"|\b(?:internal|interior|private) (?:spiral )?stair(?:case|s|way)"
)
WEAK = r"(?i)\bupper level|\blower level|\bstairs\b|\bstaircase|\bloft\b|\bmezzanine"
UNIT = r"(?:sq\.?\s*ft\.?|square[- ]f(?:ee|oo)t|\bsf\b|sqft|ft2)"
SPACE = r"(?:outdoor space|terrace|balcony|patio|garden|backyard|yard|roof ?deck|roof ?top|deck)"
OUT_A = (
    r"(?i)(?P<n>\d{2,4}(?:,\d{3})?)\s*\+?\s*"
    + UNIT
    + r"\s+(?:of\s+)?(?:private\s+)?(?:wrap[- ]around\s+)?"
    + SPACE
)
OUT_B = (
    r"(?i)" + SPACE + r"\s+(?:of\s+|measuring\s+|spanning\s+|\(\s*)?"
    r"(?:approximately\s+|approx\.?\s+|about\s+|over\s+|nearly\s+|~\s*)?(?P<n>\d{2,4}(?:,\d{3})?)\s*"
    + UNIT
)

f = pq.ParquetFile(c.RECS)
parts = []
for g in range(f.num_row_groups):
    t = f.read_row_group(g, columns=["listing_id", "last_collected_at", "description"])
    desc = pc.fill_null(t["description"], "")

    def num(pat):
        x = pc.struct_field(pc.extract_regex(desc, pat), "n")
        x = pc.replace_substring(x, ",", "")
        return pd.to_numeric(
            pd.Series(x.to_numpy(zero_copy_only=False)), errors="coerce"
        ).to_numpy()

    a, b = num(OUT_A), num(OUT_B)
    parts.append(
        pd.DataFrame(
            {
                "listing_id": t["listing_id"].to_numpy(zero_copy_only=False),
                "t": t["last_collected_at"].to_numpy(zero_copy_only=False),
                "dup": pc.match_substring_regex(desc, DUP).to_numpy(
                    zero_copy_only=False
                ),
                "dup_bld": pc.match_substring_regex(desc, DUP_BLD).to_numpy(
                    zero_copy_only=False
                ),
                "struct": pc.match_substring_regex(desc, STRUCT).to_numpy(
                    zero_copy_only=False
                ),
                "weak": pc.match_substring_regex(desc, WEAK).to_numpy(
                    zero_copy_only=False
                ),
                "out_sqft": np.where(np.isfinite(a), a, b),
                "desc_len": pc.utf8_length(desc).to_numpy(zero_copy_only=False),
            }
        )
    )
x = pd.concat(parts).sort_values("t").drop_duplicates("listing_id", keep="last")
x["dup_unit"] = (x.dup & ~x.dup_bld) | x.struct
x.loc[(x.out_sqft < 20) | (x.out_sqft > 5000), "out_sqft"] = np.nan
x.drop(columns="t").to_parquet(c.OUT + "s7_text.parquet")
ids = pd.read_parquet(c.DATA, columns=["listing_id"]).listing_id.astype(str)
x = x[x.listing_id.astype(str).isin(set(ids)) & (x.desc_len > 80)]
print(
    "rows",
    len(x),
    {k: float(x[k].mean()) for k in ["dup", "dup_bld", "struct", "dup_unit", "weak"]},
    "out_sqft",
    float(x.out_sqft.notna().mean()),
    flush=True,
)

rng = np.random.default_rng(20261113)


def draw(m, n, label):
    s = x[m]
    s = s.iloc[rng.choice(len(s), min(n, len(s)), replace=False)]
    return pd.DataFrame({"listing_id": s.listing_id.astype(str), "sample": label})


picks = pd.concat(
    [
        draw(x.dup_unit, 200, "dup_matched"),
        draw(~x.dup_unit & ~x.dup & ~x.weak, 50, "unmatched_random"),
        draw(~x.dup_unit & ~x.dup & x.weak, 50, "unmatched_weak"),
        draw(x.out_sqft.notna(), 100, "outdoor_size"),
    ]
)
want = set(picks.listing_id)
text = {}
for g in range(f.num_row_groups):
    t = f.read_row_group(
        g, columns=["listing_id", "last_collected_at", "description"]
    ).to_pandas()
    t = t[t.listing_id.astype(str).isin(want)]
    for r in t.itertuples():
        k = str(r.listing_id)
        if k not in text or text[k][0] < r.last_collected_at:
            text[k] = (r.last_collected_at, r.description)
picks["description"] = picks.listing_id.map(
    lambda k: (text.get(k) or (0, ""))[1][:3000]
)
picks = picks.merge(
    x[["listing_id", "out_sqft"]].astype({"listing_id": str}),
    on="listing_id",
    how="left",
)
picks = picks.sample(frac=1, random_state=1).reset_index(drop=True)
picks["read_id"] = np.arange(len(picks))
picks.to_parquet(c.OUT + "s7_picks.parquet")
# the readers see neither the sample label nor the parsed size
rd = c.OUT + "s7_read/"
os.makedirs(rd, exist_ok=True)
for i in range(4):
    part = picks.iloc[i::4]
    with open(rd + f"batch{i}.jsonl", "w") as fh:
        for r in part.itertuples():
            fh.write(
                json.dumps({"read_id": int(r.read_id), "description": r.description})
                + "\n"
            )
print(picks["sample"].value_counts().to_dict(), flush=True)
