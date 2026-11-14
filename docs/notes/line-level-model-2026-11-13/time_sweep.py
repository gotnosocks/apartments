"""The CPU sweep time of L1 and of the line model on the 1-in-90 sample of buildings from
Y1's timing.

The script takes the sample that `docs/notes/year-noise-2026-11-12/time_sweep.py` wrote and
builds the design of the model named on the command line on the latest split's training
rows: `l1`, `line`, or `line-bld`, the line model with L1's slow columns alone. It runs 2
chains of 60 warmup and 60 draws (or as many of each as the second argument says), then
prints the seconds a sweep and each chain's mean of the scales."""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import (  # noqa: E402
    building_zones_floor_asof,
    drift,
    drift_building_phase,
    drift_building_phase_line,
    drift_line,
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
n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
run = dict(seed=1, chains=2, warmup=n, draws=n, level_dof=4.0)
if which == "l1":
    spec, settings = drift_building_phase, drift.Settings(**run)
else:
    spec = drift_building_phase_line
    slow = (
        drift.Settings().slow_columns
        if which == "line-bld"
        else drift_line.SLOW_COLUMNS
    )
    settings = drift_line.Settings(**run, slow_columns=slow)
full = spec.design(frame)
train = spec.subset(full, ~held)
print(
    which,
    len(train.y),
    "rows",
    int(train.units),
    "units",
    getattr(train, "lines", 0),
    "lines",
)
out = spec.run(train, spec.Priors(), settings, log=lambda m: None)
print(which, "seconds_per_sweep", out["result"]["gibbs"]["seconds_per_sweep"])
print(which, "seconds", out["seconds"], flush=True)
for k in ("unit_sd", "drift_sd", "bld_sd", "sigma") + (
    ("line_sd",) if which != "l1" else ()
):
    print(which, k, out["trace"][k].mean(axis=1).round(4).tolist())
