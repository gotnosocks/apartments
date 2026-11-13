"""S12, part B's ad reading: draw the held-out ads that state one of the codes and that L1
over-predicts by more than its 80% interval, with controls inside the 50% interval matched on
the code, zone and bedrooms, and write them in shuffled batches for blind readers.

The batches hold each ad's text and facts under a reading id, with nothing on its group or
L1's prediction. The key from reading ids to groups goes to a separate file."""

import json
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "causal-screens-2026-11-13"))
import common as c  # noqa: E402

CODES = {
    "ad:private_outdoor_roof_rights": "roof rights",
    "ad:feat_hardwood_floors": "hardwood floors",
    "ad:fireplace_decorative": "decorative fireplace",
    "ad:views_city": "city views",
    "ad:private_outdoor_balcony": "balcony",
    "ad:views_park": "park views",
    "bld:amen_live_in_super": "live-in super",
}
PER_CODE, CONTROLS, BATCHES = 15, 7, 5
rng = np.random.default_rng(20261113)

h = pd.read_parquet(c.OUT + "s12b_heldout.parquet")
h["beds"] = np.minimum(h.bedrooms.fillna(0), 3).astype(int)
over = h.y < h.lo
mid = (h.y >= h.q25) & (h.y <= h.q75)
taken = set()
picks = []
for k in CODES:
    on = h[k] > 0
    cand = h[on & over & ~h.listing_id.isin(taken)]
    g = cand.iloc[rng.permutation(len(cand))[:PER_CODE]]
    taken |= set(g.listing_id)
    picks.append(g.assign(code=k, group="over"))
    pool = h[on & mid & ~h.listing_id.isin(taken)]
    ctl = []
    for _, row in g.iloc[:CONTROLS].iterrows():
        m = pool[(pool.zone == row.zone) & (pool.beds == row.beds)]
        m = m[~m.listing_id.isin(taken)]
        if len(m):
            one = m.iloc[[rng.integers(len(m))]]
            taken |= set(one.listing_id)
            ctl.append(one)
    picks.append(pd.concat(ctl).assign(code=k, group="control"))
s = pd.concat(picks, ignore_index=True)

facts = pd.read_parquet(
    c.DATA,
    columns=["listing_id", "neighbourhood", "unit_id", "full_baths", "latest_ask"],
)
s = s.merge(facts, on="listing_id", how="left", suffixes=("", "_f"))
want = set(s.listing_id.astype(str))
text = {}
f = pq.ParquetFile(c.RECS)
for i in range(f.metadata.num_row_groups):
    g = f.read_row_group(i, columns=["listing_id", "description"]).to_pandas()
    g = g[g.listing_id.astype(str).isin(want) & g.description.notna()]
    for lid, t in zip(g.listing_id.astype(str), g.description):
        if len(t) > len(text.get(lid, "")):
            text[lid] = t
s["description"] = s.listing_id.astype(str).map(text).fillna("")
s = s.iloc[rng.permutation(len(s))].reset_index(drop=True)
s["read_id"] = [f"R{i:03d}" for i in range(len(s))]
s["batch"] = np.arange(len(s)) % BATCHES

os.makedirs(c.OUT + "s12read", exist_ok=True)
for b in range(BATCHES):
    with open(c.OUT + f"s12read/batch{b}.jsonl", "w") as out:
        for _, r in s[s.batch == b].iterrows():
            out.write(
                json.dumps(
                    {
                        "read_id": r.read_id,
                        "coded_feature": CODES[r.code],
                        "neighbourhood": r.neighbourhood,
                        "unit": None if pd.isna(r.unit_id) else str(r.unit_id),
                        "bedrooms": None if pd.isna(r.bedrooms) else float(r.bedrooms),
                        "full_baths": None
                        if pd.isna(r.full_baths)
                        else float(r.full_baths),
                        "monthly_ask": float(r.latest_ask),
                        "description": r.description[:3000],
                    }
                )
                + "\n"
            )
s.drop(columns="description").to_parquet(c.OUT + "s12read/key.parquet")
print(
    s.groupby(["code", "group"]).size().to_dict(),
    "no text",
    int((s.description == "").sum()),
)
