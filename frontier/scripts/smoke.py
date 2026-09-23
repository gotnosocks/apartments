import sys
import time

import jax

if "f64" in sys.argv:
    jax.config.update("jax_enable_x64", True)
import numpy as np

from rentfrontier import data, features, model, sample, splits

chains, warmup, draws = (int(v) for v in sys.argv[1:4])
extra = dict(a.split("=") for a in sys.argv[4:] if "=" in a)
extra = {
    k: (
        float(v)
        if k in ("init_inflation", "learning_rate")
        else int(v)
        if k.endswith("steps")
        else tuple(v.split(","))
        if k == "noncentered"
        else v
    )
    for k, v in extra.items()
}
frame = data.load()
heldout = splits.row_split(frame)
prep = model.prepare(frame, heldout, features.build("base-v1", frame, ~heldout))
t = time.perf_counter()
mc = model.ModelConfig(noncentered=extra.pop("noncentered", ()))
out = sample.run(
    prep,
    mc,
    sample.Settings(
        chains=chains, warmup=warmup, draws=draws, keep_every=min(50, draws), **extra
    ),
)
print("total", time.perf_counter() - t)
ref = np.load(
    "/home/ben/code/apartments/data/model/feature-screen-20260923/nuts-hwalk/heldout.npz",
    allow_pickle=True,
)
r = dict(zip(ref["audit_id"], ref["lpd"]))
d = out["lpd"] - np.array([r[a] for a in prep.test_audit_id])
print("elpd", out["lpd"].sum(), "delta", d.sum(), "se", d.std() * np.sqrt(len(d)))
print("chain elpd spread", np.percentile(out["lpd_chain"].sum(1), [0, 50, 100]))
names = sample.SCALARS
sc = out["trace"]["scalars"]
print({n: round(float(v), 4) for n, v in zip(names, sc.mean((0, 1)))})
print(
    "accept",
    out["trace"]["accept"].mean(),
    "divergent",
    out["trace"]["divergent"].sum(),
    "steps",
    out["trace"]["steps"].mean(),
)
import blackjax

for i, n in enumerate(names):
    print(
        n,
        "rhat",
        float(blackjax.rhat(sc[..., i], 0, 1)),
        "ess",
        float(blackjax.ess(sc[..., i], 0, 1)),
    )
