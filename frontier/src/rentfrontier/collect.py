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
    "market_drift",
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


def heldout_logpdf(p, test: model_module.Arrays, unseen: bool = True):
    """Log predictive density of each held-out row under one draw.

    Rows whose unit has no training rows (only when `unseen`) integrate the
    unit effect over its prior; see `heldout_logpdf_given_mu`.
    """
    mu = model_module.linear_predictor(p, test, include_unit=False)
    u = p["unit"][jnp.maximum(test.unit, 0)]
    if "unit_drift" in p:
        u = u + p["unit_drift"][jnp.maximum(test.unit, 0)] * test.unit_time
    return heldout_logpdf_given_mu(p, test, mu, u, unseen)


def heldout_logpdf_given_mu(p, test: model_module.Arrays, mu, u, unseen: bool = True):
    """Held-out log density from the predictor without unit terms (`mu`) and
    the unit level plus drift of seen units (`u`, ignored for unseen units).

    `p` needs nu, sigma, unit_scale and optionally unit_drift_scale, unit_nu.
    Unseen units integrate the unit effect over its prior:
    - Gaussian units: level + drift is N(0, tau^2 + tau_d^2 t^2), by
      Gauss-Hermite quadrature;
    - Student-t units: the level on a fixed grid over its t prior and, with a
      unit drift, the drift s ~ N(0, tau_d^2) by 8-node Gauss-Hermite, i.e.
      an exact 2-D quadrature of the t-level plus normal-drift convolution.
    """
    seen = test.unit >= 0
    lp_seen = student_t_logpdf(test.y - mu - u, p["nu"], p["sigma"])
    if not unseen:
        return lp_seen

    drift_scale = p.get("unit_drift_scale", jnp.zeros(()))
    xt = test.unit_time
    # Gaussian units: level + drift together.
    gauss_scale = jnp.sqrt(p["unit_scale"] ** 2 + (drift_scale * xt) ** 2)
    x, w = (jnp.asarray(a, mu.dtype) for a in np.polynomial.hermite.hermgauss(GH_NODES))
    shifted = (
        test.y[:, None] - mu[:, None] - math.sqrt(2.0) * gauss_scale[:, None] * x[None]
    )
    lp_gauss = logsumexp(
        student_t_logpdf(shifted, p["nu"], p["sigma"]) + jnp.log(w)[None], axis=1
    ) - 0.5 * math.log(math.pi)
    # Student-t units: level on a grid (spacing 0.2 unit scale), drift by GH.
    nu_u = p.get("unit_nu", jnp.zeros(()))
    z = jnp.linspace(-40.0, 40.0, 401, dtype=mu.dtype)
    log_wz = student_t_logpdf(z, jnp.maximum(nu_u, 1e-3), 1.0) + math.log(0.2)
    xd, wd = (jnp.asarray(a, mu.dtype) for a in np.polynomial.hermite.hermgauss(8))
    drift_nodes = math.sqrt(2.0) * drift_scale * xt[:, None] * xd[None]  # (rows, 8)
    shifted_t = (
        test.y[:, None, None]
        - mu[:, None, None]
        - p["unit_scale"] * z[None, None, :]
        - drift_nodes[:, :, None]
    )  # (rows, 8, grid)
    inner = logsumexp(
        student_t_logpdf(shifted_t, p["nu"], p["sigma"]) + log_wz[None, None], axis=2
    )
    lp_t = logsumexp(inner + jnp.log(wd)[None], axis=1) - 0.5 * math.log(math.pi)
    lp_new = jnp.where(nu_u > 0, lp_t, lp_gauss)
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
    has_unseen = bool((np.asarray(prep.test.unit) < 0).any())
    trace_b, trace_u = trace_indices(prep, n_trace, trace_seed)
    n_blocks = draws // keep_every

    def one_chain(state, chain_key):
        def transition(carry, k):
            st, acc, s1, s2 = carry
            st, info = step(k, st)
            p = params(st)
            e = model_module.effects(p)
            acc = jnp.logaddexp(acc, heldout_logpdf(p, test, has_unseen))
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


def batched(fn, chains, batch):
    """vmap `fn` over chains, `batch` chains at a time (lax.map over groups)."""
    if not batch or batch >= chains:
        return jax.vmap(fn)
    if chains % batch:
        raise ValueError("chains must be a multiple of chain_batch")

    def run(*args):
        grouped = jax.tree.map(
            lambda a: a.reshape(chains // batch, batch, *a.shape[1:]), args
        )
        out = jax.lax.map(lambda g: jax.vmap(fn)(*g), grouped)
        return jax.tree.map(lambda a: a.reshape(chains, *a.shape[2:]), out)

    return run


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
