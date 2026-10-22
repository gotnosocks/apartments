"""Time the per-chunk numeric steps of rentfrontier.summary on synthetic arrays
of NB9's shape (1,000 kept draws x 1,024 rows, 24 terms). Uses the repo's own
function bodies, extracted from the source files, so nothing is reimplemented
except the JAX unit-level step's helpers.

    python bench_summary.py <repo>
"""

import ast
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

repo = Path(sys.argv[1])
src_summary = (repo / "frontier/src/rentfrontier/summary.py").read_text()
src_explain = (repo / "frontier/src/rentfrontier/explain.py").read_text()


def extract(src, names):
    tree = ast.parse(src)
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.Assign)):
            n = node.name if isinstance(node, ast.FunctionDef) else None
            if n in names or (
                isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) in names for t in node.targets)
            ):
                out.append(ast.get_source_segment(src, node))
    return "\n\n".join(out)


ns = {"np": np, "math": math}
exec(
    extract(
        src_summary,
        {
            "PROBABILITIES",
            "PREDICTIVE",
            "normalized_weights",
            "psis_log_weights",
            "weighted_quantiles",
            "predictive_quantiles",
            "_stats",
        },
    ),
    ns,
)
exec(extract(src_explain, {"decompose"}), ns)

D, N, T = 1000, 1024, 24
CHUNKS = math.ceil(266_513 / N)
rng = np.random.default_rng(0)
terms = {"market": 8.0 + 0.01 * rng.standard_normal((D, N))}
for i in range(T - 1):
    terms[f"t{i}"] = 0.05 * rng.standard_normal((D, N)) + 0.02 * rng.standard_normal(N)
total = sum(terms.values())
loglik = -0.5 * ((0.1 * rng.standard_normal((D, N))) / 0.1) ** 2 - 2.0
sigma = np.full((D, 1), 0.12) + 0.005 * rng.standard_normal((D, 1))
nu = 4.0 + 0.3 * rng.standard_normal(D)
log_ask = total.mean(0) + 0.1 * rng.standard_normal(N)

timings = {}


def timed(name, f, reps=1):
    t0 = time.perf_counter()
    for _ in range(reps):
        r = f()
    timings[name] = (time.perf_counter() - t0) / reps
    return r


dollars, rent = timed("LMDI decomposition", lambda: ns["decompose"](terms))
log_w, k = timed("PSIS weights (arviz_stats)", lambda: ns["psis_log_weights"](loglik))
w = ns["normalized_weights"](log_w)
table = {}
timed(
    "weighted mean + quantiles, all terms",
    lambda: [ns["_stats"](f"{n}_usd", v, w, table) for n, v in dollars.items()],
)
timed("weighted quantiles, estimate + fitted", lambda: [ns["_stats"]("e", rent, w, table), ns["_stats"]("f", rent, w, table)])
from scipy import stats

timed("PIT (scipy t.cdf)", lambda: ((stats.t.cdf((log_ask[None] - total) / sigma, nu[:, None])) * w).sum(0))
probs = [p for _, lo, hi in ns["PREDICTIVE"] for p in (lo, hi)]
timed("predictive 80/95 quantiles (Newton)", lambda: ns["predictive_quantiles"](total, sigma, nu, w, probs))
timed(
    "inputs JSON (40 keys a row)",
    lambda: [json.dumps({f"feature_{j}": round(0.1 * j, 4) for j in range(40)}, separators=(",", ":")) for _ in range(N)],
)

# The JAX unit-level step (summary.loo_unit_levels), CPU here instead of the GPU.
import jax
import jax.numpy as jnp
from jax.scipy.special import gammaln, logsumexp

jax.config.update("jax_enable_x64", True)


def student_t_logpdf(x, nu, scale):
    z = x / scale
    return gammaln((nu + 1) / 2) - gammaln(nu / 2) - 0.5 * jnp.log(nu * math.pi) - jnp.log(scale) - (nu + 1) / 2 * jnp.log1p(z * z / nu)


lo, hi, n = (-40.0, 40.0, 401)
z = jnp.linspace(lo, hi, n)
step = (hi - lo) / (n - 1)
seg = np.sort(rng.integers(0, N // 2, N))
_, seg = np.unique(seg, return_inverse=True)
n_seg = N


@jax.jit
def unit_levels(y, rest, seg, nu, sig, us, keys):
    ones = jnp.ones(y.shape[0])

    def one(args):
        rest_s, nu_s, sig_s, us_s, key = args
        w = -0.5 * z * z - 0.5 * math.log(2 * math.pi) + math.log(step)
        ll = student_t_logpdf((y - rest_s)[:, None] - us_s * z[None, :], nu_s, sig_s)
        total = jax.ops.segment_sum(ll, seg, num_segments=n_seg)
        count = jax.ops.segment_sum(ones, seg, num_segments=n_seg)
        log_unit = logsumexp(total + w[None], axis=1)
        others = total[seg] - ll + w[None]
        log_rest = jnp.where(count[seg] == 1, 0.0, logsumexp(others, axis=1))
        cell = jax.random.categorical(key, others, axis=1)
        return log_unit[seg] - log_rest, us_s * z[cell]

    return jax.lax.map(one, (rest, nu, sig, us, keys))


args = (
    jnp.asarray(log_ask),
    jnp.asarray(total),
    jnp.asarray(seg),
    jnp.asarray(nu),
    jnp.asarray(sigma[:, 0]),
    jnp.full(D, 0.08),
    jax.random.split(jax.random.PRNGKey(0), D),
)
jax.block_until_ready(unit_levels(*args))  # compile
timed("unit levels, JAX float64 on CPU", lambda: jax.block_until_ready(unit_levels(*args)))

print(f"per chunk of {N} rows x {D} draws x {T} terms; NB9 = {CHUNKS} chunks (266,513 rows)")
tot = 0.0
for name, s in sorted(timings.items(), key=lambda kv: -kv[1]):
    tot += s
    print(f"{name:42s} {s:7.2f} s/chunk  {s * CHUNKS / 60:6.1f} min for NB9")
print(f"{'total of these steps':42s} {tot:7.2f} s/chunk  {tot * CHUNKS / 60:6.1f} min for NB9")
