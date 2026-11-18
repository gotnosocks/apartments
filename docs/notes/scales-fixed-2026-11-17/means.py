"""Write the scale means of a run as a set for `held.py`.

    python means.py RUN OUT.json

RUN is a run directory with `posterior.npz`. The script averages each tight scale's draws
over chains and sweeps and writes them, with RUN as the source, in the layout of a set in
`rentfrontier.drift_scales`.
"""

import json
import sys
from pathlib import Path

import numpy as np

SCALES = (
    "nu",
    "sigma",
    "unit_sd",
    "drift_sd",
    "drift_tau",
    "bld_sd",
    "building_ar_sd",
    "building_ar_rho",
    "tau",
)

run = Path(sys.argv[1])
post = np.load(run / "posterior.npz", allow_pickle=True)
values = {}
for name in SCALES:
    draws = np.asarray(post[f"trace/{name}"])
    mean = draws.reshape(-1, *draws.shape[2:]).mean(axis=0)
    values[name] = mean.tolist()
Path(sys.argv[2]).write_text(
    json.dumps({"source": f"the run {run}", "values": values}, indent=1)
)
print(json.dumps(values, indent=1))
