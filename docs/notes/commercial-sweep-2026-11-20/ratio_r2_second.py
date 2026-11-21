"""Write blind second-read batches for every first read coded commercial, placeholder or unclear.

The blocks are the first pass's cached blocks (`ratio_r1_draw.py`), under new read ids S001...
in a new seeded order, so a second reader sees neither the first code nor the first read id.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("/data1/apartments/tmp/ratio-read")
SEED = 20261122
N_BATCH = 10

if __name__ == "__main__":
    D = pd.read_parquet(OUT / "draw_r1.parquet")
    L = pd.read_csv(OUT / "r1_parsed.csv", dtype=str)
    D = D.merge(L[["read_id", "answer"]], on="read_id")
    S = D[D.answer != "apartment"].copy()
    print("second reads", len(S), S.answer.value_counts().to_dict())
    body = json.loads((OUT / "blocks.json").read_text())
    rng = np.random.default_rng(SEED)
    S = S.iloc[rng.permutation(len(S))].reset_index(drop=True)
    S["read2_id"] = [f"S{i + 1:03d}" for i in range(len(S))]
    for k, part in enumerate(np.array_split(np.arange(len(S)), N_BATCH)):
        rows = S.iloc[part]
        p = OUT / f"batch_r2_{k + 1:02d}.md"
        p.write_text(
            "\n\n".join(
                f"### {r.read2_id}\n{body[r.listing_id]}" for r in rows.itertuples()
            )
            + "\n"
        )
        print(p.name, len(rows), hashlib.sha256(p.read_bytes()).hexdigest()[:16])
    S[["read2_id", "read_id", "listing_id"]].to_parquet(OUT / "draw_r2.parquet")
