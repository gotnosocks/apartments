"""Each building's local effects integrated out of the Gibbs design, given the
global coefficients.

The gradient-based sampler in docs/model/gpu-inference-direction-2026-10-17.md
moves the global coefficients `g` and the scales with a library kernel, while
the row weights `lam` and the unit weights `kappa` stay fixed as Gibbs sites.
Given all of those, each building's rows follow a linear Gaussian model, and
this module evaluates its marginal in two folds:

1. Each unit's effect folds into its rows' noise (Sherman-Morrison), which
   comes down to segment sums over the unit's rows.
2. Each building's compact block (level, slopes and the walk knots its rows
   touch, `gibbs.compact_walk`) folds in next (Woodbury), with one small
   Cholesky factor per building.

`log_marginal` returns log p(y | g, scales, lam, kappa) with every constant
kept, `log_target` adds the prior of `g` and the scale priors on log
coordinates, and `draw_locals` draws the building blocks and the unit effects
from their Gaussian conditional after a kernel step. The design comes from
`gibbs.build_design` (compact, without unit drift or line effects), so the
buckets and chunks match the Gibbs sampler's.
"""

import jax
import jax.numpy as jnp
import numpy as np
from jax.scipy.linalg import solve_triangular

from rentfrontier import gibbs
from rentfrontier.gibbs import Design


def check_design(d: Design):
    """Raise unless `d` is a compact design the marginal covers."""
    if not d.buckets or d.unit_drift or d.n_lines:
        raise ValueError(
            "the marginal needs a compact design (building walk) without unit "
            "drift or line effects"
        )


def row_weights(d: Design, s, lam):
    """Each row's noise precision lam / sigma^2."""
    return lam / gibbs.sigma_rows(d, s) ** 2


def bucket_prior(d: Design, bk, s):
    """(K_b, width, width) prior precision of the bucket's compact blocks:
    the shared local structures, the walk over the touched knots, and 1 on
    unused slots."""
    n_fixed = d.knot_start
    shared = sum(
        d.local_structures[n] / s[n] ** 2
        for n in d.local_structures
        if n != "walk_scale"
    )
    if d.walk_ar:
        walk = jnp.pad(
            gibbs.ar_precision(bk.gap, bk.used, gibbs.walk_rho(d, s)),
            ((0, 0), (n_fixed, 0), (n_fixed, 0)),
        )
    else:
        walk = bk.walk
    return (
        shared[: bk.width, : bk.width][None]
        + walk / s["walk_scale"] ** 2
        + jax.vmap(jnp.diag)(bk.pad)
    )


def bucket_cells(bk, w, c, r):
    """The bucket's building cells with each unit's effect folded into the
    noise: q_ll = Z' A^-1 Z (K_b, width, width) and r_l = Z' A^-1 r
    (K_b, width), where A = W^-1 + U P_u^-1 U' and c holds each unit's
    1 / (P_u + U'WU). The rows enter one chunk of buildings at a time, as in
    `gibbs._compact_parts`."""
    kb, width, n_slots = bk.buildings.shape[0], bk.width, bk.slots.shape[1]
    n_b, n_u = bk.chunk_bld.shape[1], bk.chunk_units.shape[1]

    def chunk(carry, ch):
        q_ll, r_l = carry
        pos, unit = ch["chunk_pos"], ch["chunk_unit"]
        rows = bk.rows[pos]
        wr = w[rows] * ch["chunk_mask"]
        slots, vals = bk.slots[pos], bk.values[pos]
        cu = c[ch["chunk_units"]]
        n_r = pos.shape[0]
        z = jnp.zeros((n_r, width)).at[jnp.arange(n_r)[:, None], slots].add(vals)
        uz = jnp.zeros((n_u, width))
        for m in range(n_slots):
            uz = uz.at[unit, slots[:, m]].add(wr * vals[:, m])
        adj = z - (cu[:, None] * uz)[unit]
        c_ll = jnp.zeros((n_b * width, width))
        for m in range(n_slots):
            cell = ch["chunk_row_bld"] * width + slots[:, m]
            wv = (wr * vals[:, m])[:, None]
            c_ll = c_ll + jax.ops.segment_sum(wv * adj, cell, n_b * width)
        c_r = jax.ops.segment_sum(
            (wr * r[rows])[:, None] * adj, ch["chunk_row_bld"], n_b
        )
        # Padded buildings (index kb) fall outside and drop.
        bld = ch["chunk_bld"]
        q_ll = q_ll.at[bld].set(c_ll.reshape(n_b, width, width), mode="drop")
        r_l = r_l.at[bld].set(c_r, mode="drop")
        return (q_ll, r_l), None

    chunks = {
        k: getattr(bk, k)
        for k in (
            "chunk_bld",
            "chunk_pos",
            "chunk_mask",
            "chunk_row_bld",
            "chunk_unit",
            "chunk_units",
        )
    }
    init = (jnp.zeros((kb, width, width)), jnp.zeros((kb, width)))
    (q_ll, r_l), _ = jax.lax.scan(chunk, init, chunks)
    return 0.5 * (q_ll + jnp.swapaxes(q_ll, 1, 2)), r_l


def _folds(d: Design, g, s, lam, kappa):
    """The unit fold and, per bucket, the factor of the building posterior
    precision, the whitened right side and the prior precision."""
    w = row_weights(d, s, lam)
    r = d.y - gibbs.global_value(d, g)
    seg_u = lambda v: jax.ops.segment_sum(v, d.unit, d.n_units)
    prec_u = kappa / s["unit_scale"] ** 2
    c = 1.0 / (prec_u + seg_u(w))
    h = seg_u(w * r)
    blocks = []
    for bk in d.buckets:
        q_ll, r_l = bucket_cells(bk, w, c, r)
        prior = bucket_prior(d, bk, s)
        chol = jnp.linalg.cholesky(q_ll + prior)
        vr = solve_triangular(chol, r_l[..., None], lower=True)[..., 0]
        blocks.append((bk, chol, vr, prior))
    return w, r, prec_u, c, h, blocks


def _logdet(chol):
    return 2 * jnp.sum(jnp.log(jnp.diagonal(chol, axis1=-2, axis2=-1)))


def log_marginal(d: Design, g, s, lam, kappa):
    """log N(y; a g, W^-1 + U P_u^-1 U' + Z P_l^-1 Z'), with W = lam / sigma^2
    and P_u = kappa / unit_scale^2, by the two folds:

        log|C|   = -log|W| + log|P_u + U'WU| - log|P_u|
                   + sum over buildings of log|P_b + Z_b'A^-1 Z_b| - log|P_b|
        r'C^-1 r = r'Wr - h'(P_u + U'WU)^-1 h - sum over buildings of r_b'(P_b + Z_b'A^-1 Z_b)^-1 r_b

    with r = y - a g and h = U'W r."""
    check_design(d)
    w, r, prec_u, c, h, blocks = _folds(d, g, s, lam, kappa)
    quad = jnp.sum(w * r * r) - jnp.sum(c * h * h)
    logdet = -jnp.sum(jnp.log(w)) - jnp.sum(jnp.log(c)) - jnp.sum(jnp.log(prec_u))
    for _, chol, vr, prior in blocks:
        quad = quad - jnp.sum(vr * vr)
        logdet = logdet + _logdet(chol) - _logdet(jnp.linalg.cholesky(prior))
    n = d.y.shape[0]
    return -0.5 * (n * np.log(2 * np.pi) + logdet + quad)


def global_precision(d: Design, s):
    """(P, P) prior precision of the global coefficients."""
    q = jnp.diag(d.prior_fixed)
    for name, (sl, r) in d.global_blocks.items():
        q = q.at[sl, sl].add(r / s[name] ** 2)
    return q


def log_global_prior(d: Design, g, s):
    """log N(g; 0, global_precision^-1)."""
    chol = jnp.linalg.cholesky(global_precision(d, s))
    return 0.5 * (
        _logdet(chol) - jnp.sum((chol.T @ g) ** 2) - g.shape[0] * np.log(2 * np.pi)
    )


def log_target(d: Design, g, log_s, lam, kappa):
    """log p(y, g, log scales | lam, kappa) up to a constant: the marginal,
    the prior of g, and each scale's prior on log coordinates
    (`gibbs.scale_log_prior`, Jacobian included). `log_s` maps each of
    `d.scale_names` to its log."""
    s = {k: jnp.exp(v) for k, v in log_s.items()}
    prior_s = sum(gibbs.scale_log_prior(k, s[k], d.prior_sd[k]) for k in d.scale_names)
    return log_marginal(d, g, s, lam, kappa) + log_global_prior(d, g, s) + prior_s


def draw_locals(d: Design, g, s, lam, kappa, z_l, z_u, z_f=None):
    """Draw the local block theta_l (K, L, full layout) and the unit effects
    u (J,) from their conditional given g, the scales and the weights, from
    standard normals z_l (K, L), z_u (J,) and z_f (K, `d.n_fill`; None: the
    untouched knots at their conditional mean). The buildings come first,
    with the units integrated out, then the units given the buildings."""
    check_design(d)
    w, r, prec_u, c, h, blocks = _folds(d, g, s, lam, kappa)
    n_fixed, k = d.knot_start, d.n_fill
    fixed_l = jnp.zeros((d.n_buildings, n_fixed))
    x = jnp.zeros((d.n_buildings, k + 1))  # column k takes the unused slots
    for bk, chol, vr, _ in blocks:
        rhs = vr + z_l[bk.buildings, : bk.width]
        tc = solve_triangular(jnp.swapaxes(chol, 1, 2), rhs[..., None], lower=False)[
            ..., 0
        ]
        fixed_l = fixed_l.at[bk.buildings].set(tc[:, :n_fixed])
        x = x.at[bk.buildings[:, None], bk.knot].set(tc[:, n_fixed:])
    if d.walk_ar:
        rho = gibbs.walk_rho(d, s)
        walk = gibbs.fill_ar(d, x[:, :k], rho, s["walk_scale"], z_f)
        theta_l = jnp.concatenate([fixed_l, walk], axis=1)
    else:
        walk = gibbs.fill_walk(d, x[:, :k], s["walk_scale"], z_f)
        theta_l = jnp.concatenate([fixed_l, walk[:, 1:]], axis=1)
    local = gibbs.local_value(theta_l, d.building, d.slots, d.slot_values)
    seg_u = lambda v: jax.ops.segment_sum(v, d.unit, d.n_units)
    u = c * (h - seg_u(w * local)) + jnp.sqrt(c) * z_u
    return theta_l, u
