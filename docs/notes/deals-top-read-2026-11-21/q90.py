"""The live Deals run's 5th and 95th percentiles for the picked ads, from the same exact
quantiles `drift_deals.deals` publishes (it writes the 10/90 and 2.5/97.5 bounds only).
Checks the published median and 80% bounds match before writing q90.csv."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import drift_score

RUN = Path(
    "/data1/apartments/frontier/runs/"
    "drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3"
)
SCRATCH = Path(sys.argv[1])
dataset = drift_score.dataset_dir(RUN)
frame = pd.read_parquet(dataset / "rows.parquet", columns=["listing_id"])
held = np.load(RUN / "posterior.npz")["heldout"]
ids = frame.listing_id[held].astype(str).to_numpy()
res = drift_score.score_run(RUN, exact=True)
q = np.exp(res["q"].astype(float))
out = pd.DataFrame(
    {
        "listing_id": ids,
        "q05": q[:, 1].round(0),
        "q10": q[:, 2].round(0),
        "q90": q[:, 5].round(0),
        "q95": q[:, 6].round(0),
        "median": np.exp(res["pred"]).round(0),
    }
)
picks = pd.read_csv(SCRATCH / "picks.csv", dtype={"listing_id": str})
m = picks.merge(out, on="listing_id", how="left")
print("max |median diff|", (m["median"] - m.model_median).abs().max())
m[["listing_id", "q05", "q10", "q90", "q95", "median"]].to_csv(
    SCRATCH / "q90.csv", index=False
)
