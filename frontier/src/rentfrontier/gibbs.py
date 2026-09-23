"""Structured blocked Gibbs sampler for the model in `model.build_model`.

Same posterior as the NumPyro model (same priors, Student-t likelihood).
The Student-t is written as a scale mixture: eps_i | lam_i ~ N(0, sigma^2 /
lam_i), lam_i ~ Gamma(nu/2, nu/2). One iteration:

1. All Gaussian latents jointly, given lam and the scales:
   - global block: intercept, feature coefficients, month trend, season and
     (optionally) bedroom-group market curves;
   - one local block per building: level, optional bedroom slope and optional
     walk knots;
   - one effect per unit.
   Unit effects are integrated out analytically (each row has one unit, so
   their block is diagonal). Building blocks are eliminated by batched
   Cholesky factors (units nest in buildings), leaving a dense global
   system. The draw is exact: no tuning, no funnel.
2. (sigma, nu) jointly by random-walk Metropolis with lam integrated out,
   then lam | sigma, nu (partially collapsed Gibbs, valid in this order).
3. Every group scale: independence Metropolis whose proposal is the exact
   conditional under a flat prior on the scale, so the accept ratio only
   carries the half-normal prior (acceptance ~1).
4. With a building walk, a rescaling move (walk_scale, walk) -> (c *
   walk_scale, c * walk), which moves along the scale/latent ridge that
   plain Gibbs crosses slowly.
5. Collapsed scale update (after the first half of warmup): a joint
   random-walk Metropolis step on all group log-scales whose target is the
   marginal posterior with every Gaussian latent integrated out (computed
   from the same block factorisation), followed by the latent draw from the
   kept factorisation. This removes the scale/latent coupling entirely.

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
    rescale_steps: int = 5  # (walk_scale, walk) rescaling moves per iteration
    rescale_step_sd: float = 0.01  # on log c
    trace_groups: int = 32
    # Collapsed Metropolis update of all group scales (latents integrated
    # out); proposal sd = collapse_scale * sd(log scale) / sqrt(#scales),
    # sized from the first half of warmup.
    collapse: bool = True
    collapse_scale: float = 2.38
    chain_batch: int = 0  # vectorise this many chains at a time (0 = all)
    # Extra one-dimensional collapsed updates for these scales (if present).
    solo_scales: tuple = ("walk_scale",)

    def to_dict(self):
        return asdict(self)


@dataclass
class Design:
    a: jnp.ndarray  # (N, P) global design
    y: jnp.ndarray
    unit: jnp.ndarray
    building: jnp.ndarray
    unit_building: jnp.ndarray
    slots: jnp.ndarray  # (N, S) local slots each row touches in its building
    slot_values: jnp.ndarray  # (N, S)
    prior_fixed: jnp.ndarray  # (P,) diagonal of the fixed prior precision
    global_blocks: dict  # scale name -> (slice, (n, n) structure)
    global_ranks: dict
    local_structures: dict  # scale name -> (L, L) structure within a building block
    local_ranks: dict  # scale name -> rank per building
    trend: slice
    season: slice
    bedroom_time: slice | None
    trend_basis: jnp.ndarray
    bedroom_time_basis: jnp.ndarray
    slope_index: int | None  # local index of the bedroom slope
    knot_start: int | None  # local index of walk knot 1 (knot 0 is fixed at 0)
    n_features: int
    n_months: int
    n_units: int
    n_buildings: int
    n_local: int
    prior_sd: dict

    @property
    def scale_names(self):
        return ("sigma", "unit_scale", *self.global_blocks, *self.local_structures)


def _rw1_anchored(n):
    d = np.diff(np.eye(n + 1), axis=0)[:, 1:]  # steps from a fixed 0
    return d.T @ d


def build_design(
    prep: model_module.Prepared, config: model_module.ModelConfig
) -> Design:
    tr = prep.train
    n, f = tr.x.shape
    t = len(prep.periods)
    groups = model_module.TIME_GROUPS

    # ----------------------------------------------------------- global block
    # Market trend and bedroom-group curves: random walks over knots every
    # trend_knot_months / bedroom_time_knot_months, linearly interpolated.
    trend_basis = model_module.knot_basis(t, config.trend_knot_months)
    bed_basis = model_module.knot_basis(t, config.bedroom_time_knot_months)
    nt, nb = trend_basis.shape[1], bed_basis.shape[1]
    trend = slice(1 + f, 1 + f + nt)
    season = slice(trend.stop, trend.stop + 12)
    bedroom_time = (
        slice(season.stop, season.stop + len(groups) * nb)
        if config.bedroom_time
        else None
    )
    p = (bedroom_time or season).stop
    a = np.zeros((n, p))
    a[:, 0] = 1.0
    a[:, 1 : 1 + f] = tr.x
    a[:, trend] = trend_basis[tr.month]
    # Season enters as season_raw - mean(season_raw), as in the NumPyro model.
    a[:, season] = -1.0 / 12
    a[np.arange(n), season.start + tr.calendar] += 1.0
    blocks = {
        "trend_scale": (trend, _rw1_anchored(nt)),
        "season_scale": (season, np.eye(12)),
    }
    if bedroom_time is not None:
        for gi, g in enumerate(groups):
            rows = np.flatnonzero(tr.bed_group == g)
            cols = slice(
                bedroom_time.start + gi * nb, bedroom_time.start + (gi + 1) * nb
            )
            a[rows, cols] = bed_basis[tr.month[rows]]
        blocks["bedroom_time_scale"] = (
            bedroom_time,
            np.kron(np.eye(len(groups)), _rw1_anchored(nb)),
        )
    fixed = np.zeros(p)
    fixed[0] = 1.0
    fixed[1 : 1 + f] = 1.0 / (config.beta_sd * prep.features.prior_scale) ** 2
    unit_building = np.zeros(len(prep.units), dtype=np.int32)
    unit_building[tr.unit] = tr.building

    # ------------------------------------------------------------ local block
    # Per building: [level, (bedroom slope), (walk knots 1..k-1)].
    columns = [(np.zeros(n, np.int32), np.ones(n))]
    structures = {"building_scale": [0]}
    slope_index = knot_start = None
    n_local = 1
    if config.bedroom_slope:
        slope_index = n_local
        columns.append(
            (np.full(n, slope_index, np.int32), tr.beds_centered.astype(float))
        )
        structures["bedroom_slope_scale"] = [slope_index]
        n_local += 1
    if config.building_walk:
        k = model_module.n_knots(t)
        knot_start = n_local
        lo, frac = tr.knot, tr.knot_frac
        # Knot j >= 1 sits at local index knot_start + j - 1; knot 0 is fixed at 0,
        # so a row before knot 1 puts zero weight on its lower slot.
        columns.append(
            (
                knot_start + np.maximum(lo - 1, 0).astype(np.int32),
                np.where(lo >= 1, 1 - frac, 0.0),
            )
        )
        columns.append((knot_start + lo.astype(np.int32), frac))
        n_local += k - 1
    slots = np.stack([c[0] for c in columns], axis=1).astype(np.int32)
    values = np.stack([c[1] for c in columns], axis=1)

    local_structures, local_ranks = {}, {}
    for name, idx in structures.items():
        m = np.zeros((n_local, n_local))
        m[idx, idx] = 1.0
        local_structures[name] = m
        local_ranks[name] = 1
    if config.building_walk:
        m = np.zeros((n_local, n_local))
        m[knot_start:, knot_start:] = _rw1_anchored(n_local - knot_start)
        local_structures["walk_scale"] = m
        local_ranks["walk_scale"] = n_local - knot_start

    prior_sd = {
        "sigma": config.noise_scale_sd,
        "unit_scale": config.unit_scale_sd,
        "building_scale": config.building_scale_sd,
        "trend_scale": config.trend_scale_sd,
        "season_scale": config.season_scale_sd,
        "walk_scale": config.walk_scale_sd,
        "bedroom_time_scale": config.bedroom_time_scale_sd,
        "bedroom_slope_scale": config.bedroom_slope_scale_sd,
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
        global_blocks={k: (sl, jnp.asarray(r)) for k, (sl, r) in blocks.items()},
        global_ranks={k: r.shape[0] for k, (sl, r) in blocks.items()},
        local_structures={k: jnp.asarray(v) for k, v in local_structures.items()},
        local_ranks=local_ranks,
        trend=trend,
        season=season,
        bedroom_time=bedroom_time,
        trend_basis=jnp.asarray(trend_basis),
        bedroom_time_basis=jnp.asarray(bed_basis),
        slope_index=slope_index,
        knot_start=knot_start,
        n_features=f,
        n_months=t,
        n_units=len(prep.units),
        n_buildings=len(prep.buildings),
        n_local=n_local,
        prior_sd=prior_sd,
    )


def _update_scale(key, current, q, rank, prior_sd):
    """tau | x for x ~ N(0, tau^2 R^-1) with rank(R) = rank, half-normal prior."""
    k1, k2 = jax.random.split(key)
    proposal = jnp.sqrt((q / 2) / jax.random.gamma(k1, (rank - 1) / 2))
    log_accept = -(proposal**2 - current**2) / (2 * prior_sd**2)
    return jnp.where(jnp.log(jax.random.uniform(k2)) < log_accept, proposal, current)


def local_value(theta_l, building, slots, values):
    return jnp.sum(theta_l[building[:, None], slots] * values, axis=1)


def gaussian_block(d: Design, lam, s, z_g, z_l, z_u):
    """Joint draw of (global, building blocks, units) given lam and scales `s`.

    With zero noise vectors it returns the conditional posterior mean.
    """
    J, K, L = d.n_units, d.n_buildings, d.n_local
    y, a, bld, slots, vals = d.y, d.a, d.building, d.slots, d.slot_values
    n_slots = slots.shape[1]
    w = lam / s["sigma"] ** 2
    seg_u = lambda v: jax.ops.segment_sum(v, d.unit, J)  # noqa: E731
    sw = seg_u(w)
    c = 1.0 / (1.0 / s["unit_scale"] ** 2 + sw)  # unit posterior variance given rest
    h = seg_u(w * y)
    wa = w[:, None] * a
    g = seg_u(wa)  # (J, P) unit sums of weighted global rows
    gl = jnp.zeros((J, L))  # unit sums of weighted local rows
    for m in range(n_slots):
        gl = gl.at[d.unit, slots[:, m]].add(w * vals[:, m])

    # Global precision / rhs with units integrated out.
    q = a.T @ wa - g.T @ (c[:, None] * g) + jnp.diag(d.prior_fixed)
    for name, (sl, r) in d.global_blocks.items():
        q = q.at[sl, sl].add(r / s[name] ** 2)
    rhs_g = wa.T @ y - g.T @ (c * h)

    # Building blocks, with units integrated out (units nest in buildings).
    # With a~_i = a_L,i - c_j gl_j (row i's local design minus its unit's
    # correction), sum_i w_i a~_i b_i^T equals
    # sum_i w_i a_L,i b_i^T - sum_j c_j gl_j (sum_{i in j} w_i b_i)^T,
    # so each building term is one segment sum over rows. Accumulating one
    # local index at a time keeps temporaries at (rows x columns).
    n = a.shape[0]
    a_l = jnp.zeros((n, L)).at[jnp.arange(n)[:, None], slots].add(vals)
    wadj = w[:, None] * (a_l - (c[:, None] * gl)[d.unit])
    seg_b = lambda v: jax.ops.segment_sum(v, bld, K)  # noqa: E731

    def per_local(i):
        col = jax.lax.dynamic_index_in_dim(wadj, i, axis=1, keepdims=True)
        return seg_b(col * a_l), seg_b(col * a)

    q_ll, q_lg = jax.lax.map(per_local, jnp.arange(L))
    q_ll = jnp.swapaxes(q_ll, 0, 1)  # (K, L, L)
    q_lg = jnp.swapaxes(q_lg, 0, 1)  # (K, L, P)
    q_ll = 0.5 * (q_ll + jnp.swapaxes(q_ll, 1, 2))
    r_l = seg_b(wadj * y[:, None])
    prior_l = sum(d.local_structures[n] / s[n] ** 2 for n in d.local_structures)
    q_ll = q_ll + prior_l[None]

    # Eliminate building blocks (batched Cholesky), then the global block.
    chol_l = jnp.linalg.cholesky(q_ll)
    v = solve_triangular(chol_l, q_lg, lower=True)  # (K, L, P)
    vr = solve_triangular(chol_l, r_l[..., None], lower=True)[..., 0]
    schur = q - jnp.einsum("klp,klq->pq", v, v)
    r_s = rhs_g - jnp.einsum("klp,kl->p", v, vr)
    chol = jnp.linalg.cholesky(schur)
    white = solve_triangular(chol, r_s, lower=True)
    theta = solve_triangular(chol.T, white + z_g, lower=False)
    rhs = vr - jnp.einsum("klp,p->kl", v, theta) + z_l
    theta_l = solve_triangular(jnp.swapaxes(chol_l, 1, 2), rhs[..., None], lower=False)[
        ..., 0
    ]
    fixed = a @ theta + local_value(theta_l, bld, slots, vals)
    u = c * (h - seg_u(w * fixed)) + jnp.sqrt(c) * z_u

    # Log marginal likelihood of y given lam and the scales, with every
    # Gaussian latent integrated out, up to terms that do not depend on the
    # group scales:  1/2 b'Q^-1 b - 1/2 log|Q_post| + 1/2 log|Q_prior|.
    # The block elimination order (units, buildings, global) splits both the
    # quadratic form and the determinant into per-level pieces.
    quad = jnp.sum(c * h * h) + jnp.sum(vr * vr) + jnp.sum(white * white)
    logdet_post = (
        -jnp.sum(jnp.log(c))
        + 2 * jnp.sum(jnp.log(jnp.diagonal(chol_l, axis1=1, axis2=2)))
        + 2 * jnp.sum(jnp.log(jnp.diagonal(chol)))
    )
    logdet_prior = -2 * J * jnp.log(s["unit_scale"])
    for name, rank in d.global_ranks.items():
        logdet_prior = logdet_prior - 2 * rank * jnp.log(s[name])
    for name, rank in d.local_ranks.items():
        logdet_prior = logdet_prior - 2 * K * rank * jnp.log(s[name])
    # Terms that depend on sigma through W = lam / sigma^2.
    logdet_w = jnp.sum(jnp.log(w))
    logml = 0.5 * (quad - logdet_post + logdet_prior + logdet_w - jnp.sum(w * y * y))
    return theta, theta_l, u, fixed, logml


def site_values(d: Design, state):
    """Constrained NumPyro site values (as in model.build_model) from a state."""
    theta, theta_l = state["theta"], state["local"]
    f = d.n_features

    def steps(curve):  # anchored walk values -> steps from 0
        return jnp.diff(
            jnp.concatenate([jnp.zeros(curve.shape[:-1] + (1,)), curve], axis=-1),
            axis=-1,
        )

    out = {
        "alpha": theta[0],
        "beta": theta[1 : 1 + f],
        "trend_step": steps(theta[d.trend]),
        "trend_basis": d.trend_basis,
        "season_raw": theta[d.season],
        "building": theta_l[:, 0],
        "unit": state["unit"],
        "nu": state["nu"],
        **{n: state[n] for n in d.scale_names},
    }
    if d.bedroom_time is not None:
        out["bedroom_time_step"] = steps(
            theta[d.bedroom_time].reshape(
                len(model_module.TIME_GROUPS), d.bedroom_time_basis.shape[1]
            )
        )
        out["bedroom_time_basis"] = d.bedroom_time_basis

    if d.slope_index is not None:
        out["bedroom_slope"] = theta_l[:, d.slope_index]
    if d.knot_start is not None:
        out["walk_step"] = steps(theta_l[:, d.knot_start :])
    return out


def make_step(d: Design):
    n = d.y.shape[0]
    rank = {
        "sigma": n,
        "unit_scale": d.n_units,
        **d.global_ranks,
        **{k: r * d.n_buildings for k, r in d.local_ranks.items()},
    }

    hier = list(d.scale_names)  # collapsed update covers sigma and every group scale

    def step(key, state, cfg, prop_sd=None, solo_sd=None):
        """One iteration. `cfg` holds the step sizes; with `prop_sd` (one
        proposal sd per hierarchical log-scale) the scales are first updated
        by a collapsed Metropolis step that integrates out every latent."""
        noise_steps, sigma_step_sd, nu_step_sd, rescale_steps, rescale_step_sd = cfg
        keys = jax.random.split(key, 12)
        s = {k: state[k] for k in d.scale_names}
        z = (
            jax.random.normal(keys[0], (d.a.shape[1],)),
            jax.random.normal(keys[1], (d.n_buildings, d.n_local)),
            jax.random.normal(keys[2], (d.n_units,)),
        )
        out = gaussian_block(d, state["lam"], s, *z)
        info = {}
        if prop_sd is not None:
            # Collapsed scale update: p(scales | lam, sigma, y) with all
            # Gaussian latents integrated out, random-walk on log scales. The
            # latents are then drawn from whichever factorisation is kept.
            k1, k2 = jax.random.split(keys[11])
            step_ = prop_sd * jax.random.normal(k1, (len(hier),))
            s_new = dict(s)
            for i, name in enumerate(hier):
                s_new[name] = s[name] * jnp.exp(step_[i])
            out_new = gaussian_block(d, state["lam"], s_new, *z)

            def log_prior(sc):
                return sum(
                    -(sc[k] ** 2) / (2 * d.prior_sd[k] ** 2) + jnp.log(sc[k])
                    for k in hier
                )

            log_ratio = out_new[-1] - out[-1] + log_prior(s_new) - log_prior(s)
            ok = jnp.log(jax.random.uniform(k2)) < log_ratio
            out = jax.tree.map(lambda a, b: jnp.where(ok, b, a), out, out_new)
            s = {k: jnp.where(ok, s_new[k], s[k]) for k in s}
            info["collapsed_accept"] = ok.astype(jnp.float64)
            # One-dimensional collapsed updates for the slowest scales, each
            # with its own proposal size (a joint step must use the smallest).
            for i, (name, sd_i) in enumerate((solo_sd or {}).items()):
                k1, k2 = jax.random.split(jax.random.fold_in(keys[11], 100 + i))
                s_new = dict(s)
                s_new[name] = s[name] * jnp.exp(sd_i * jax.random.normal(k1))
                out_new = gaussian_block(d, state["lam"], s_new, *z)
                log_ratio = (
                    out_new[-1]
                    - out[-1]
                    - (s_new[name] ** 2 - s[name] ** 2) / (2 * d.prior_sd[name] ** 2)
                    + jnp.log(s_new[name] / s[name])
                )
                ok = jnp.log(jax.random.uniform(k2)) < log_ratio
                out = jax.tree.map(lambda a, b: jnp.where(ok, b, a), out, out_new)
                s = {k: jnp.where(ok, s_new[k], s[k]) for k in s}
                info[f"solo_accept_{name}"] = ok.astype(jnp.float64)
        theta, theta_l, u, fixed, _ = out
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
            noise_mh,
            (z0, log_target(z0), jnp.zeros(())),
            jax.random.split(keys[3], noise_steps),
        )
        sigma, nu = jnp.exp(z[0]), jnp.exp(z[1])
        lam = jax.random.gamma(keys[4], (nu + 1) / 2, (n,)) / (
            (nu + (e / sigma) ** 2) / 2
        )

        new = {"sigma": sigma}
        new["unit_scale"] = _update_scale(
            keys[5],
            s["unit_scale"],
            jnp.sum(u * u),
            rank["unit_scale"],
            d.prior_sd["unit_scale"],
        )
        for i, (name, (sl, r)) in enumerate(d.global_blocks.items()):
            x = theta[sl]
            new[name] = _update_scale(
                jax.random.fold_in(keys[6], i),
                s[name],
                x @ r @ x,
                rank[name],
                d.prior_sd[name],
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

        info["noise_accept"] = noise_acc / noise_steps
        if d.knot_start is not None:
            # Rescaling move on (walk_scale, walk knots): (tau, W) -> (c tau, c W).
            # Given the knots, tau is pinned down tightly, and vice versa, so
            # plain Gibbs moves along this ridge slowly. For a symmetric step
            # on log c the acceptance ratio is
            #   lik(cW) / lik(W) * prior(c tau) / prior(tau) * c,
            # with the Gaussian likelihood given lam, sigma and all other latents.
            wts = lam / sigma**2
            walk_only = (
                jnp.zeros_like(theta_l)
                .at[:, d.knot_start :]
                .set(theta_l[:, d.knot_start :])
            )
            contrib = local_value(walk_only, d.building, d.slots, d.slot_values)

            def rescale(carry, k):
                c_tot, tau, acc = carry
                k1, k2 = jax.random.split(k)
                log_c = rescale_step_sd * jax.random.normal(k1)
                c = jnp.exp(log_c)
                r_now = e - (c_tot - 1.0) * contrib
                r_new = e - (c_tot * c - 1.0) * contrib
                log_ratio = (
                    -0.5 * jnp.sum(wts * (r_new**2 - r_now**2))
                    - ((c * tau) ** 2 - tau**2) / (2 * d.prior_sd["walk_scale"] ** 2)
                    + log_c
                )
                ok = jnp.log(jax.random.uniform(k2)) < log_ratio
                return (
                    jnp.where(ok, c_tot * c, c_tot),
                    jnp.where(ok, c * tau, tau),
                    acc + ok,
                ), None

            (c_tot, tau, acc), _ = jax.lax.scan(
                rescale,
                (jnp.ones(()), new["walk_scale"], jnp.zeros(())),
                jax.random.split(keys[10], rescale_steps),
            )
            new["walk_scale"] = tau
            theta_l = theta_l.at[:, d.knot_start :].multiply(c_tot)
            info["rescale_accept"] = acc / rescale_steps
        state = {
            "theta": theta,
            "local": theta_l,
            "unit": u,
            "lam": lam,
            "nu": nu,
            **new,
        }
        return state, info

    return step


START = {
    "sigma": 0.08,
    "unit_scale": 0.1,
    "building_scale": 0.3,
    "trend_scale": 0.02,
    "season_scale": 0.02,
    "walk_scale": 0.03,
    "bedroom_time_scale": 0.01,
    "bedroom_slope_scale": 0.05,
}


def init_states(d: Design, key, chains):
    """Overdispersed starting scales; latents are drawn in the first step."""
    names = d.scale_names
    k1, _ = jax.random.split(key)
    jitter = jnp.exp(0.7 * jax.random.normal(k1, (chains, len(names) + 1)))
    state = {n: START[n] * jitter[:, i] for i, n in enumerate(names)}
    state["nu"] = 5.0 * jitter[:, -1]
    state["theta"] = jnp.zeros((chains, d.a.shape[1]))
    state["local"] = jnp.zeros((chains, d.n_buildings, d.n_local))
    state["unit"] = jnp.zeros((chains, d.n_units))
    state["lam"] = jnp.ones((chains, d.y.shape[0]))
    return state


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
    cfg = (
        settings.noise_steps,
        settings.sigma_step_sd,
        settings.nu_step_sd,
        settings.rescale_steps,
        settings.rescale_step_sd,
    )
    hier = list(d.scale_names)
    key = jax.random.PRNGKey(settings.seed)
    k_init, k_warm, k_warm2, k_draw = jax.random.split(key, 4)
    states = init_states(d, k_init, settings.chains)
    setup_seconds = time.perf_counter() - t0

    # Warmup phase 1: plain Gibbs, recording the log-scales to size the
    # collapsed proposal. Phase 2 (and all draws): collapsed scale update.
    t0 = time.perf_counter()
    n1 = settings.warmup // 2 if settings.collapse else settings.warmup

    def warm1(state, k):
        def body(st, kk):
            st, _ = step(kk, st, cfg)
            return st, jnp.log(jnp.stack([st[n] for n in (*hier, "nu")]))

        return jax.lax.scan(body, state, jax.random.split(k, n1))

    states, log_scales = jax.jit(batched(warm1, settings.chains, settings.chain_batch))(
        states, jax.random.split(k_warm, settings.chains)
    )
    prop_sd = solo_sd = None
    if settings.collapse:
        tail = np.asarray(log_scales)[:, n1 // 2 :]  # (chains, draws, scales + nu)
        # Within-chain spread: robust to chains that have not met yet, which
        # would inflate a pooled estimate during warmup.
        sd = np.sqrt(tail.var(axis=1).mean(axis=0))
        prop_sd = jnp.asarray(settings.collapse_scale * sd[:-1] / np.sqrt(len(hier)))
        solo_sd = {
            n: float(2.38 * sd[hier.index(n)])
            for n in settings.solo_scales
            if n in hier
        }
        # Size the (log sigma, log nu) random-walk steps from warmup too.
        cfg = (
            settings.noise_steps,
            float(2.38 / np.sqrt(2) * sd[hier.index("sigma")]),
            float(2.38 / np.sqrt(2) * sd[-1]),
            settings.rescale_steps,
            settings.rescale_step_sd,
        )

        def warm2(state, k):
            state, _ = jax.lax.scan(
                lambda st, kk: (step(kk, st, cfg, prop_sd, solo_sd)[0], None),
                state,
                jax.random.split(k, settings.warmup - n1),
            )
            return state

        states = jax.jit(batched(warm2, settings.chains, settings.chain_batch))(
            states, jax.random.split(k_warm2, settings.chains)
        )
    jax.block_until_ready(states)
    warmup_seconds = time.perf_counter() - t0
    log(
        f"warmup {warmup_seconds:.1f}s "
        + " ".join(
            f"{n}={float(np.median(states[n])):.4f}" for n in (*d.scale_names, "nu")
        )
        + (
            f" collapsed proposal sd {dict(zip(hier, np.round(np.asarray(prop_sd), 4)))}"
            if prop_sd is not None
            else ""
        )
    )

    t0 = time.perf_counter()
    out = collect_module.collect(
        lambda k, st: step(k, st, cfg, prop_sd, solo_sd),
        lambda st: site_values(d, st),
        states,
        k_draw,
        prep,
        settings.draws,
        settings.keep_every,
        jnp.float64,
        settings.seed,
        settings.trace_groups,
        vmap=lambda fn: batched(fn, settings.chains, settings.chain_batch),
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
    out["collapsed_proposal_sd"] = (
        None if prop_sd is None else dict(zip(hier, np.asarray(prop_sd).tolist()))
    )
    out["noise_step_sd"] = {"sigma": cfg[1], "nu": cfg[2]}
    out["solo_proposal_sd"] = solo_sd
    return out
