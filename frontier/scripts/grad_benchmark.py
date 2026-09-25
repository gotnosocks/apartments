"""Time log-density + gradient per chain versus number of parallel chains."""

import sys
import time

import jax

if sys.argv[1] == "f64":
    jax.config.update("jax_enable_x64", True)
import jax.flatten_util
from numpyro.infer.util import initialize_model
from rentfrontier import data, features, model, splits

frame = data.load()
heldout = splits.row_split(frame)
feats = features.build("base-v1", frame, ~heldout)
prep = model.prepare(frame, heldout, feats)
info = initialize_model(
    jax.random.PRNGKey(0),
    model.build_model(prep, model.ModelConfig()),
    dynamic_args=False,
)
flat, unravel = jax.flatten_util.ravel_pytree(info.param_info.z)
potential_fn = info.potential_fn
print(sys.argv[1], jax.devices()[0], "dim", flat.size, prep.sizes, flush=True)
vg = jax.jit(jax.vmap(jax.value_and_grad(lambda x: -potential_fn(unravel(x)))))
for chains in [int(c) for c in sys.argv[2].split(",")]:
    x = flat[None] + 0.01 * jax.random.normal(
        jax.random.PRNGKey(1), (chains, flat.size), flat.dtype
    )
    jax.block_until_ready(vg(x))
    reps = max(3, int(200 / chains))
    t = time.perf_counter()
    for _ in range(reps):
        out = vg(x)
    jax.block_until_ready(out)
    dt = (time.perf_counter() - t) / reps
    print(
        f"chains={chains:4d} {dt * 1e3:8.2f} ms/eval  {dt / chains * 1e3:7.3f} ms/chain-grad",
        flush=True,
    )
