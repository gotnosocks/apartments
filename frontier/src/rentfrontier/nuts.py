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
    "building_dev",
    "building_total_dev",
    "bedroom_slope_dev",
    "unit",
    "unit_total",
    "unit_decentered",
    "unit_total_decentered",
    "walk_step",
    "walk_step_decentered",
    "walk_free",
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
    # "season_zerosum", "building_zerosum", "building_totals", "unit_totals",
    # "unit_partial", "walk_levels", "slope_totals".
    # They change how NUTS moves, not the model.
    coordinates: tuple = ()
    # float32 arithmetic (run.py leaves jax_enable_x64 off). The RTX 2060 runs
    # float32 at full rate but float64 at about 1/32; scoring (loo, variance)
    # still runs in float64 from the kept draws.
    float32: bool = False
    # Chains start at unconstrained values drawn uniformly in (-r, r) (NumPyro's
    # init_to_uniform; its default r = 2). The flat totals and levels are on
    # the log-rent scale, where 2 is a factor of 7.
    init_radius: float = 2.0
    # Warmup runs in this many equal segments (when they divide it; one
    # compilation either way), logging each segment's time (the first
    # includes compilation), leapfrog steps and step sizes.
    warmup_segments: int = 5
    # Warm start from NumPyro SVI with a mean-field normal guide (AutoNormal,
    # Adam) run for this many steps first (0 = off): each chain starts at a
    # draw from the fitted guide, and its variances are the initial inverse
    # mass matrix, which NumPyro's windowed adaptation then refines. With
    # the identity as the initial metric, the first warmup iterations run
    # the deepest trees. Counted in the fit time.
    svi_steps: int = 0
    svi_lr: float = 0.01
    svi_guide: str = "normal"  # or "lowrank"
    svi_rank: int = 20
    # False: keep the initial (SVI) metric through warmup and adapt only the
    # step size. NumPyro's windowed estimates are regularized as in Stan,
    # adding 1e-3 * 5 / (n + 5) to every variance: after the first 25-draw
    # window no coordinate's metric sd is below 0.013, where the tightest
    # posterior sds (data-rich building totals, market levels) are a few
    # thousandths, so the step size falls (7229ef0: m0q from 0.07-0.13 to
    # 0.014-0.045).
    adapt_mass: bool = True

    def to_dict(self):
        return asdict(self)


def run(
    prep: model_module.Prepared,
    config: model_module.ModelConfig,
    settings: Settings,
    log=print,
):
    from numpyro.infer import NUTS, init_to_uniform
    from numpyro.infer.util import initialize_model

    from .collect import batched

    if jax.config.jax_enable_x64 == settings.float32:
        raise RuntimeError(
            "jax_enable_x64 must be off for float32 NUTS and on otherwise (run.py sets it)"
        )
    dtype = jnp.float32 if settings.float32 else jnp.float64
    t0 = time.perf_counter()
    present = {
        "walk_step": config.building_walk and "walk_levels" not in settings.coordinates,
        "unit_drift": config.unit_drift,
    }
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
    init = [None] * settings.chains
    metric, svi_info = None, None
    if settings.svi_steps:
        init, metric, svi_info = svi_start(model_fn, dense, settings, log)
    elif not settings.adapt_mass:
        raise ValueError("a fixed metric (adapt_mass=False) needs the SVI warm start")
    kernel = NUTS(
        model_fn,
        target_accept_prob=settings.target_accept,
        max_tree_depth=settings.max_tree_depth,
        dense_mass=[tuple(dense)] if dense else (False if metric is None else []),
        inverse_mass_matrix=metric,
        adapt_mass_matrix=settings.adapt_mass,
        init_strategy=init_to_uniform(radius=settings.init_radius),
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
        kernel.init(k, settings.warmup, init_params=z, model_args=(), model_kwargs={})
        for k, z in zip(jax.random.split(k_init, settings.chains), init)
    ]
    states = jax.tree.map(lambda *xs: jnp.stack(xs), *inits)

    def step(k, st):
        st = kernel.sample(st._replace(rng_key=k), (), {})
        info = {"divergent": st.diverging, "steps": st.num_steps}
        return st, info | {"accept": st.accept_prob}

    def warm(state, keys):
        def body(st, k):
            st, info = step(k, st)
            return st, info["steps"]

        return jax.lax.scan(body, state, keys)

    setup_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    keys = jax.vmap(lambda k: jax.random.split(k, settings.warmup))(
        jax.random.split(k_warm, settings.chains)
    )
    segments = settings.warmup_segments
    if not segments or settings.warmup % segments:
        segments = 1
    length = settings.warmup // segments
    warm_segment = jax.jit(vmap(warm))
    for i in range(segments):
        t1 = time.perf_counter()
        states, steps = warm_segment(states, keys[:, i * length : (i + 1) * length])
        steps = np.asarray(steps)
        log(
            f"segment {i + 1}/{segments} of warmup: {time.perf_counter() - t1:.0f}s, "
            f"{steps.mean():.0f} leapfrog steps per iteration (by chain "
            f"{np.round(steps.mean(axis=1)).astype(int).tolist()}), step size "
            f"{np.round(np.asarray(states.adapt_state.step_size), 4).tolist()}"
        )
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
    out["svi"] = svi_info
    return out


def svi_start(model_fn, dense, settings: Settings, log):
    """Starting points (unconstrained, one per chain) and an initial inverse
    mass matrix from NumPyro SVI: a mean-field normal guide ("normal") or a
    low-rank multivariate normal ("lowrank", whose covariance gives the dense
    globals' block its correlations)."""
    from jax.flatten_util import ravel_pytree
    from numpyro.infer import SVI, Trace_ELBO, init_to_uniform
    from numpyro.infer.autoguide import AutoLowRankMultivariateNormal, AutoNormal
    from numpyro.infer.util import initialize_model
    from numpyro.optim import Adam

    t0 = time.perf_counter()
    key = jax.random.fold_in(jax.random.PRNGKey(settings.seed), 1)
    k_fit, k_draw = jax.random.split(key)
    init_loc = init_to_uniform(radius=settings.init_radius)
    if settings.svi_guide == "lowrank":
        guide = AutoLowRankMultivariateNormal(
            model_fn, rank=settings.svi_rank, init_loc_fn=init_loc
        )
    elif settings.svi_guide == "normal":
        guide = AutoNormal(model_fn, init_loc_fn=init_loc)
    else:
        raise ValueError(f"unknown svi_guide {settings.svi_guide!r}")
    svi = SVI(model_fn, guide, Adam(settings.svi_lr), Trace_ELBO())
    fit = svi.run(k_fit, settings.svi_steps, progress_bar=False)
    params = jax.device_get(fit.params)
    # The unconstrained latent vector, in the sorted-site order both the guide
    # and NumPyro's mass-matrix blocks flatten it in: covariance F F' + diag(d).
    z = initialize_model(jax.random.PRNGKey(0), model_fn).param_info.z
    _, unravel = ravel_pytree(z)
    if settings.svi_guide == "lowrank":
        loc = params["auto_loc"]
        factor = params["auto_cov_factor"] * params["auto_scale"][:, None]
        diag = params["auto_scale"] ** 2
    else:
        loc = ravel_pytree({k: params[f"{k}_auto_loc"] for k in z})[0]
        diag = ravel_pytree({k: params[f"{k}_auto_scale"] for k in z})[0] ** 2
        factor = jnp.zeros((loc.size, 0))
    init = []
    for kc in jax.random.split(k_draw, settings.chains):
        k1, k2 = jax.random.split(kc)
        e1 = jax.random.normal(k1, (factor.shape[1],))
        e2 = jax.random.normal(k2, loc.shape)
        init.append(unravel(loc + factor @ e1 + jnp.sqrt(diag) * e2))
    index = {
        k: np.asarray(v).astype(int).ravel()
        for k, v in unravel(jnp.arange(loc.size, dtype=loc.dtype)).items()
    }
    variance = (factor**2).sum(axis=1) + diag
    metric = {(k,): variance[index[k]] for k in z if k not in dense}
    if dense:
        i = np.concatenate([index[k] for k in dense])
        metric[tuple(dense)] = factor[i] @ factor[i].T + jnp.diag(diag[i])
    losses = np.asarray(fit.losses)
    seconds = time.perf_counter() - t0
    log(
        f"svi ({settings.svi_guide}) {settings.svi_steps} steps {seconds:.1f}s, loss "
        f"{losses[0]:.4g} -> {losses[-1]:.4g} (mean of the last 10%: "
        f"{losses[-len(losses) // 10 :].mean():.4g})"
    )
    info = {
        "guide": settings.svi_guide,
        "seconds": seconds,
        "final_loss": float(losses[-1]),
    }
    return init, metric, info
