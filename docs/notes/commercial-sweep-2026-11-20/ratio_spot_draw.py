"""Draw 20 first-pass apartment codes of the ratio-row hand read for a hand spot check."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("/data1/apartments/tmp/ratio-read")

if __name__ == "__main__":
    B = json.loads((OUT / "blocks.json").read_text())
    D = pd.read_parquet(OUT / "draw_r1.parquet").merge(
        pd.read_csv(OUT / "r1_parsed.csv", dtype=str), on="read_id"
    )
    A = D[D.answer == "apartment"].sort_values("read_id")
    pick = A.iloc[np.random.default_rng(20261123).choice(len(A), 20, replace=False)]
    pick = pick.sort_values("read_id")
    pick[["read_id", "listing_id"]].to_csv(OUT / "spot_pick.csv", index=False)
    for r in pick.itertuples():
        print(f"== {r.read_id} | {r.why}\n{B[r.listing_id][:700]}\n")
