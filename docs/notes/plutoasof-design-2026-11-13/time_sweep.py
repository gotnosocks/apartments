"""The CPU sweep time of L1 and of P1 on the 1-in-90 sample of buildings from Y1's timing.

The script takes the sample that `docs/notes/year-noise-2026-11-12/time_sweep.py` wrote. It
builds the design of the model named on the command line (`l1` or `plutoasof`) on the latest
split's training rows and prints the seconds the design took. Then it runs 2 chains of 60
warmup and 60 draws and prints the seconds a sweep."""

import json
import sys
import time

import pandas as pd

from rentfrontier import (
    building_zones_floor_asof,
    drift,
    drift_building_phase,
    drift_building_phase_plutoasof,
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
spec = {"l1": drift_building_phase, "plutoasof": drift_building_phase_plutoasof}[which]
t0 = time.perf_counter()
full = spec.design(frame)
print(which, "design_seconds", round(time.perf_counter() - t0, 1), flush=True)
train = spec.subset(full, ~held)
print(which, len(train.y), "rows", int(train.units), "units")
out = spec.run(
    train,
    spec.Priors(),
    drift.Settings(chains=2, warmup=60, draws=60, level_dof=4.0, seed=1),
    log=lambda m: None,
)
print(which, "seconds_per_sweep", out["result"]["gibbs"]["seconds_per_sweep"])
print(which, "seconds", out["seconds"], flush=True)
