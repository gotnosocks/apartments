"""Image read of the low outliers, part 5: stairs, plan levels and the text mark `duplex`.

Prints the share of the base model's held-out ads carrying the text marks `duplex` and
`penthouse` in five bands of the predictive distribution, income ads left out. Then joins
the Haiku reads to the duplex dataset and prints, for low ads and controls, the shares
with a plan on 2 or more levels, stairs in the photos, a ground or basement mark, the text
mark, and any of the duplex signs, followed by the overlaps between them.

Run from this folder: python duplex.py
"""

import numpy as np
import pandas as pd
from pilot import OUT, reads

ROWS = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse/rows.parquet"
)
RUN = "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz"

if __name__ == "__main__":
    fr = pd.read_parquet(
        ROWS, columns=["listing_id", "duplex", "penthouse", "income_restricted"]
    )
    p = np.load(RUN, allow_pickle=True)
    h = fr[p["heldout"]].reset_index(drop=True)
    assert (h.listing_id.to_numpy() == p["listing"]).all()
    h["cdf"] = p["cdf"]
    h = h[~h.income_restricted.fillna(False).astype(bool)]
    bands = {
        "below 1%": h.cdf < 0.01,
        "1% to 5%": (h.cdf >= 0.01) & (h.cdf < 0.05),
        "middle half": (h.cdf > 0.25) & (h.cdf < 0.75),
        "95% to 99%": (h.cdf > 0.95) & (h.cdf <= 0.99),
        "above 99%": h.cdf > 0.99,
    }
    for name, m in bands.items():
        print(
            f"held-out {name:12s} n {m.sum():6d} duplex {100 * h.duplex[m].mean():5.1f}% "
            f"penthouse {100 * h.penthouse[m].mean():5.1f}%"
        )

    r = (
        reads("haiku")
        .reset_index()
        .merge(pd.read_parquet(OUT / "blind.parquet"), on="label")
        .merge(pd.read_parquet(OUT / "draw.parquet"), on="listing_id")
    )
    fr["listing_id"] = fr.listing_id.astype(str)
    r = r[~r.repeat].merge(
        fr.drop_duplicates("listing_id"), on="listing_id", how="left"
    )
    print("draw ads found in the duplex dataset", r.duplex.notna().sum(), "of", len(r))
    plan = r.plan.astype(bool)
    r["levels"] = plan & (pd.to_numeric(r.plan_levels, errors="coerce").fillna(1) > 1)
    r["stairs"] = r.categories.map(lambda v: "walkup_or_stairs" in v)
    r["ground"] = r.categories.map(lambda v: "ground_or_basement" in v)
    r["text"] = r.duplex.fillna(False).astype(bool)
    r["sign"] = r.levels | r.stairs | r.text
    r["stairs_alone"] = r.stairs & ~r.levels & ~r.text
    r["ground_alone"] = r.ground & ~r.sign
    low = r.group == "low"
    for c in (
        "levels",
        "stairs",
        "ground",
        "text",
        "sign",
        "stairs_alone",
        "ground_alone",
    ):
        print(
            f"{c:13s} low {100 * r[c][low].mean():5.1f}% controls {100 * r[c][~low].mean():5.1f}%"
        )
    print(
        "stairs with a plan level or the text mark:",
        (r.stairs & ~r.stairs_alone).sum(),
        "of",
        r.stairs.sum(),
    )
    known = r[plan & r.duplex.notna()]
    print("plans in the dataset, levels (rows) against the text mark (columns)")
    print(pd.crosstab(known.levels, known.text))
