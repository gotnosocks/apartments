"""A short run of L1 or of the line model on the 1-in-90 sample of buildings from Y1's
timing, printing the fixed columns' coefficients and, for the line model, the spread of the
line levels.

The script builds the design of the model named on the command line (`l1` or `line`) on the
latest split's training rows and runs 2 chains of as many warmup sweeps and draws as the
second argument says. For the line model it wraps the sweep so that each draw also records
the line levels' mean, their root mean square, and their root mean square about their
building's mean over the lines of buildings with two or more lines. It prints each
coefficient's mean over the second half of the draws (all but the `bld:` columns) and each
chain's mean of the scales and of the line summaries, and saves the coefficients' draws to
`beta-{model}-{sweeps}.npy`, which `pairs.py` reads. It runs from the worktree's root on the
CPU."""

import json
import sys
from pathlib import Path

import numpy as np
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
OUT = "/data1/apartments/tmp/line-level-20261113"

which, n = sys.argv[1], int(sys.argv[2])
frame = pd.read_parquet(SUB)
frame.attrs["dataset"] = D
frame.attrs["source_sha256"] = json.load(open(D + "/manifest.json"))["rows_sha256"]
building_zones_floor_asof.SPLIT = "latest"
held = splits.SPLITS["latest"](frame)
run = dict(seed=1, chains=2, warmup=n, draws=n, level_dof=4.0)
if which == "l1":
    spec, settings = drift_building_phase, drift.Settings(**run)
else:
    spec, settings = drift_building_phase_line, drift_line.Settings(**run)
train = spec.subset(spec.design(frame), ~held)
names = list(train.names)

if which != "l1":
    make = drift_line.make_sampler

    def recorded(*a, **k):
        sweep, init, predict, parts = make(*a, **k)
        site = np.asarray(parts["data"]["line_site"])
        cnt = np.bincount(site, minlength=len(site))
        multi = cnt[site] > 1

        def sweep_and_record(keys, st):
            new, out = sweep(keys, st)
            levels = np.asarray(new["line"])
            dev = [
                row - (np.bincount(site, row, len(site)) / np.maximum(cnt, 1))[site]
                for row in levels
            ]
            return new, out | {
                "line_mean": levels.mean(axis=1),
                "line_rms": np.sqrt((levels**2).mean(axis=1)),
                "line_within": np.array([np.sqrt((x[multi] ** 2).mean()) for x in dev]),
            }

        return sweep_and_record, init, predict, parts

    drift_line.make_sampler = recorded
    drift_line.TRACED = drift_line.TRACED + ("line_mean", "line_rms", "line_within")

out = spec.run(train, spec.Priors(), settings, log=lambda m: print(m[:400], flush=True))
beta = out["trace"]["beta"]
half = beta.shape[1] // 2
mean = beta[:, half:].mean(axis=(0, 1))
for name, value in zip(names, mean):
    if not name.startswith("bld:"):
        print(which, name, round(float(value), 4))
for k in ("unit_sd", "drift_sd", "line_sd", "line_mean", "line_rms", "line_within"):
    if k in out["trace"]:
        print(which, k, out["trace"][k][:, half:].mean(axis=1).round(4).tolist())
np.save(f"{OUT}/beta-{which}-{n}.npy", beta)
