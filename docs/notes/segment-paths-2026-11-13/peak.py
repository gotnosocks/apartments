"""The host's numpy memory in `drift.main_run` for the segment model, from the end of the design
build through `drift.make_sampler`, on the 1-in-90 sample of buildings from Y1's timing.

    python peak.py RUNS

The script runs `main_run` on the latest split with the segment module as its spec. It starts
`tracemalloc` once the design of all rows is built, so that design is left out of the counts.
In place of the sampler it records the memory held and the peak so far, then calls
`make_sampler` and records the most it adds, and stops there. It prints each count in units of
the design of all rows. The run's folder goes in RUNS, which must exist."""

import json
import sys
import tracemalloc
import types
from pathlib import Path

import pandas as pd

from rentfrontier import b0, drift
from rentfrontier import drift_building_phase_segment as seg
from rentfrontier import run as runmod

D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
SUB = "/data1/apartments/tmp/sprint-20261112/y1/timing/subset.parquet"
frame = pd.read_parquet(SUB)
frame.attrs["dataset"] = D
frame.attrs["source_sha256"] = json.loads(Path(D, "manifest.json").read_text())[
    "rows_sha256"
]
b0.load_frame = lambda: frame
runmod.RUNS = Path(sys.argv[1])
size = {}


def design(f):
    d = seg.design(f)
    size["design"] = d.x.nbytes
    tracemalloc.start()
    tracemalloc.reset_peak()
    size["base"] = tracemalloc.get_traced_memory()[0]
    return d


class Stop(Exception):
    pass


def sample(train, priors, settings, log=print, checkpoint=None):
    cur, peak = tracemalloc.get_traced_memory()
    size["at_sample"] = cur - size["base"]
    size["peak_before_sample"] = peak - size["base"]
    size["train_x"], size["pred_x"] = train.x.nbytes, train.pred["x"].nbytes
    tracemalloc.reset_peak()
    drift.make_sampler(
        train,
        priors,
        settings,
        gp=seg.gp_spec(train.names),
        groups=drift.groups_of(train, seg.GROUPS),
    )
    size["sampler_extra"] = tracemalloc.get_traced_memory()[1] - cur
    raise Stop


spec = types.SimpleNamespace(
    **{k: getattr(seg, k) for k in dir(seg) if not k.startswith("__")}
)
spec.design = design
try:
    drift.main_run(
        ["--split", "latest", "--name", "peak", "--chains", "2", "--dev"],
        name=seg.NAME,
        sample=sample,
        spec=spec,
        level_dof=seg.LEVEL_DOF,
    )
except Stop:
    pass
print(
    json.dumps(
        {k: round(v / size["design"], 3) for k, v in size.items()}
        | {"design_mb": size["design"] / 1e6}
    )
)
