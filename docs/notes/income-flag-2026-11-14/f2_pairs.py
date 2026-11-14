"""S15, part 2: pairs of ads from mixed units, for a reader.

From `f1_heldout.parquet` the script takes the held-out ads `income_restricted_v2` marks
whose unit has a training ad the flag leaves unmarked and whose description is known. It
draws 10 of them with the seed 20261114 and pairs each with its unit's latest such training
ad. The reader gets the earlier ad first and is not told which ad the flag marks. Each ad
carries its description (as `t1_texts.py` of the text-flag screen wrote it), its
ask and the day it was priced. The pairs go to `OUT/f2_pairs.md` for the reader and to
`OUT/f2_pairs.parquet`.

`income_restricted_v2` in the `-textflags` copy now holds the flag with S15b's negation guard.
A rerun reads that flag, from the copy and from a rerun's `f1_heldout.parquet`, so it draws
from 265 held-out ads where S15 drew from 275, and its pairs may differ from the ones read.

    systemd-run --user --scope -q -p MemoryMax=3G python f2_pairs.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

COPY = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags"
)
TEXTS = Path("/data1/apartments/tmp/text-flags-2026-11-13/texts.parquet")
OUT = Path("/data1/apartments/tmp/income-flag-2026-11-14")
SEED = 20261114
PAIRS = 10

h = pd.read_parquet(OUT / "f1_heldout.parquet")
d = pd.read_parquet(
    COPY / "rows.parquet",
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "price_at",
        "latest_ask",
        "bedrooms",
        "description_known",
        "income_restricted_v2",
    ],
)
d["listing_id"] = d.listing_id.astype(str)
held = set(h.listing_id)
d["ukey"] = np.where(
    d.unit_id.isna(),
    "row:" + d.listing_id,
    d.building.astype(str) + "|" + d.unit_id.astype(str),
)
tr = d[
    ~d.listing_id.isin(held)
    & ~d.income_restricted_v2.astype(bool)
    & d.description_known.astype(bool)
]
tr = tr[tr.ukey.isin(h.ukey[h.new])]
hn = h[h.new & h.ukey.isin(tr.ukey)]
pick = hn.sample(PAIRS, random_state=SEED)
mate = tr.sort_values("price_at").groupby("ukey").tail(1).set_index("ukey")
ids = set(pick.listing_id) | set(mate.loc[pick.ukey].listing_id)
tx = pd.read_parquet(TEXTS)
tx = tx[tx.listing_id.astype(str).isin(ids)].set_index("listing_id").text
rows, md = [], ["# Pairs of ads from the same apartment\n"]
for k, (_, a) in enumerate(pick.iterrows(), start=1):
    b = mate.loc[a.ukey]
    rows.append(
        {
            "pair": k,
            "ukey": a.ukey,
            "flagged_id": a.listing_id,
            "flagged_ask": float(a.latest_ask),
            "flagged_day": str(pd.Timestamp(a.price_at).date()),
            "flagged_gap": float(a.gap),
            "other_id": b.listing_id,
            "other_ask": float(b.latest_ask),
            "other_day": str(pd.Timestamp(b.price_at).date()),
            "old_flag": bool(a.old),
        }
    )
    md.append(f"## Pair {k}\n")
    for tag, x, ask, day in (
        ("earlier", b.listing_id, b.latest_ask, b.price_at),
        ("later", a.listing_id, a.latest_ask, a.price_at),
    ):
        md.append(
            f"### Pair {k}, {tag} ad: asking ${ask:,.0f} a month, "
            f"priced {pd.Timestamp(day).date()}\n\n{tx.get(x, '')}\n"
        )
pd.DataFrame(rows).to_parquet(OUT / "f2_pairs.parquet")
(OUT / "f2_pairs.md").write_text("\n".join(md))
print(pd.DataFrame(rows).to_string())
