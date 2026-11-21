"""Score a run's held-out ads and mark the units with no training ad.

Usage: score.py RUN TAG. Writes scores-TAG.parquet in the scratch folder: one row per
held-out ad with the predictive's median, cdf at the ask, quantiles and log density.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import drift_deals, drift_score

OUT = Path("/data1/apartments/tmp/po-firstad-noise")
run = Path("/data1/apartments/frontier/runs") / sys.argv[1]
frame, h, held = drift_deals._held_frame(run)
res = drift_score.score_run(run)
assert (res["listing"] == h.listing_id.astype(str).to_numpy()).all()
train_units = set(frame.unit_id[~held].dropna())
q = res["q"].astype(float)
out = pd.DataFrame(
    {
        "listing_id": h.listing_id.astype(str),
        "building": h.building.astype(str),
        "first_day": h.first_day.astype(str),
        "bedrooms": h.bedrooms,
        "no_unit": ~h.unit_id.isin(train_units).to_numpy()
        | h.unit_id.isna().to_numpy(),
        "y": res["y"],
        "pred": res["pred"],
        "cdf": res["cdf"],
        "elpd": res["elpd"],
        "unit_sd": res["unit_sd"],
    }
)
for i, p in enumerate(res["quantiles"]):
    out[f"q{int(round(1000 * p)):03d}"] = q[:, i]
out.to_parquet(OUT / f"scores-{sys.argv[2]}.parquet")
z = np.load(run / "posterior.npz")
print(run.name)
print(
    "held-out ads", len(out), "with no training ad of the unit", int(out.no_unit.sum())
)
print("quantiles", list(res["quantiles"]))
print("first days", out.first_day.min(), "to", out.first_day.max())
for k in ("kept/phase_scale", "kept/unit_sd", "kept/sigma", "kept/nu"):
    if k in z:
        v = z[k].reshape(-1, *z[k].shape[2:])
        print(k, np.round(v.mean(0), 3))
