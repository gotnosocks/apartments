"""Interval width and the model's unit sd on held-out ads, by mark and half.

Explains the coverage gap of `a9_heldout.py`: the spread of the gap against the width the
model gave. `width90` is the log distance from the 5% to the 95% point.
"""

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/any-unit"
RUN = "/data1/apartments/frontier/runs/drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"

if __name__ == "__main__":
    s = np.load(f"{RUN}/pred_scores.npz", allow_pickle=True)
    w = pd.DataFrame(
        {
            "listing_id": s["listing"].astype(str),
            "width90": s["q"][:, 6] - s["q"][:, 1],
            "unit_sd": s["unit_sd"],
        }
    )
    d = pd.read_parquet(f"{OUT}/heldout.parquet").merge(w, on="listing_id")
    for mark in ("m_text", "m_overlap", "m_any"):
        for h in "AB":
            x = d[d.half == h]
            mb = set(x.building[x[mark]])
            g = {
                "marked": x[mark],
                "same_bldg": ~x[mark] & x.building.isin(mb),
                "all": pd.Series(True, index=x.index),
            }
            out = []
            for k, m in g.items():
                y = x[m]
                out.append(
                    f"{k} width90 {y.width90.median():.3f} unit_sd {y.unit_sd.median():.3f}"
                    f" sd/width {y.gap.std() / y.width90.median():.3f}"
                )
            print(mark[2:], h, " | ".join(out))
