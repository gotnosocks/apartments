"""The CPU sweep time of L1 and of its segment paths, quarterly and weekly, on the 1-in-90
sample of buildings from Y1's timing.

The script takes the sample that `docs/notes/year-noise-2026-11-12/time_sweep.py` wrote and
builds the design named on the command line on the latest split's training rows:

    l1       L1 (`drift-building-phase`)
    quarter  L1 with a path for each segment between quarter starts
             (`drift-building-phase-segment`)
    week     the same paths with a knot at every week of the grid, built here with the
             module's `path_design`, each segment's process over the weeks' years

It runs 2 chains of WARMUP warmup and DRAWS draws (60 and 60 unless given), then prints the
design's size and the seconds a sweep."""

import json
import sys

import numpy as np
import pandas as pd

from rentfrontier import (
    building_zones_floor_asof,
    drift,
    drift_building_phase,
    drift_building_phase_segment as seg,
    splits,
)

D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
SUB = "/data1/apartments/tmp/sprint-20261112/y1/timing/subset.parquet"

which = sys.argv[1]
warmup, draws = (int(a) for a in sys.argv[2:4]) if len(sys.argv) > 3 else (60, 60)
frame = pd.read_parquet(SUB)
frame.attrs["dataset"] = D
frame.attrs["source_sha256"] = json.load(open(D + "/manifest.json"))["rows_sha256"]
building_zones_floor_asof.SPLIT = "latest"
held = splits.SPLITS["latest"](frame)
gp = "spec"
if which == "l1":
    full = drift_building_phase.design(frame)
elif which == "quarter":
    full = seg.design(frame)
    gp = seg.gp_spec(full.names)
else:
    base = drift_building_phase.design(frame)
    knots = np.arange(base.weeks + 1) / drift.YEAR_WEEKS
    labels = seg.segment_names(base)
    full = seg.path_design(base, knots, [f"w{j}" for j in range(len(knots))])
    ref = (seg.REFERENCE - pd.Timestamp(base.start)).days / seg.YEAR_DAYS
    gp = drift_building_phase.gp_spec(full.names)
    for s in labels:
        cols = [n for n in full.names if n.startswith(f"seg:{s}:w")]
        x = np.array([int(n.rsplit(":w", 1)[1]) for n in cols]) / drift.YEAR_WEEKS - ref
        gp.append(dict(name=f"seg:{s}", cols=cols, x=x, amp=seg.SEG_AMP, ls=seg.SEG_LS))
train = drift_building_phase.subset(full, ~held)
paths = sum(n.startswith("seg:") for n in train.names)
print(
    which,
    len(train.y),
    "rows",
    int(train.units),
    "units",
    len(train.names),
    "columns",
    paths,
    "path columns",
    train.weeks,
    "weeks",
    flush=True,
)
out = drift.run(
    train,
    drift_building_phase.Priors(),
    drift.Settings(chains=2, warmup=warmup, draws=draws, level_dof=4.0, seed=1),
    log=lambda m: None,
    gp=gp,
    groups=drift.groups_of(train, drift_building_phase.GROUPS),
)
print(which, "seconds_per_sweep", out["result"]["gibbs"]["seconds_per_sweep"])
print(which, "seconds", out["seconds"], flush=True)
