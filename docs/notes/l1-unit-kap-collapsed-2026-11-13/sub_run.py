"""Subsample mixing check: run a model on the 1-in-90 building sample's latest-split
training rows and save the traced scalars. argv: model chains warmup draws seed out.npz"""

import json, sys, time
import numpy as np, pandas as pd
from rentfrontier import splits, drift, building_zones_floor_asof
from rentfrontier import (
    drift_building_phase,
    drift_building_phase_unitt,
    drift_building_phase_unitk,
)

which, chains, warmup, draws, seed, out = (
    sys.argv[1],
    *map(int, sys.argv[2:6]),
    sys.argv[6],
)
D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise"
SUB = "/data1/apartments/tmp/sprint-20261112/y1/timing/subset.parquet"
frame = pd.read_parquet(SUB)
frame.attrs["dataset"] = D
frame.attrs["source_sha256"] = json.loads(open(D + "/manifest.json").read())[
    "rows_sha256"
]
building_zones_floor_asof.SPLIT = "latest"
held = splits.SPLITS["latest"](frame)
mods = {
    "l1": drift_building_phase,
    "l1t": drift_building_phase_unitt,
    "l1tk": drift_building_phase_unitk,
}
extra = {}
if which.startswith("l1t-"):
    extra = {"unit_move": which.split("-", 1)[1]}
    spec = drift_building_phase_unitt
else:
    spec = mods[which]
EXTRA = ("x_mll", "x_sml", "x_mlk", "x_vlk", "x_skp")
orig_ms = drift.make_sampler


def patched(*a, **k):
    sweep, init, predict, parts = orig_ms(*a, **k)
    import jax, jax.numpy as jnp

    def summ(st):
        ll = jnp.log(st["lam"])
        o = {"x_mll": ll.mean(), "x_sml": (st["lam"] < 0.25).mean()}
        if "ukap" in st:
            lk = jnp.log(st["ukap"])
            o |= {
                "x_mlk": lk.mean(),
                "x_vlk": lk.var(),
                "x_skp": (st["ukap"] < 0.25).mean(),
            }
        else:
            o |= {
                "x_mlk": 0.0 * ll.mean(),
                "x_vlk": 0.0 * ll.mean(),
                "x_skp": 0.0 * ll.mean(),
            }
        return o

    sj = jax.jit(jax.vmap(summ))

    def sw(keys, st):
        new, out = sweep(keys, st)
        return new, out | sj(new)

    return sw, init, predict, parts


drift.make_sampler = patched
drift.TRACED = drift.TRACED + EXTRA
full = spec.design(frame)
train = spec.subset(full, ~held)
print(which, len(train.y), "rows", int(train.units), "units", flush=True)
st = drift.Settings(
    chains=chains,
    warmup=warmup,
    draws=draws,
    keep_every=draws,
    level_dof=4.0,
    seed=seed,
    budget_seconds=None,
)
t0 = time.time()
res = spec.run(train, spec.Priors(), st, log=lambda m: print(m, flush=True), **extra)
print("keys", list(res.keys()), flush=True)
tr = res.get("trace", {})
np.savez(out, **{k: np.asarray(v) for k, v in tr.items()})
print(
    which,
    "done",
    time.time() - t0,
    res["result"]["gibbs"].get("seconds_per_sweep"),
    flush=True,
)
