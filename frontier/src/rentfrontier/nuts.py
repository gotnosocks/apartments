"""NumPyro NUTS on `model.build_model`, bookkept exactly like the Gibbs sampler.

    python -m rentfrontier.run --sampler nuts --model L3-season --split rows ...

Warmup is NumPyro's own adaptation (step size and diagonal mass matrix over
`warmup` iterations of its NUTS kernel). The retained draws then run through
`collect.collect`, the Gibbs sampler's on-device bookkeeping, so a NUTS run
has the same held-out scores, traces, kept draws and all-effects R-hat, and
is scored by the same PSIS-LOO and variance code.

Parameterization changes how NUTS moves, not the model. Sites are centred,
as written in `build_model`, except `NONCENTERED`: the building walk and the
unit drift. Most building half-years and most units carry too little data
to inform those steps, and centred NUTS mixes badly near a small scale. The
trend, season, building and unit levels are data-rich; non-centring them made
NUTS diverge at their scales (the removed model ladder at 3c26c4a: 1 and 6
divergences on L2 and L3).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace

import jax
import jax.numpy as jnp
import numpy as np

from . import collect as collect_module
from . import model as model_module

NONCENTERED = ("walk_step", "unit_drift")
# Per-building and per-unit sites; every other site is global (the intercept,
# coefficients, trend and season steps and every scale: about 130 numbers).
LOCAL_SITES = {
    "building",
    "unit",
    "unit_total",
    "walk_step",
    "walk_step_decentered",
    "bedroom_slope",
    "fslope",
    "unit_drift",
    "unit_drift_decentered",
}


@dataclass(frozen=True)
class Settings:
    chains: int = 4
    warmup: int = 1000
    draws: int = 1000
    keep_every: int = 4  # one joint draw kept per chain every this many draws
    seed: int = 20260925
    target_accept: float = 0.8
    max_tree_depth: int = 10
    trace_groups: int = 32
    chain_batch: int | None = None  # vectorise this many chains at a time
    # NumPyro's structured mass matrix: dense over the global sites (their
    # posterior correlations make diagonal-mass trees deep), diagonal over the
    # per-building and per-unit arrays.
    dense_globals: bool = False
    # Sampling coordinates (model.ModelConfig.coordinates): "trend_levels",
    # "unit_totals". They change how NUTS moves, not the model.
    coordinates: tuple = ()
    # float32 arithmetic (run.py leaves jax_enable_x64 off). The RTX 2060 runs
    # float32 at full rate but float64 at about 1/32; scoring (loo, variance)
    # still runs in float64 from the kept draws.
    float32: bool = False

    def to_dict(self):
        return asdict(self)


def run(
    prep: model_module.Prepared,
    config: model_module.ModelConfig,
    settings: Settings,
    log=print,
):
    from numpyro.infer import NUTS
    from numpyro.infer.util import initialize_model

    from .gibbs import batched

    if jax.config.jax_enable_x64 == settings.float32:
        raise RuntimeError(
            "jax_enable_x64 must be off for float32 NUTS and on otherwise (run.py sets it)"
        )
    dtype = jnp.float32 if settings.float32 else jnp.float64
    t0 = time.perf_counter()
    present = {"walk_step": config.building_walk, "unit_drift": config.unit_drift}
    config = replace(
        config,
        noncentered=tuple(s for s in NONCENTERED if present[s]),
        coordinates=tuple(settings.coordinates),
    )
    model_fn = model_module.build_model(prep, config)
    dense = []
    if settings.dense_globals:
        # The latent sites from NumPyro's own initialization: tracing a prior
        # draw would fail on the flat-prior `trend_absolute` site.
        z = initialize_model(jax.random.PRNGKey(0), model_fn).param_info.z
        dense = sorted(k for k in z if k not in LOCAL_SITES)
    kernel = NUTS(
        model_fn,
        target_accept_prob=settings.target_accept,
        max_tree_depth=settings.max_tree_depth,
        dense_mass=[tuple(dense)] if dense else False,
    )
    k_init, k_warm, k_draw = jax.random.split(jax.random.PRNGKey(settings.seed), 3)
    vmap = (
        (lambda fn: batched(fn, settings.chains, settings.chain_batch))
        if settings.chain_batch
        else jax.vmap
    )
    # One init per chain: a single key keeps the kernel's sample function
    # unbatched (NumPyro's vectorized init wraps it in vmap), so the chains
    # are vectorised here and in collect alike.
    inits = [
        kernel.init(k, settings.warmup, model_args=(), model_kwargs={})
        for k in jax.random.split(k_init, settings.chains)
    ]
    states = jax.tree.map(lambda *xs: jnp.stack(xs), *inits)

    def step(k, st):
        st = kernel.sample(st._replace(rng_key=k), (), {})
        info = {"divergent": st.diverging, "steps": st.num_steps}
        return st, info | {"accept": st.accept_prob}

    def warm(state, key):
        state, _ = jax.lax.scan(
            lambda st, k: (step(k, st)[0], None),
            state,
            jax.random.split(key, settings.warmup),
        )
        return state

    setup_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    states = jax.jit(vmap(warm))(states, jax.random.split(k_warm, settings.chains))
    jax.block_until_ready(states)
    warmup_seconds = time.perf_counter() - t0
    step_size = np.asarray(states.adapt_state.step_size)
    log(f"warmup {warmup_seconds:.1f}s step size {np.round(step_size, 4).tolist()}")

    fixed = model_module.constants(prep, config)
    constrain = kernel.postprocess_fn((), {})

    def params(st):
        return {**fixed, **constrain(st.z)}

    t0 = time.perf_counter()
    out = collect_module.collect(
        step,
        params,
        states,
        k_draw,
        prep,
        settings.draws,
        settings.keep_every,
        dtype,
        settings.seed,
        settings.trace_groups,
        vmap=vmap,
    )
    sampling_seconds = time.perf_counter() - t0
    steps = np.asarray(out["trace"]["steps"])
    divergences = int(np.asarray(out["trace"]["divergent"]).sum())
    log(
        f"sampling {sampling_seconds:.1f}s, {steps.mean():.0f} leapfrog steps per "
        f"draw, {divergences} divergences"
    )
    out["seconds"] = {
        "setup": setup_seconds,
        "warmup": warmup_seconds,
        "sampling": sampling_seconds,
    }
    out["dtype"] = str(np.dtype(dtype))
    out["sampler"] = "numpyro-nuts"
    out["noncentered"] = list(config.noncentered)
    out["step_size"] = step_size.tolist()
    out["mean_tree_steps"] = float(steps.mean())
    out["dense_sites"] = dense
    return out
