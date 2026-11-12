import sys, time, numpy as np, pandas as pd
from rentfrontier import (
    b0,
    splits,
    drift,
    drift_building,
    drift_building_phase,
    drift_building_phase_year,
    building_zones_floor_asof,
)

which = sys.argv[1]
D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
import os, gc

SUB = "/data1/apartments/tmp/sprint-20261112/y1/timing/subset.parquet"
if not os.path.exists(SUB):
    frame = b0.load_frame(D)
    rng = np.random.default_rng(0)
    b = frame.building.unique()
    pick = rng.choice(b, size=len(b) // 90, replace=False)
    frame[frame.building.isin(pick)].reset_index(drop=True).to_parquet(SUB)
    print("wrote subset")
    sys.exit(0)
attrs = b0.load_frame.__globals__["json"].loads(open(D + "/manifest.json").read())
frame = pd.read_parquet(SUB)
frame.attrs["dataset"] = D
frame.attrs["source_sha256"] = attrs["rows_sha256"]
building_zones_floor_asof.SPLIT = "latest"
held = splits.SPLITS["latest"](frame)
spec = {"l1": drift_building_phase, "y1": drift_building_phase_year}[which]
full = spec.design(frame)
train = spec.subset(full, ~held)
print(which, len(train.y), "rows", int(train.units), "units", flush=True)
out = drift_building.run(
    train,
    spec.Priors(),
    drift.Settings(chains=2, warmup=60, draws=60, level_dof=4.0, seed=1),
    log=lambda m: None,
)
print(
    which,
    "seconds_per_sweep",
    out["result"]["gibbs"]["seconds_per_sweep"],
    out["seconds"],
    flush=True,
)
