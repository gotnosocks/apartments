"""The CPU sweep time of L1 and of L2 on the 1-in-90 sample of buildings from Y1's timing.

The script takes the sample that `docs/notes/year-noise-2026-11-12/time_sweep.py` wrote, builds
the design of the model named on the command line (`l1` or `l2`) on the latest split's
training rows and runs 2 chains of 60 warmup and 60 draws, then prints the seconds a sweep."""

import json
import sys

import pandas as pd

from rentfrontier import (
    building_zones_floor_asof,
    drift,
    drift_building_phase,
    drift_building_phase_level,
    splits,
)

D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
SUB = "/data1/apartments/tmp/sprint-20261112/y1/timing/subset.parquet"

which = sys.argv[1]
frame = pd.read_parquet(SUB)
frame.attrs["dataset"] = D
frame.attrs["source_sha256"] = json.load(open(D + "/manifest.json"))["rows_sha256"]
building_zones_floor_asof.SPLIT = "latest"
held = splits.SPLITS["latest"](frame)
spec = {"l1": drift_building_phase, "l2": drift_building_phase_level}[which]
full = spec.design(frame)
train = spec.subset(full, ~held)
print(
    which, len(train.y), "rows", int(train.units), "units", len(train.names), "columns"
)
out = spec.run(
    train,
    spec.Priors(),
    drift.Settings(chains=2, warmup=60, draws=60, level_dof=4.0, seed=1),
    log=lambda m: None,
)
print(which, "seconds_per_sweep", out["result"]["gibbs"]["seconds_per_sweep"])
print(which, "seconds", out["seconds"], flush=True)
