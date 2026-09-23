"""Structured blocked Gibbs sampler for the model in `model.build_model`.

Same posterior as the NumPyro model (same priors, Student-t likelihood).
The Student-t is written as a scale mixture: eps_i | lam_i ~ N(0, sigma^2 /
lam_i), lam_i ~ Gamma(nu/2, nu/2). One iteration:

1. All Gaussian latents jointly, given lam and the scales: intercept,
   feature coefficients, month trend, season, every building effect and
   every unit effect. Unit effects are integrated out analytically (each
   row has one unit, so their block is diagonal), buildings are eliminated
   in closed form (each unit sits in one building), leaving a dense
   ~260-dimensional global system. The draw is exact; there is no tuning
   and no funnel.
2. (sigma, nu) jointly by random-walk Metropolis with lam integrated out,
   then lam | sigma, nu (a partially collapsed Gibbs step, valid in this
   order).
3. Every group scale: independence Metropolis whose proposal is
   the exact conditional under a flat prior on the scale, so the accept
   ratio only carries the half-normal prior (acceptance ~1).

Chains run in parallel under vmap, in float64.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import jax
import jax.numpy as jnp
import numpy as np
from jax.scipy.linalg import solve_triangular

from . import collect as collect_module
from . import model as model_module


@dataclass(frozen=True)
class Settings:
    chains: int = 8
    warmup: int = 300
    draws: int = 1000
    keep_every: int = 50
    seed: int = 20260923
    noise_steps: int = 10  # joint (sigma, nu) Metropolis steps per iteration
    sigma_step_sd: float = 0.004  # on log sigma
    nu_step_sd: float = 0.03  # on log nu
    trace_groups: int = 32

    def to_dict(self):
        return asdict(self)


@dataclass
class Design:
    a: jnp.ndarray  # (N, P) global design
    y: jnp.ndarray
    unit: jnp.ndarray
    building: jnp.ndarray
    unit_building: jnp.ndarray
    slots: jnp.ndarray  # (N, 3) local slots each row touches in its building
    slot_values: jnp.ndarray  # (N, 3)
    prior_fixed: jnp.ndarray  # (P,) diagonal of the fixed prior precision
    local_structures: dict  # scale name -> (L, L) structure within a building block
    local_ranks: dict  # scale name -> rank per building
    trend: slice
    season: slice
    n_features: int
    n_units: int
    n_buildings: int
    n_local: int
    walk: bool
    prior_sd: dict

    @property
    def scale_names(self):
        return (
            "sigma",
            "unit_scale",
            "trend_scale",
            "season_scale",
            *self.local_structures,
        )


def _rw1_anchored(n):
    d = np.diff(np.eye(n + 1), axis=0)[:, 1:]  # steps from a fixed 0
    return d.T @ d


def build_design(
    prep: model_module.Prepared, config: model_module.ModelConfig
) -> Design:
    tr = prep.train
    n, f = tr.x.shape
    t = len(prep.periods)
    p = 1 + f + (t - 1) + 12
    a = np.zeros((n, p))
    a[:, 0] = 1.0
    a[:, 1 : 1 + f] = tr.x
    trend = slice(1 + f, 1 + f + t - 1)
    season = slice(trend.stop, trend.stop + 12)
    rows = np.flatnonzero(tr.month > 0)
    a[rows, trend.start + tr.month[rows] - 1] = 1.0
    # Season enters as season_raw - mean(season_raw), as in the NumPyro model.
    a[:, season] = -1.0 / 12
    a[np.arange(n), season.start + tr.calendar] += 1.0
    fixed = np.zeros(p)
    fixed[0] = 1.0
    fixed[1 : 1 + f] = 1.0 / (config.beta_sd * prep.features.prior_scale) ** 2
    unit_building = np.zeros(len(prep.units), dtype=np.int32)
    unit_building[tr.unit] = tr.building

    # Local block per building: [level, walk knots 1..n_knots-1] (knot 0 is 0).
    slots = np.zeros((n, 3), dtype=np.int32)
    values = np.zeros((n, 3))
    values[:, 0] = 1.0
    structures = {"building_scale": np.zeros((1, 1))}
    structures["building_scale"][0, 0] = 1.0
    ranks = {"building_scale": 1}
    n_local = 1
    if config.building_walk:
        k = model_module.n_knots(t)
        n_local = k  # level + (k - 1) free knots
        lo, frac = tr.knot, tr.knot_frac
        slots[:, 1] = lo  # knot j -> local index j (index 0 is the level)
        values[:, 1] = np.where(lo >= 1, 1 - frac, 0.0)
        slots[:, 2] = lo + 1
        values[:, 2] = frac
        level = np.zeros((k, k))
        level[0, 0] = 1.0
        walk = np.zeros((k, k))
        walk[1:, 1:] = _rw1_anchored(k - 1)
        structures = {"building_scale": level, "walk_scale": walk}
        ranks = {"building_scale": 1, "walk_scale": k - 1}
    prior_sd = {
        "sigma": config.noise_scale_sd,
        "unit_scale": config.unit_scale_sd,
        "building_scale": config.building_scale_sd,
        "trend_scale": config.trend_scale_sd,
        "season_scale": config.season_scale_sd,
        "walk_scale": config.walk_scale_sd,
    }
    return Design(
        a=jnp.asarray(a),
        y=jnp.asarray(tr.y, jnp.float64),
        unit=jnp.asarray(tr.unit),
        building=jnp.asarray(tr.building),
        unit_building=jnp.asarray(unit_building),
        slots=jnp.asarray(slots),
        slot_values=jnp.asarray(values),
        prior_fixed=jnp.asarray(fixed),
        local_structures={k: jnp.asarray(v) for k, v in structures.items()},
        local_ranks=ranks,
        trend=trend,
        season=season,
        n_features=f,
        n_units=len(prep.units),
        n_buildings=len(prep.buildings),
        n_local=n_local,
        walk=config.building_walk,
        prior_sd=prior_sd,
    )


def _update_scale(key, current, q, rank, prior_sd):
    """tau | x for x ~ N(0, tau^2 R^-1) with rank(R) = rank, half-normal prior."""
    k1, k2 = jax.random.split(key)
    proposal = jnp.sqrt((q / 2) / jax.random.gamma(k1, (rank - 1) / 2))
    log_accept = -(proposal**2 - current**2) / (2 * prior_sd**2)
    return jnp.where(jnp.log(jax.random.uniform(k2)) < log_accept, proposal, current)


def local_value(d: Design, theta_l, building, slots, values):
    return jnp.sum(theta_l[building[:, None], slots] * values, axis=1)


def gaussian_block(d: Design, lam, s, z_g, z_l, z_u):
    """Joint draw of (global, building blocks, units) given lam and scales `s`.

    With zero noise vectors it returns the conditional posterior mean.
    """
    J, K, L = d.n_units, d.n_buildings, d.n_local
    y, a, bld, slots, vals = d.y, d.a, d.building, d.slots, d.slot_values
    w = lam / s["sigma"] ** 2
    seg_u = lambda v: jax.ops.segment_sum(v, d.unit, J)  # noqa: E731
    seg_ub = lambda v: jax.ops.segment_sum(v, d.unit_building, K)  # noqa: E731
    sw = seg_u(w)
    c = 1.0 / (1.0 / s["unit_scale"] ** 2 + sw)  # unit posterior variance given rest
    h = seg_u(w * y)
    wa = w[:, None] * a
    g = seg_u(wa)  # (J, P) unit sums of weighted global rows
    gl = jnp.zeros((J, L))  # unit sums of weighted local rows
    for m in range(3):
        gl = gl.at[d.unit, slots[:, m]].add(w * vals[:, m])

    # Global precision / rhs with units integrated out.
    q = a.T @ wa - g.T @ (c[:, None] * g) + jnp.diag(d.prior_fixed)
    t = d.trend
    rw = jnp.asarray(_rw1_anchored(t.stop - t.start))
    q = q.at[t, t].add(rw / s["trend_scale"] ** 2)
    q = q.at[d.season, d.season].add(jnp.eye(12) / s["season_scale"] ** 2)
    r = wa.T @ y - g.T @ (c * h)

    # Building blocks, with units integrated out (units nest in buildings).
    q_ll = jnp.zeros((K, L, L))
    q_lg = jnp.zeros((K, L, a.shape[1]))
    r_l = jnp.zeros((K, L))
    for m1 in range(3):
        wv = w * vals[:, m1]
        for m2 in range(3):
            q_ll = q_ll.at[bld, slots[:, m1], slots[:, m2]].add(wv * vals[:, m2])
        q_lg = q_lg.at[bld, slots[:, m1]].add(wv[:, None] * a)
        r_l = r_l.at[bld, slots[:, m1]].add(wv * y)
    cgl = c[:, None] * gl
    q_ll = q_ll - jnp.stack([seg_ub(cgl[:, i : i + 1] * gl) for i in range(L)], axis=1)
    q_lg = q_lg - jnp.stack([seg_ub(cgl[:, i : i + 1] * g) for i in range(L)], axis=1)
    r_l = r_l - seg_ub(cgl * h[:, None])
    prior_l = sum(d.local_structures[n] / s[n] ** 2 for n in d.local_structures)
    q_ll = q_ll + prior_l[None]

    # Eliminate building blocks (batched Cholesky), then the global block.
    chol_l = jnp.linalg.cholesky(q_ll)
    v = solve_triangular(chol_l, q_lg, lower=True)  # (K, L, P)
    vr = solve_triangular(chol_l, r_l[..., None], lower=True)[..., 0]
    schur = q - jnp.einsum("klp,klq->pq", v, v)
    r_s = r - jnp.einsum("klp,kl->p", v, vr)
    chol = jnp.linalg.cholesky(schur)
    theta = solve_triangular(
        chol.T, solve_triangular(chol, r_s, lower=True) + z_g, lower=False
    )
    rhs = vr - jnp.einsum("klp,p->kl", v, theta) + z_l
    theta_l = solve_triangular(jnp.swapaxes(chol_l, 1, 2), rhs[..., None], lower=False)[
        ..., 0
    ]
    fixed = a @ theta + local_value(d, theta_l, bld, slots, vals)
    u = c * (h - seg_u(w * fixed)) + jnp.sqrt(c) * z_u
    return theta, theta_l, u, fixed


def site_values(d: Design, state):
    """Constrained NumPyro site values (as in model.build_model) from a state."""
    theta, theta_l = state["theta"], state["local"]
    f = d.n_features
    trend = jnp.concatenate([jnp.zeros(1), theta[d.trend]])
    out = {
        "alpha": theta[0],
        "beta": theta[1 : 1 + f],
        "trend_step": jnp.diff(trend),
        "season_raw": theta[d.season],
        "building": theta_l[:, 0],
        "unit": state["unit"],
        "nu": state["nu"],
        **{n: state[n] for n in d.scale_names},
    }
    if d.walk:
        knots = jnp.concatenate([jnp.zeros((d.n_buildings, 1)), theta_l[:, 1:]], axis=1)
        out["walk_step"] = jnp.diff(knots, axis=1)
    return out


def make_step(d: Design):
    n = d.y.shape[0]
    rank = {
        "sigma": n,
        "unit_scale": d.n_units,
        "trend_scale": d.trend.stop - d.trend.start,
        "season_scale": 12,
        **{k: r * d.n_buildings for k, r in d.local_ranks.items()},
    }
    rw = jnp.asarray(_rw1_anchored(d.trend.stop - d.trend.start))

    def step(key, state, noise_steps, sigma_step_sd, nu_step_sd):
        keys = jax.random.split(key, 12)
        s = {k: state[k] for k in d.scale_names}
        p = d.a.shape[1]
        theta, theta_l, u, fixed = gaussian_block(
            d,
            state["lam"],
            s,
            jax.random.normal(keys[0], (p,)),
            jax.random.normal(keys[1], (d.n_buildings, d.n_local)),
            jax.random.normal(keys[2], (d.n_units,)),
        )
        e = d.y - fixed - u[d.unit]

        # (sigma, nu) | e jointly, with lam integrated out (exact Student-t
        # likelihood), by random-walk Metropolis on (log sigma, log nu); then
        # lam | sigma, nu, e. Updating sigma given lam instead mixes slowly,
        # because sigma and all lam can scale up together.
        sigma_prior = d.prior_sd["sigma"]

        def log_target(z):
            sigma, nu = jnp.exp(z[0]), jnp.exp(z[1])
            return (
                jnp.sum(collect_module.student_t_logpdf(e, nu, sigma))
                - sigma**2 / (2 * sigma_prior**2)
                + jax.scipy.stats.gamma.logpdf(nu, 2.0, scale=10.0)
                + z[0]
                + z[1]
            )

        step_sd = jnp.asarray([sigma_step_sd, nu_step_sd])

        def noise_mh(carry, k):
            z, lt, acc = carry
            k1, k2 = jax.random.split(k)
            prop = z + step_sd * jax.random.normal(k1, (2,))
            lp = log_target(prop)
            ok = jnp.log(jax.random.uniform(k2)) < lp - lt
            return (jnp.where(ok, prop, z), jnp.where(ok, lp, lt), acc + ok), None

        z0 = jnp.log(jnp.stack([s["sigma"], state["nu"]]))
        (z, _, noise_acc), _ = jax.lax.scan(
            noise_mh, (z0, log_target(z0), 0.0), jax.random.split(keys[3], noise_steps)
        )
        sigma, nu = jnp.exp(z[0]), jnp.exp(z[1])
        lam = jax.random.gamma(keys[4], (nu + 1) / 2, (n,)) / (
            (nu + (e / sigma) ** 2) / 2
        )

        new = {"sigma": sigma}
        new["unit_scale"] = _update_scale(
            keys[6],
            s["unit_scale"],
            jnp.sum(u * u),
            rank["unit_scale"],
            d.prior_sd["unit_scale"],
        )
        tr = theta[d.trend]
        new["trend_scale"] = _update_scale(
            keys[8],
            s["trend_scale"],
            tr @ rw @ tr,
            rank["trend_scale"],
            d.prior_sd["trend_scale"],
        )
        se = theta[d.season]
        new["season_scale"] = _update_scale(
            keys[9],
            s["season_scale"],
            se @ se,
            rank["season_scale"],
            d.prior_sd["season_scale"],
        )
        for i, name in enumerate(d.local_structures):
            quad = jnp.einsum("kl,lm,km->", theta_l, d.local_structures[name], theta_l)
            new[name] = _update_scale(
                jax.random.fold_in(keys[7], i),
                s[name],
                quad,
                rank[name],
                d.prior_sd[name],
            )
        state = {
            "theta": theta,
            "local": theta_l,
            "unit": u,
            "lam": lam,
            "nu": nu,
            **new,
        }
        return state, {"noise_accept": noise_acc / noise_steps}

    return step


def init_states(d: Design, key, chains):
    """Overdispersed starting scales; latents are drawn in the first step."""
    start = {
        "sigma": 0.08,
        "unit_scale": 0.1,
        "building_scale": 0.3,
        "trend_scale": 0.02,
        "season_scale": 0.02,
        "walk_scale": 0.03,
    }
    names = d.scale_names
    k1, k2 = jax.random.split(key)
    jitter = jnp.exp(0.7 * jax.random.normal(k1, (chains, len(names) + 1)))
    state = {n: start[n] * jitter[:, i] for i, n in enumerate(names)}
    state["nu"] = 5.0 * jitter[:, -1]
    state["theta"] = jnp.zeros((chains, d.a.shape[1]))
    state["local"] = jnp.zeros((chains, d.n_buildings, d.n_local))
    state["unit"] = jnp.zeros((chains, d.n_units))
    state["lam"] = jnp.ones((chains, d.y.shape[0]))
    return state


def run(
    prep: model_module.Prepared,
    config: model_module.ModelConfig,
    settings: Settings,
    log=print,
):
    if not jax.config.jax_enable_x64:
        raise RuntimeError("The Gibbs sampler needs float64 (jax_enable_x64)")
    t0 = time.perf_counter()
    d = build_design(prep, config)
    step = make_step(d)
    step_fn = lambda k, st: step(
        k, st, settings.noise_steps, settings.sigma_step_sd, settings.nu_step_sd
    )  # noqa: E731
    key = jax.random.PRNGKey(settings.seed)
    k_init, k_warm, k_draw = jax.random.split(key, 3)
    states = init_states(d, k_init, settings.chains)
    setup_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()

    def warm_chain(state, k):
        state, _ = jax.lax.scan(
            lambda st, kk: step_fn(kk, st), state, jax.random.split(k, settings.warmup)
        )
        return state

    states = jax.jit(jax.vmap(warm_chain))(
        states, jax.random.split(k_warm, settings.chains)
    )
    jax.block_until_ready(states)
    warmup_seconds = time.perf_counter() - t0
    log(
        f"warmup {warmup_seconds:.1f}s "
        + " ".join(
            f"{n}={float(np.median(states[n])):.4f}" for n in (*d.scale_names, "nu")
        )
    )

    t0 = time.perf_counter()
    out = collect_module.collect(
        step_fn,
        lambda st: site_values(d, st),
        states,
        k_draw,
        prep,
        settings.draws,
        settings.keep_every,
        jnp.float64,
        settings.seed,
        settings.trace_groups,
    )
    sampling_seconds = time.perf_counter() - t0
    log(f"sampling {sampling_seconds:.1f}s")
    out["seconds"] = {
        "setup": setup_seconds,
        "warmup": warmup_seconds,
        "sampling": sampling_seconds,
    }
    out["dtype"] = "float64"
    out["sampler"] = "structured-gibbs"
    return out
