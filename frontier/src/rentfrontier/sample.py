"""Many-chain GPU sampling with BlackJAX ChEES-HMC.

The NumPyro model supplies the unconstrained log density. Adaptation
(step size, trajectory length, diagonal mass matrix) is pooled across all
chains (Hoffman, Radul & Sountsov 2021). After warmup every chain takes a
short run of draws. Everything the leaderboard and contribution reports need
is accumulated on the device during sampling, so the full posterior is never
held in memory:

- per-row held-out log predictive density (pooled log-mean-exp over draws);
- posterior mean and variance of every named effect;
- traces of scalars, coefficients and a random subset of group effects for
  R-hat / ESS;
- a thinned set of joint draws for dollar contributions.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass

import blackjax
import blackjax.adaptation.base
import jax
import jax.flatten_util
import jax.numpy as jnp
import numpy as np
import numpyro.optim
import optax
from jax.scipy.special import logsumexp
from numpyro.infer.util import initialize_model

from . import model as model_module

GH_NODES = 48
SCALARS = (
    "alpha",
    "sigma",
    "nu",
    "unit_scale",
    "building_scale",
    "trend_scale",
    "season_scale",
)


@dataclass(frozen=True)
class Settings:
    chains: int = 128
    warmup: int = 1000
    draws: int = 200
    keep_every: int = 50  # joint draws kept per chain every this many draws
    learning_rate: float = 0.025
    # Starts: draws from a mean-field ADVI fit (NumPyro SVI, AutoNormal), with
    # the guide's scale inflated so chains start overdispersed. Maximising the
    # joint density instead collapses to the degenerate sigma -> 0 mode.
    vi_steps: int = 3000
    vi_learning_rate: float = 0.01
    init_inflation: float = 2.0
    seed: int = 20260923
    trace_groups: int = 32
    adaptation: str = "chees"  # "chees" (jittered HMC) or "meads" (generalized HMC)
    mass_matrix: str | None = (
        "diagonal"  # ChEES ensemble diagonal metric, or None (identity)
    )

    def to_dict(self):
        return asdict(self)


def _student_t_logpdf(x, nu, scale):
    z = x / scale
    return (
        jax.scipy.special.gammaln((nu + 1) / 2)
        - jax.scipy.special.gammaln(nu / 2)
        - 0.5 * jnp.log(nu * math.pi)
        - jnp.log(scale)
        - (nu + 1) / 2 * jnp.log1p(z * z / nu)
    )


def heldout_logpdf(p, test: model_module.Arrays):
    """Log predictive density of each held-out row under one draw.

    Rows whose unit has no training rows integrate the unit effect over its
    prior N(0, unit_scale^2) by Gauss-Hermite quadrature.
    """
    mu = model_module.linear_predictor(p, test, include_unit=False)
    seen = test.unit >= 0
    u = p["unit"][jnp.maximum(test.unit, 0)]
    lp_seen = _student_t_logpdf(test.y - mu - u, p["nu"], p["sigma"])
    x, w = (jnp.asarray(a, mu.dtype) for a in np.polynomial.hermite.hermgauss(GH_NODES))
    shifted = test.y[:, None] - mu[:, None] - math.sqrt(2.0) * p["unit_scale"] * x[None]
    lp_new = logsumexp(
        _student_t_logpdf(shifted, p["nu"], p["sigma"]) + jnp.log(w)[None], axis=1
    ) - 0.5 * math.log(math.pi)
    return jnp.where(seen, lp_seen, lp_new)


def run(
    prep: model_module.Prepared,
    config: model_module.ModelConfig,
    settings: Settings,
    log=print,
):
    dtype = jnp.float64 if jax.config.jax_enable_x64 else jnp.float32
    key = jax.random.PRNGKey(settings.seed)
    info = initialize_model(
        key, model_module.build_model(prep, config), dynamic_args=False
    )
    flat0, unravel = jax.flatten_util.ravel_pytree(info.param_info.z)
    dim = flat0.size

    def logdensity(x):
        return -info.potential_fn(unravel(x))

    def constrained(x):
        return info.postprocess_fn(unravel(x))

    test = model_module.Arrays(
        *(
            jnp.asarray(getattr(prep.test, f))
            for f in ("y", "x", "month", "calendar", "building", "unit")
        )
    )
    test = model_module.Arrays(
        test.y.astype(dtype),
        test.x.astype(dtype),
        test.month,
        test.calendar,
        test.building,
        test.unit,
    )
    rng = np.random.default_rng(settings.seed)
    trace_b = jnp.asarray(
        np.sort(rng.choice(len(prep.buildings), settings.trace_groups, replace=False))
    )
    trace_u = jnp.asarray(
        np.sort(rng.choice(len(prep.units), settings.trace_groups, replace=False))
    )

    k_init, k_warm, k_sample = jax.random.split(key, 3)
    t0 = time.perf_counter()
    loc, scale, elbo = _advi(prep, config, settings, info, k_init)
    z = jax.random.normal(jax.random.fold_in(k_init, 1), (settings.chains, dim), dtype)
    init = (loc[None] + settings.init_inflation * scale[None] * z).astype(dtype)
    jax.block_until_ready(init)
    init_seconds = time.perf_counter() - t0
    lp = jax.vmap(logdensity)(init)
    log(
        f"advi init {init_seconds:.1f}s final elbo loss={elbo:.1f} logdensity median={float(jnp.median(lp)):.1f}"
    )

    # ---------------------------------------------------------------- warmup
    t0 = time.perf_counter()
    no_info = blackjax.adaptation.base.get_filter_adapt_info_fn()
    if settings.adaptation == "chees":
        warmup = blackjax.chees_adaptation(
            logdensity,
            settings.chains,
            mass_matrix_estimation=settings.mass_matrix,
            # The length floor tracks a dense dim x dim covariance (2.2 GB at
            # dim 23.5k in float32), too large for the local card.
            _length_floor=False,
            adaptation_info_fn=no_info,
        )
        (states, params), _ = warmup.run(
            k_warm, init, 0.01, optax.adam(settings.learning_rate), settings.warmup
        )
        kernel = blackjax.dynamic_hmc(logdensity, **params)
        adapted = {
            "step_size": float(params["step_size"]),
            "leapfrog_steps": float(params["integration_steps_params"][0]),
        }
    elif settings.adaptation == "meads":
        warmup = blackjax.meads_adaptation(
            logdensity, settings.chains, adaptation_info_fn=no_info
        )
        (states, params), _ = warmup.run(k_warm, init, settings.warmup)
        kernel = blackjax.ghmc(logdensity, **params)
        adapted = {k: float(params[k]) for k in ("step_size", "alpha", "delta")}
    else:
        raise ValueError(settings.adaptation)
    jax.block_until_ready(states)
    warmup_seconds = time.perf_counter() - t0
    log(f"warmup {warmup_seconds:.1f}s {adapted}")

    # -------------------------------------------------------------- sampling
    def one_chain(state, chain_key):
        def step(carry, k):
            st, acc, s1, s2 = carry
            st, inf = kernel.step(k, st)
            p = constrained(st.position)
            e = model_module.effects(p)
            acc = jnp.logaddexp(acc, heldout_logpdf(p, test))
            s1 = jax.tree.map(lambda a, v: a + v, s1, e)
            s2 = jax.tree.map(lambda a, v: a + v * v, s2, e)
            trace = {
                "scalars": jnp.stack([e[n] for n in SCALARS]),
                "beta": e["beta"],
                "trend": e["trend"][::12],
                "building": e["building"][trace_b],
                "unit": e["unit"][trace_u],
                "accept": inf.acceptance_rate,
                "divergent": inf.is_divergent,
                "steps": getattr(inf, "num_integration_steps", jnp.ones((), jnp.int32)),
            }
            return (st, acc, s1, s2), trace

        def block(carry, keys):
            carry, trace = jax.lax.scan(step, carry, keys)
            return carry, (trace, model_module.effects(constrained(carry[0].position)))

        zeros = jax.tree.map(
            jnp.zeros_like, model_module.effects(constrained(state.position))
        )
        carry = (state, jnp.full(test.y.shape, -jnp.inf, dtype), zeros, zeros)
        n_blocks = settings.draws // settings.keep_every
        keys = jax.random.split(chain_key, n_blocks * settings.keep_every).reshape(
            n_blocks, settings.keep_every, -1
        )
        (_, acc, s1, s2), (trace, kept) = jax.lax.scan(block, carry, keys)
        trace = jax.tree.map(lambda a: a.reshape(-1, *a.shape[2:]), trace)
        return acc, s1, s2, trace, kept

    t0 = time.perf_counter()
    acc, s1, s2, trace, kept = jax.jit(jax.vmap(one_chain))(
        states, jax.random.split(k_sample, settings.chains)
    )
    jax.block_until_ready(acc)
    sampling_seconds = time.perf_counter() - t0
    log(f"sampling {sampling_seconds:.1f}s")

    n = (settings.draws // settings.keep_every) * settings.keep_every * settings.chains
    acc = np.asarray(acc, np.float64)
    lpd = _logsumexp_np(acc) - math.log(n)
    mean = jax.tree.map(lambda a: np.asarray(a, np.float64).sum(0) / n, s1)
    var = jax.tree.map(
        lambda a, m: np.asarray(a, np.float64).sum(0) / n - m * m, s2, mean
    )
    return {
        "lpd": lpd,
        "lpd_chain": acc - math.log(n // settings.chains),
        "mean": mean,
        "sd": jax.tree.map(lambda v: np.sqrt(np.maximum(v, 0)), var),
        "trace": jax.tree.map(np.asarray, trace),
        "kept": jax.tree.map(np.asarray, kept),
        "trace_buildings": np.asarray(trace_b),
        "trace_units": np.asarray(trace_u),
        "dim": int(dim),
        "adaptation": adapted,
        "seconds": {
            "init": init_seconds,
            "warmup": warmup_seconds,
            "sampling": sampling_seconds,
        },
        "dtype": str(np.dtype(dtype)),
    }


def _advi(prep, config, settings, info, key):
    """Mean-field ADVI; returns loc and scale in the sampler's flat ordering."""
    import numpyro.infer
    import numpyro.infer.autoguide

    model = model_module.build_model(prep, config)
    guide = numpyro.infer.autoguide.AutoNormal(model, init_scale=0.05)
    svi = numpyro.infer.SVI(
        model,
        guide,
        numpyro.optim.Adam(settings.vi_learning_rate),
        numpyro.infer.Trace_ELBO(),
    )
    result = svi.run(key, settings.vi_steps, progress_bar=False)
    names = list(info.param_info.z)
    loc = {n: result.params[f"{n}_auto_loc"] for n in names}
    scale = {n: result.params[f"{n}_auto_scale"] for n in names}
    flat_loc, _ = jax.flatten_util.ravel_pytree(loc)
    flat_scale, _ = jax.flatten_util.ravel_pytree(scale)
    return flat_loc, flat_scale, float(result.losses[-100:].mean())


def _logsumexp_np(a):
    m = a.max(axis=0)
    return m + np.log(np.exp(a - m).sum(axis=0))
