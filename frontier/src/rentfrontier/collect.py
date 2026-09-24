"""On-device posterior bookkeeping shared by all samplers.

Given a per-chain transition `step(key, state) -> (state, info)` and a map
`params(state) -> constrained site values` (the NumPyro site names used by
`model.effects`), run the retained draws for every chain under vmap and keep:

- per-row held-out log predictive density (log-sum-exp over draws);
- running sums and sums of squares of every named effect;
- traces of scalars, coefficients, sampled trend points and a fixed random
  subset of building and unit effects, for R-hat / ESS;
- one joint draw of all effects every `keep_every` draws, for contributions.
"""

from __future__ import annotations

import math

import jax
import jax.numpy as jnp
import numpy as np
from jax.scipy.special import gammaln, logsumexp

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
    "walk_scale",
    "bedroom_time_scale",
    "bedroom_slope_scale",
    "unit_nu",
    "unit_drift_scale",
)


def student_t_logpdf(x, nu, scale):
    z = x / scale
    return (
        gammaln((nu + 1) / 2)
        - gammaln(nu / 2)
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
    drift_scale = p.get("unit_drift_scale", jnp.zeros(()))
    if "unit_drift" in p:
        u = u + p["unit_drift"][jnp.maximum(test.unit, 0)] * test.unit_time
    # Unseen unit: level and drift are both unknown. For Gaussian units their
    # sum is exactly N(0, tau^2 + tau_d^2 t^2); for Student-t units the scale
    # is widened the same way (an approximation to the t-normal convolution).
    unit_scale = jnp.sqrt(p["unit_scale"] ** 2 + (drift_scale * test.unit_time) ** 2)
    lp_seen = student_t_logpdf(test.y - mu - u, p["nu"], p["sigma"])
    x, w = (jnp.asarray(a, mu.dtype) for a in np.polynomial.hermite.hermgauss(GH_NODES))
    shifted = (
        test.y[:, None] - mu[:, None] - math.sqrt(2.0) * unit_scale[:, None] * x[None]
    )
    lp_new = logsumexp(
        student_t_logpdf(shifted, p["nu"], p["sigma"]) + jnp.log(w)[None], axis=1
    ) - 0.5 * math.log(math.pi)
    # Student-t unit prior (unit_nu > 0): integrate on a fixed grid in units
    # of unit_scale; the grid spacing (0.1 scale) is well below sigma.
    nu_u = p.get("unit_nu", jnp.zeros(()))
    z = jnp.linspace(-40.0, 40.0, 801, dtype=mu.dtype)
    log_wz = student_t_logpdf(z, jnp.maximum(nu_u, 1e-3), 1.0) + math.log(0.1)
    shifted_t = test.y[:, None] - mu[:, None] - unit_scale[:, None] * z[None]
    lp_new_t = logsumexp(
        student_t_logpdf(shifted_t, p["nu"], p["sigma"]) + log_wz[None], axis=1
    )
    lp_new = jnp.where(nu_u > 0, lp_new_t, lp_new)
    return jnp.where(seen, lp_seen, lp_new)


def device_arrays(a: model_module.Arrays, dtype) -> model_module.Arrays:
    return a.map(
        lambda v: (
            jnp.asarray(v, dtype)
            if np.issubdtype(np.asarray(v).dtype, np.floating)
            else jnp.asarray(v)
        )
    )


def trace_indices(prep, n, seed):
    rng = np.random.default_rng(seed)
    b = np.sort(
        rng.choice(len(prep.buildings), min(n, len(prep.buildings)), replace=False)
    )
    u = np.sort(rng.choice(len(prep.units), min(n, len(prep.units)), replace=False))
    return jnp.asarray(b), jnp.asarray(u)


def collect(
    step,
    params,
    states,
    key,
    prep,
    draws,
    keep_every,
    dtype,
    trace_seed,
    n_trace=32,
    vmap=jax.vmap,
):
    """Run `draws` retained transitions per chain and summarise them."""
    test = device_arrays(prep.test, dtype)
    trace_b, trace_u = trace_indices(prep, n_trace, trace_seed)
    n_blocks = draws // keep_every

    def one_chain(state, chain_key):
        def transition(carry, k):
            st, acc, s1, s2 = carry
            st, info = step(k, st)
            p = params(st)
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
                "fslope_scales": e["fslope_scales"],
                **info,
            }
            return (st, acc, s1, s2), trace

        def block(carry, keys):
            carry, trace = jax.lax.scan(transition, carry, keys)
            return carry, (trace, model_module.effects(params(carry[0])))

        zeros = jax.tree.map(jnp.zeros_like, model_module.effects(params(state)))
        carry = (state, jnp.full(test.y.shape, -jnp.inf, dtype), zeros, zeros)
        keys = jax.random.split(chain_key, n_blocks * keep_every).reshape(
            n_blocks, keep_every, -1
        )
        (_, acc, s1, s2), (trace, kept) = jax.lax.scan(block, carry, keys)
        trace = jax.tree.map(lambda a: a.reshape(-1, *a.shape[2:]), trace)
        return acc, s1, s2, trace, kept

    n_chains = jax.tree.leaves(states)[0].shape[0]
    acc, s1, s2, trace, kept = jax.jit(vmap(one_chain))(
        states, jax.random.split(key, n_chains)
    )
    n = n_blocks * keep_every * n_chains
    acc = np.asarray(acc, np.float64)
    m = acc.max(axis=0)
    lpd = m + np.log(np.exp(acc - m).sum(axis=0)) - math.log(n)
    mean = jax.tree.map(lambda a: np.asarray(a, np.float64).sum(0) / n, s1)
    var = jax.tree.map(
        lambda a, mu: np.asarray(a, np.float64).sum(0) / n - mu * mu, s2, mean
    )
    return {
        "rhat_all": all_effects_rhat(s1, s2, n // n_chains),
        "lpd": lpd,
        "lpd_chain": acc - math.log(n // n_chains),
        "mean": mean,
        "sd": jax.tree.map(lambda v: np.sqrt(np.maximum(v, 0)), var),
        "trace": jax.tree.map(np.asarray, trace),
        "kept": jax.tree.map(np.asarray, kept),
        "trace_buildings": np.asarray(trace_b),
        "trace_units": np.asarray(trace_u),
    }


def all_effects_rhat(s1, s2, n):
    """R-hat for every element of every named effect, from per-chain moments.

    s1, s2: per-chain running sums and sums of squares, leading axis = chain;
    n: draws per chain. Catches chains stuck in different modes for any single
    building, unit or coefficient, which a sample of traced effects can miss.
    """
    out = {}
    for key in s1:
        a1 = np.asarray(s1[key], np.float64)
        a2 = np.asarray(s2[key], np.float64)
        if a1.ndim < 1 or a1.shape[0] < 2:
            continue
        m = a1 / n
        v = np.maximum(a2 / n - m * m, 0.0) * n / (n - 1)
        w = v.mean(axis=0)
        b = n * m.var(axis=0, ddof=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.sqrt(((n - 1) / n * w + b / n) / w)
        r = np.where(w > 0, r, 1.0).ravel()
        if r.size == 0:
            continue
        i = int(np.nanargmax(r))
        out[key] = {
            "max": float(np.nanmax(r)),
            "argmax": i,
            "over_1_05": int((r > 1.05).sum()),
            "size": int(r.size),
        }
    return out
