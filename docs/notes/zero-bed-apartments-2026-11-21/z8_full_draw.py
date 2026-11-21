"""Review round: the 195 training rows that meet both marks, for a full blind read.

Rows: training rows coded 0 bed with no ledger entry whose text states 2 or more bedrooms for
the unit (`T`) and whose unit has another typed ad coded 2 or more (`U_any`).

For each row I count the unit's other ads with a typed count (ledger-set ads left out, as in
`z2_marks.py`) and how many of them code the text's count (`bed_text`). `majority` means more
than half of them do, the bar of Ben's rule that ad text never overrides coded fields
(2026-10-04): a correction is backed only where the unit's other ads mostly agree.

All 195 go to blind readers in the blocks of `z4_draw.py`, under new ids Y001 to Y195 in a
seeded shuffle, 15 to a batch. No ask is read.
"""

import hashlib
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(WT / "pipeline"))
from models.ledger import entries  # noqa: E402
from z4_draw import ADS, build  # noqa: E402

OUT = Path("/data1/apartments/tmp/zero-bed")
SEED = 20261122
PER_BATCH = 15

if __name__ == "__main__":
    rows = entries.read(sorted((WT / "pipeline" / "ledger").glob("*.ndjson")))
    gone = {r["retracts"] for r in rows if r["change"] == "retract"}
    bedset = sorted(
        {
            str(r["listing_id"])
            for r in rows
            if r["change"] == "set"
            and r["entry"] not in gone
            and r.get("bedrooms") is not None
        }
    )
    m = pd.read_parquet(OUT / "marked.parquet")
    D = m[m["T"] & m.U_any].copy()
    D["listing_id"] = D.listing_id.astype(str)
    c = duckdb.connect()
    c.execute("set memory_limit='2GB'")
    c.execute("set threads=2")
    c.register("d", D[["listing_id", "unit_id", "bed_text"]])
    c.register("bedset", pd.DataFrame({"listing_id": bedset}))
    G = c.execute(f"""
      select d.listing_id, count(o.listing_id) n_other,
        sum((o.bedrooms = d.bed_text)::int) n_agree,
        list(o.listing_id order by o.first_day) filter (where o.bedrooms = d.bed_text) agree_ids,
        list(o.listing_id order by o.first_day) filter (where o.bedrooms <> d.bed_text) other_ids
      from d join '{ADS}' o on o.unit_id = d.unit_id and o.listing_id <> d.listing_id
      where o.bedrooms is not null and o.listing_id not in (select listing_id from bedset)
      group by 1""").df()
    D = D.merge(G, on="listing_id", how="left")
    D["majority"] = D.n_agree * 2 > D.n_other
    print(
        "rows",
        len(D),
        "majority of the unit's other counted ads code the text's count",
        int(D.majority.sum()),
    )
    print(
        "other counted ads per row",
        D.n_other.clip(upper=6).value_counts().sort_index().to_dict(),
    )
    print(
        "agreeing share",
        pd.cut(D.n_agree / D.n_other, [-0.01, 0, 0.5, 0.99, 1])
        .value_counts()
        .sort_index()
        .to_dict(),
    )
    print(
        "majority by half",
        D.groupby("half").majority.agg(["sum", "size"]).to_dict("index"),
    )
    rng = np.random.default_rng(SEED)
    D = D.iloc[rng.permutation(len(D))].reset_index(drop=True)
    D["read_id"] = [f"Y{i + 1:03d}" for i in range(len(D))]
    blocks = build(D)
    nb = -(-len(D) // PER_BATCH)
    for k, part in enumerate(np.array_split(np.arange(len(D)), nb)):
        p = OUT / f"full_batch_{k + 1:02d}.md"
        p.write_text("\n\n".join(blocks[i] for i in part) + "\n")
        assert "$" not in p.read_text()
        print(p.name, len(part), hashlib.sha256(p.read_bytes()).hexdigest()[:16])
    keep = [
        "read_id",
        "listing_id",
        "unit_id",
        "building",
        "half",
        "bed_text",
        "u2_min",
        "n_other",
        "n_agree",
        "majority",
        "agree_ids",
        "other_ids",
        "first_day",
        "lister",
    ]
    D[keep].to_parquet(OUT / "full_draw.parquet")
    print(json.dumps({"rows": len(D), "batches": nb, "seed": SEED}))
