import sys
import time

import jax
import jax.flatten_util
import jax.numpy as jnp
import numpy as np
from numpyro.infer.util import initialize_model
from rentfrontier import data, features, model, sample, splits

frame = data.load()
heldout = splits.row_split(frame)
prep = model.prepare(frame, heldout, features.build("base-v1", frame, ~heldout))
info = initialize_model(
    jax.random.PRNGKey(0),
    model.build_model(prep, model.ModelConfig()),
    dynamic_args=False,
)
flat0, unravel = jax.flatten_util.ravel_pytree(info.param_info.z)
ld = lambda x: -info.potential_fn(unravel(x))
start = jax.random.uniform(jax.random.PRNGKey(1), (16, flat0.size), jnp.float32, -2, 2)
x = start
for steps, lr in [(int(s), float(l)) for s, l in (a.split(":") for a in sys.argv[1:])]:
    t = time.perf_counter()
    x = sample._optimize_starts(ld, x, steps, lr)
    jax.block_until_ready(x)
    c = jax.vmap(lambda v: info.postprocess_fn(unravel(v)))(x)
    lp = jax.vmap(ld)(x)
    print(
        f"+{steps}@{lr} {time.perf_counter() - t:.1f}s lp med {float(jnp.median(lp)):.0f} min {float(lp.min()):.0f} max {float(lp.max()):.0f}"
    )
    for n in [
        "sigma",
        "nu",
        "unit_scale",
        "building_scale",
        "trend_scale",
        "season_scale",
    ]:
        v = np.asarray(c[n])
        print(f"   {n:15s} {np.round(np.percentile(v, [0, 50, 100]), 4)}")
