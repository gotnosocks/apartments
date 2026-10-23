"""Building zones with the unit's floor on as-of features from the corrected build, with a
random effect for each unit.

The model is `rentfrontier.building_zones_floor_asof2` with one more term in each row's mean:

    y_i ~ StudentT(nu, x_i beta + eta_site(i) + v_unit(i) + L(t_i), sigma_group(i))
    v_k ~ Normal(0, su^2),  su ~ HalfNormal(UNIT_SD_PRIOR)

A unit is a pair of the frame's building and `unit_id`, so every unit sits inside a building.
On the corrected build's data each `unit_id` already lies in a single building. I number the
units with at least MIN_UNIT_ROWS training rows, in sorted order of their keys. Every other
row carries -1 and gets no effect. With MIN_UNIT_ROWS = 1 those are the rows with no
`unit_id` and the held-out ads of units with no training row.
With MIN_UNIT_ROWS = 1 a unit with a single training row gets an effect too. Its data hardly
separates the effect from that row's noise, so its posterior stays close to the prior, but the
model is then the same for every unit, and a held-out ad of a unit that was listed once before
gets that listing's shrunken residual. On the latest split of all data there are about 935k
units, and the effects cost a few MB per chain, so I keep them all.

I sample the model with the blocked Gibbs sweep of `rentfrontier.building_zones_gibbs`,
changed in four places:

1. The global block theta is drawn as there, from y - v in place of y, with the building
   levels integrated out and v at its last draw.
2. The zone spreads b_z and the building levels eta are drawn with the unit effects
   integrated out as well. With c_i = lam_i / sigma_g^2 as the row weight, and per unit
   C_k = sum c_i and R_k = sum c_i (y_i - m_i), where m_i is the row's mean without eta and v,
   integrating v_k out scales the unit's rows by g_k = 1 / (1 + su^2 C_k). A building's sums
   for the levels become
       C'_s = (sum of c over its rows with no effect) + sum over its units of g_k C_k,
       R'_s = (the same for c (y - m)) + sum over its units of g_k R_k,
   and `update_spread` and the level draw run on C' and R' in place of C and R.
3. Given the new levels, I draw su with v integrated out, then v. With r0 = y - m - eta, the
   unit sums C_k and R_k = sum c_i r0_i give each unit the marginal log density
       -log(1 + su^2 C_k) / 2 + R_k^2 / (2 (C_k + 1 / su^2)),
   which I sum over units, add the HalfNormal prior to, and slice-sample in log su. Then
   v_k ~ Normal(R_k / P_k, 1 / P_k) with P_k = C_k + 1 / su^2.
4. The noise step reads r0 - v.

Steps 2 and 3 draw (b, eta, su, v) given theta: each step integrates out only what a later
step draws again, so the sweep leaves the posterior unchanged.

With `Settings.joint_amp` I draw the zone amplitudes and the waves together given the levels
(`rentfrontier.amp_joint`), as `building_zones_gibbs` does.

I keep no draws of v: 935k effects over 4 chains and 1000 draws would take 30 GB. In their
place each chain keeps a running mean and variance of every effect over its draws after warmup
(Welford's update), saved as the kept arrays `unit_mean` and `unit_var`, (chains, units). su is
traced and kept as `unit_sd`, and it goes into the diagnostics and the summary. To predict a
held-out ad, `unit_offset` adds the posterior mean of its unit's effect, or 0 for a unit with no
training row.

    python -m rentfrontier.run --model building-zones-floor-asof2-unit --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import math
import sys
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import (
    amp_joint,
    b0,
    building_zones_floor_asof,
    building_zones_floor_asof2,
    two_zone,
)
from .building_zones_floor_asof2 import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Priors,
    Settings,
    gp_spec,
    site_rows,
    site_zone,
    split_index,
    wave_matrix,
)
from .building_zones_gibbs import _prior_vectors, gp_cov
from .two_zone import site_share

NAME = "building-zones-floor-asof2-unit"
# The HalfNormal scale of the unit effects' sd su, on log rent. Units of a building with the same
# size and floor columns rarely differ by more than 10 to 20% in rent, so 0.1 puts most of the
# prior mass below 0.2 and leaves su near 0 open.
UNIT_SD_PRIOR = 0.1
# The fewest training rows a unit needs to get an effect.
MIN_UNIT_ROWS = 1


@dataclass
class Design(building_zones_floor_asof2.Design):
    unit: np.ndarray = None  # (rows,) the row's unit number, -1 for no effect
    units: int = 0  # the number of units with an effect


def unit_index(frame: pd.DataFrame, held) -> tuple[np.ndarray, int]:
    """Each row's unit number and the number of units: the units with at least
    MIN_UNIT_ROWS training rows, numbered in sorted order of (building, unit_id), and -1 for
    the rest."""
    key = (frame.building.astype(str) + "|" + frame.unit_id.astype(str)).to_numpy(str)
    ok = frame.unit_id.notna().to_numpy()
    train = ok & ~np.asarray(held, bool)
    keys, counts = np.unique(key[train], return_counts=True)
    keys = keys[counts >= MIN_UNIT_ROWS]
    unit = pd.Index(keys).get_indexer(key)
    unit[~ok] = -1
    return unit.astype(np.int64), len(keys)


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The as-of floor design of `frame` on the corrected build
    (`building_zones_floor_asof2`), with each row's unit number."""
    held = building_zones_floor_asof.held_out(frame, held)
    d = building_zones_floor_asof2.design(frame, start, held=held, **kw)
    unit, units = unit_index(frame, held)
    return Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(d)},
        unit=unit,
        units=units,
    )


def subset(d: Design, mask: np.ndarray) -> Design:
    return dataclasses.replace(
        building_zones_floor_asof2.subset(d, mask), unit=d.unit[mask]
    )


def unit_offset(d: Design, kept: dict) -> np.ndarray:
    """Each row's posterior mean unit effect, averaged over chains, and 0 for a row with no
    effect."""
    mean = np.asarray(kept["unit_mean"], float).reshape(-1, d.units).mean(0)
    return np.where(d.unit >= 0, mean[np.maximum(d.unit, 0)], 0.0)


def make_sampler(d: Design, priors: Priors, settings: Settings, gp=None):
    """The jitted sweep, the initial state and the global system for design `d`, as
    `building_zones_gibbs.make_sampler` builds them (see there for `gp`), with the unit
    effects v and their sd su in the state as `v` and `unit_sd`."""
    jax, jnp = b0._jax()
    seg = jax.ops.segment_sum
    alpha = d.names.index("alpha")
    others = np.array([j for j in range(len(d.names)) if j != alpha])
    pb = len(others)
    W1 = d.weeks + 1
    Bc, sds = wave_matrix(d)
    K = len(sds)
    nz = len(d.surfaces)
    G = pb + W1 + 1 + K
    sl_b, sl_M, i_g, sl_w = (
        slice(0, pb),
        slice(pb, pb + W1),
        pb + W1,
        slice(pb + W1 + 1, G),
    )
    m_b, s_b, m_a, s_a = _prior_vectors(d, priors)
    prec_b, lin_b = 1 / s_b**2, m_b / s_b**2
    gps = []
    for spec in gp or ():
        pos = np.searchsorted(others, [d.names.index(c) for c in spec["cols"]])
        prec_b[pos], lin_b[pos] = 0.0, 0.0
        gps.append((pos, np.asarray(spec["x"], float), spec["amp"], spec["ls"]))
    m_g, s_g = priors.g
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    which = np.concatenate([np.full(len(s["sd"]), k) for k, s in enumerate(d.surfaces)])
    zone = site_zone(d)
    joint = (
        amp_joint.make_step(Bc, sds, which, zone, priors.amp)
        if settings.joint_amp
        else None
    )
    S = len(zone)
    rows_per_site = site_rows(d)
    n = len(d.y)
    U = d.units

    order = np.argsort(d.site, kind="stable")
    active = np.flatnonzero(rows_per_site > 0)
    rank = np.full(S, -1)
    rank[active] = np.arange(len(active))
    site_sorted = d.site[order]
    arank = rank[site_sorted]
    Q = settings.site_block
    blocks = []
    for q0 in range(0, len(active), Q):
        q1 = min(q0 + Q, len(active))
        r0, r1 = np.searchsorted(arank, [q0, q1])
        blocks.append((q0, q1, int(r0), int(r1)))
    # Rows with no effect go to unit U, whose effect stays 0 and whose sums no step reads.
    unit_sorted = np.where(d.unit[order] >= 0, d.unit[order], U)
    # Each unit's building. A unit with no training row keeps building 0 and sums of 0.
    unit_site = np.zeros(U, np.int64)
    has = unit_sorted < U
    unit_site[unit_sorted[has]] = site_sorted[has]
    x = d.x[order][:, others]
    data = dict(
        xs=[jnp.asarray(x[r0:r1]) for _, _, r0, r1 in blocks],
        wk=[jnp.asarray(d.week[order][r0:r1]) for _, _, r0, r1 in blocks],
        fr=[jnp.asarray(d.frac[order][r0:r1]) for _, _, r0, r1 in blocks],
        loc=[jnp.asarray(arank[r0:r1] - q0) for q0, _, r0, r1 in blocks],
        Bact=[jnp.asarray(Bc[active[q0:q1]]) for q0, q1, _, _ in blocks],
        y=jnp.asarray(d.y[order]),
        group=jnp.asarray(d.group[order]),
        site=jnp.asarray(site_sorted),
        unit=jnp.asarray(unit_sorted),
        unit_site=jnp.asarray(unit_site),
        Bc=jnp.asarray(Bc),
    )
    del x
    active_j = jnp.asarray(active)
    zone_j = jnp.asarray(zone)
    which_j = jnp.asarray(which)
    sds_j = jnp.asarray(sds)
    prec_b, lin_b = jnp.asarray(prec_b), jnp.asarray(lin_b)
    E = np.zeros((W1 - 1, W1 + 1))
    E[np.arange(W1 - 1), np.arange(W1 - 1)] = -1
    E[np.arange(W1 - 1), np.arange(1, W1)] = 1
    E[:, W1] = -1
    EtE = jnp.asarray(E.T @ E)
    share = site_share(d)
    parts = [slice(s["first"], s["first"] + s["sites"]) for s in d.surfaces]
    zone_share = [jnp.asarray(share[p] / max(share[p].sum(), 1e-300)) for p in parts]
    row_wgt = [
        jnp.asarray(rows_per_site[p] / max(rows_per_site[p].sum(), 1.0)) for p in parts
    ]

    def row_mean(D, theta, j):
        """x beta + L(t) at block j's rows, with alpha folded into the levels M."""
        M = theta[sl_M]
        xs, fr, wk = D["xs"], D["fr"], D["wk"]
        return xs[j] @ theta[sl_b] + (1 - fr[j]) * M[wk[j]] + fr[j] * M[wk[j] + 1]

    def weights(D, st):
        """Each row's weight c_i = lam_i / sigma_g^2."""
        return st["lam"] / st["sigma"][D["group"]] ** 2

    def global_system(D, st, y_all):
        """The precision and linear term of theta given the scales, from responses `y_all`
        in the sorted row order, with every building's level integrated out, and each
        building's sum of row weights C_s."""
        xs, wk, fr, loc, Bact = (D[k] for k in ("xs", "wk", "fr", "loc", "Bact"))
        site_all = D["site"]
        bsd2 = st["bld_sd"][zone_j] ** 2
        c_all = weights(D, st)
        C = seg(c_all, site_all, num_segments=S)
        h_eta = seg(c_all * y_all, site_all, num_segments=S)
        P = C + 1 / bsd2
        R = pb + W1
        XX = jnp.zeros((R, R))
        hR = jnp.zeros(R)
        Rw = jnp.zeros((R, K))
        ww = jnp.zeros((K, K))
        hw = jnp.zeros(K)
        for j, (q0, q1, r0, r1) in enumerate(blocks):
            c = c_all[r0:r1]
            yj = y_all[r0:r1]
            a0, a1 = 1 - fr[j], fr[j]
            nq = q1 - q0
            CX = seg(c[:, None] * xs[j], loc[j], num_segments=nq)
            flat = loc[j] * W1 + wk[j]
            CM = (
                seg(c * a0, flat, num_segments=nq * W1)
                + seg(c * a1, flat + 1, num_segments=nq * W1)
            ).reshape(nq, W1)
            CR = jnp.concatenate([CX, CM], axis=1)
            XX = XX.at[:pb, :pb].add((xs[j] * c[:, None]).T @ xs[j])
            XM = seg((c * a0)[:, None] * xs[j], wk[j], num_segments=W1) + seg(
                (c * a1)[:, None] * xs[j], wk[j] + 1, num_segments=W1
            )
            XX = XX.at[pb:, :pb].add(XM)
            XX = XX.at[:pb, pb:].add(XM.T)
            diag = seg(c * a0 * a0, wk[j], num_segments=W1) + seg(
                c * a1 * a1, wk[j] + 1, num_segments=W1
            )
            od = seg(c * a0 * a1, wk[j], num_segments=W1)[:-1]
            XX = XX.at[pb:, pb:].add(
                jnp.diag(diag) + jnp.diag(od, 1) + jnp.diag(od, -1)
            )
            hR = hR.at[:pb].add(xs[j].T @ (c * yj))
            hR = hR.at[pb:].add(
                seg(c * a0 * yj, wk[j], num_segments=W1)
                + seg(c * a1 * yj, wk[j] + 1, num_segments=W1)
            )
            ids = active_j[q0:q1]
            Pq, Cq, bq = P[ids], C[ids], bsd2[ids]
            XX = XX - (CR / Pq[:, None]).T @ CR
            Rw = Rw + (CR / (bq * Pq)[:, None]).T @ Bact[j]
            hR = hR - CR.T @ (h_eta[ids] / Pq)
            ww = ww + (Bact[j] * (Cq / (bq * Pq))[:, None]).T @ Bact[j]
            hw = hw + Bact[j].T @ (h_eta[ids] / (bq * Pq))
        A = jnp.zeros((G, G))
        h = jnp.zeros(G)
        A = A.at[:R, :R].set(XX)
        A = A.at[:R, sl_w].set(Rw)
        A = A.at[sl_w, :R].set(Rw.T)
        A = A.at[sl_w, sl_w].set(ww + jnp.diag(1 / (st["amp"][which_j] * sds_j) ** 2))
        h = h.at[:R].set(hR).at[sl_w].set(hw)
        A = A.at[sl_b, sl_b].add(jnp.diag(prec_b))
        h = h.at[sl_b].add(lin_b)
        for k, (pos, xk, _, _) in enumerate(gps):
            Lk = jnp.linalg.cholesky(gp_cov(jnp, xk, st["gp_ls"][k]))
            Ki = jax.scipy.linalg.cho_solve((Lk, True), jnp.eye(len(pos)))
            A = A.at[np.ix_(pos, pos)].add(Ki / st["gp_amp"][k] ** 2)
        A = A.at[pb, pb].add(1 / s_a**2)
        h = h.at[pb].add(m_a / s_a**2)
        A = A.at[pb : i_g + 1, pb : i_g + 1].add(EtE / st["tau"] ** 2)
        A = A.at[i_g, i_g].add(1 / s_g**2)
        h = h.at[i_g].add(m_g / s_g**2)
        return A, h

    def draw_theta(D, key, st, y_all):
        A, h = global_system(D, st, y_all)
        s = 1 / jnp.sqrt(jnp.diag(A))
        Cf = jnp.linalg.cholesky(A * s[:, None] * s[None, :])
        mean = jax.scipy.linalg.cho_solve((Cf, True), h * s)
        dev = jax.scipy.linalg.solve_triangular(
            Cf.T, jax.random.normal(key, (G,)), lower=False
        )
        return (mean + dev) * s

    def unit_sums(D, c, r):
        """Per unit, C_k = sum c_i and R_k = sum c_i r_i over its rows."""
        Cu = seg(c, D["unit"], num_segments=U + 1)[:U]
        Ru = seg(c * r, D["unit"], num_segments=U + 1)[:U]
        return Cu, Ru

    def level_sums(D, st, c, e):
        """Each building's C'_s and R'_s from the rows' weights c and remainders e = y - m,
        with the unit effects integrated out at su: a unit's rows count g_k = 1 / (1 +
        su^2 C_k) times."""
        Cs = seg(c, D["site"], num_segments=S)
        Rs = seg(c * e, D["site"], num_segments=S)
        Cu, Ru = unit_sums(D, c, e)
        lose = 1 - 1 / (1 + st["unit_sd"] ** 2 * Cu)
        Cs = Cs - seg(lose * Cu, D["unit_site"], num_segments=S)
        Rs = Rs - seg(lose * Ru, D["unit_site"], num_segments=S)
        return Cs, Rs

    def update_spread(key, st, C, Rs, F):
        """Each zone's spread b_z from the buildings' likelihood with their levels integrated
        out: per building, -log(1 + b^2 C_s) / 2 + (R_s - C_s F_s)^2 / (2 (C_s + 1 / b^2))."""
        Rp = Rs - C * F

        def logp(lb):
            b2 = jnp.exp(2 * lb)[zone_j]
            per = -0.5 * jnp.log1p(b2 * C) + 0.5 * Rp**2 / (C + 1 / b2)
            ll = seg(per, zone_j, num_segments=nz)
            return ll - jnp.exp(2 * lb) / (2 * BLD_SD_PRIOR**2) + lb

        return jnp.exp(b0.slice_vec(key, jnp.log(st["bld_sd"]), logp, 0.05))

    def update_units(key, st, Cu, Ru):
        """su with v integrated out, from each unit's sums C_k and R_k of the rows' weights
        and weighted remainders after the building levels, then v given su. The last entry
        of the returned v is the effect of rows with no unit, 0."""
        k1, k2 = jax.random.split(key)

        def logp(ls):
            s2 = jnp.exp(2 * ls[0])
            ll = jnp.sum(-0.5 * jnp.log1p(s2 * Cu) + 0.5 * Ru**2 / (Cu + 1 / s2))
            return (ll - s2 / (2 * UNIT_SD_PRIOR**2) + ls[0])[None]

        su = jnp.exp(b0.slice_vec(k1, jnp.log(st["unit_sd"])[None], logp, 0.05)[0])
        P = Cu + 1 / su**2
        v = Ru / P + jax.random.normal(k2, (U,)) / jnp.sqrt(P)
        return su, jnp.concatenate([v, jnp.zeros(1, v.dtype)])

    def update_noise(key, st, r, group_all):
        """nu, then sigma, with lam integrated out, then lam: b0's noise step."""
        k1, k2, k3 = jax.random.split(key, 3)
        a_nu, b_nu = priors.nu

        def logp_nu(lnu):
            nu = jnp.exp(lnu[0])
            ll = jnp.sum(b0.t_logpdf(r, nu, st["sigma"][group_all]))
            return (ll + a_nu * lnu[0] - b_nu * nu)[None]

        nu = jnp.exp(b0.slice_vec(k1, jnp.log(st["nu"])[None], logp_nu, 0.1)[0])

        def logp_sigma(ls):
            sig = jnp.exp(ls)
            ll = seg(b0.t_logpdf(r, nu, sig[group_all]), group_all, num_segments=4)
            return ll - sig**2 / (2 * priors.sigma**2) + ls

        sigma = jnp.exp(b0.slice_vec(k2, jnp.log(st["sigma"]), logp_sigma, 0.02))
        z2 = (r / sigma[group_all]) ** 2
        lam = jax.random.gamma(k3, (nu + 1) / 2, (n,)) / ((nu + z2) / 2)
        return nu, sigma, lam

    def update_tau(key, st, M, g):
        z = jnp.diff(M) - g
        ss, k = jnp.sum(z * z), z.shape[0]

        def logp(lt):
            t = jnp.exp(lt[0])
            return (-k * lt[0] - ss / (2 * t * t) - tau_rate * t + lt[0])[None]

        return jnp.exp(b0.slice_vec(key, jnp.log(st["tau"])[None], logp, 0.1)[0])

    def update_amp(key, st, w):
        q = seg((w / sds_j) ** 2, which_j, num_segments=nz)
        cnt = jnp.asarray(np.bincount(which, minlength=nz), dtype=w.dtype)

        def logp(la):
            a = jnp.exp(la)
            return -cnt * la - q / (2 * a * a) - a * a / (2 * priors.amp**2) + la

        return jnp.exp(b0.slice_vec(key, jnp.log(st["amp"]), logp, 0.1))

    def update_gp(key, st, theta):
        """Each process's lengthscale with its amplitude integrated out, then its amplitude:
        `building_zones_gibbs`'s step."""
        k1, k2 = jax.random.split(key)
        f = [theta[sl_b][pos] for pos, _, _, _ in gps]

        def quad(k, ls):
            Lk = jnp.linalg.cholesky(gp_cov(jnp, gps[k][1], ls))
            z = jax.scipy.linalg.solve_triangular(Lk, f[k], lower=True)
            return z @ z, 2 * jnp.sum(jnp.log(jnp.diag(Lk)))

        cnt = jnp.asarray([len(pos) for pos, _, _, _ in gps], dtype=theta.dtype)
        shape = jnp.asarray([a[0] for _, _, a, _ in gps]) + cnt / 2
        rate = jnp.asarray([a[1] for _, _, a, _ in gps])
        mu = jnp.asarray([m for _, _, _, (m, _) in gps])
        sd = jnp.asarray([s for _, _, _, (_, s) in gps])

        def parts_(ll):
            out = [quad(k, jnp.exp(ll[k])) for k in range(len(gps))]
            return jnp.stack([o[0] for o in out]), jnp.stack([o[1] for o in out])

        def logp_ls(ll):
            q, ld = parts_(ll)
            return (
                -ld / 2 - shape * jnp.log(rate + q / 2) - (ll - mu) ** 2 / (2 * sd**2)
            )

        ll = b0.slice_vec(k1, jnp.log(st["gp_ls"]), logp_ls, 0.3)
        q, _ = parts_(ll)
        amp2 = (rate + q / 2) / jax.random.gamma(k2, shape)
        return jnp.sqrt(amp2), jnp.exp(ll)

    def outputs(theta, lev, F):
        """The kept quantities building zones' NumPyro model reports, from one state."""
        M = theta[sl_M]
        g = theta[i_g]
        beta = (
            jnp.zeros(len(d.names), theta.dtype)
            .at[jnp.asarray(others)]
            .set(theta[sl_b])
            .at[alpha]
            .set(M[0])
        )
        pieces = [F[p] for p in parts]
        b = lev - F
        var_f, var_b = [], []
        for p, wgt in zip(parts, row_wgt):
            for v, out in ((F[p], var_f), (b[p], var_b)):
                mu = wgt @ v
                out.append(wgt @ (v - mu) ** 2)
        return dict(
            beta=beta,
            g=g,
            L=M - M[0],
            eta=jnp.diff(M) - g,
            gp_w=theta[sl_w],
            zone_level=jnp.stack([zs @ v for zs, v in zip(zone_share, pieces)]),
            zone_sd=jnp.stack([v.std() for v in pieces]),
            bld=b.astype(jnp.float32),
            zone_var_f=jnp.stack(var_f),
            zone_var_b=jnp.stack(var_b),
        )

    def sweep(D, key, st):
        k1, k2, k3, k4, k5, k6, k7 = jax.random.split(key, 7)
        theta = draw_theta(D, k1, st, D["y"] - st["v"][D["unit"]])
        w = theta[sl_w]
        F = D["Bc"] @ w
        m = jnp.concatenate([row_mean(D, theta, j) for j in range(len(blocks))])
        c = weights(D, st)
        C, Rs = level_sums(D, st, c, D["y"] - m)
        bsd = update_spread(k2, st, C, Rs, F)
        b2 = bsd[zone_j] ** 2
        P = C + 1 / b2
        lev = (Rs + F / b2) / P + jax.random.normal(k3, (S,)) / jnp.sqrt(P)
        r0 = D["y"] - m - lev[D["site"]]
        su, v = update_units(k7, st, *unit_sums(D, c, r0))
        r = r0 - v[D["unit"]]
        nu, sigma, lam = update_noise(k4, st, r, D["group"])
        tau = update_tau(k5, st, theta[sl_M], theta[i_g])
        if joint is None:
            amp = update_amp(k6, st, w)
        else:
            amp, w = joint(k6, lev, bsd, st["amp"])
            theta = theta.at[sl_w].set(w)
            F = D["Bc"] @ w
        new = dict(
            theta=theta,
            lev=lev,
            bld_sd=bsd,
            nu=nu,
            sigma=sigma,
            lam=lam,
            tau=tau,
            amp=amp,
            v=v,
            unit_sd=su,
        )
        if gps:
            new["gp_amp"], new["gp_ls"] = update_gp(
                jax.random.fold_in(key, 7), st, theta
            )
        return new, outputs(theta, lev, F)

    def init(key):
        k = jax.random.split(key, 6)
        jit = lambda kk, shape, sd: jnp.exp(sd * jax.random.normal(kk, shape))  # noqa: E731
        out = dict(
            theta=jnp.zeros(G),
            lev=jnp.zeros(S),
            bld_sd=0.2 * jit(k[0], (nz,), 0.1),
            nu=5.0 * jit(k[1], (), 0.2),
            sigma=0.15 * jit(k[2], (4,), 0.1),
            lam=jnp.ones(n),
            tau=0.005 * jit(k[3], (), 0.2),
            amp=0.5 * jit(k[4], (nz,), 0.2),
            v=jnp.zeros(U + 1),
            unit_sd=0.05 * jit(k[5], (), 0.2),
        )
        if gps:
            kg = jax.random.split(jax.random.fold_in(key, 7))
            out["gp_amp"] = jnp.asarray(
                [(a[1] / a[0]) ** 0.5 for _, _, a, _ in gps]
            ) * jit(kg[0], (len(gps),), 0.2)
            out["gp_ls"] = jnp.exp(jnp.asarray([m for _, _, _, (m, _) in gps])) * jit(
                kg[1], (len(gps),), 0.2
            )
        return out

    swept = jax.jit(jax.vmap(sweep, in_axes=(None, 0, 0)))
    return (
        lambda keys, st: swept(data, keys, st),
        jax.jit(jax.vmap(init)),
        dict(
            global_system=lambda st, y: global_system(data, st, y),
            order=order,
            G=G,
        ),
    )


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """Sample the posterior of design `d` with the blocked Gibbs sweep and the floor curves'
    Gaussian process priors, as `building_zones_gibbs.run` does, with su traced and kept as
    `unit_sd` and each chain's running mean and variance of the unit effects kept as
    `unit_mean` and `unit_var`, in the design's unit order."""
    jax, jnp = b0._jax()
    gp = gp_spec(d.names)
    t0 = time.perf_counter()
    sweep, init, _ = make_sampler(d, priors, settings, gp=gp)
    scales = ("nu", "sigma", "tau", "amp", "bld_sd", "unit_sd") + (
        ("gp_amp", "gp_ls") if gp else ()
    )
    traced = TRACED + ("unit_sd",) + (("gp_amp", "gp_ls") if gp else ())
    kept_names = KEPT + ("unit_sd",) + (("gp_amp", "gp_ls") if gp else ())
    key = jax.random.PRNGKey(settings.seed)
    key, sub = jax.random.split(key)
    st = init(jax.random.split(sub, settings.chains))
    jax.block_until_ready(st)
    setup_seconds = time.perf_counter() - t0

    @jax.jit
    def welford(acc, v, k):
        """The running mean and sum of squared deviations after the k-th draw v."""
        mean, m2 = acc
        new = mean + (v - mean) / k
        return new, m2 + (v - mean) * (v - new)

    U = d.units
    acc = (jnp.zeros((settings.chains, U)), jnp.zeros((settings.chains, U)))
    trace = {k: [] for k in traced}
    kept = {k: [] for k in kept_names}
    total = settings.warmup + settings.draws
    per = max(1, settings.draws // settings.chunks)
    marks = {"warmup": None}

    def output():
        stack = lambda v: np.stack(v, axis=1)  # noqa: E731
        now = time.perf_counter()
        sampling = now - marks["warmup"] if marks["warmup"] else 0.0
        warm = (marks["warmup"] or now) - t_first
        done = len(trace[traced[0]])
        moments = {
            "unit_mean": np.asarray(acc[0], np.float32),
            "unit_var": np.asarray(acc[1] / max(done - 1, 1), np.float32),
        }
        return {
            "trace": {k: stack(v) for k, v in trace.items()},
            "kept": {k: stack(v) for k, v in kept.items()} | moments,
            "seconds": {
                "setup": setup_seconds,
                "compile": compile_seconds,
                "warmup": warm,
                "sampling": sampling,
            },
            "result": {
                "gibbs": {
                    "sweeps": settings.warmup + done,
                    "seconds_per_sweep": (now - t_first)
                    / max(1, settings.warmup + done),
                }
            },
        }

    def scalars(st):
        return (
            f"nu {np.asarray(st['nu'])[:4].round(3)}, "
            f"amp {np.asarray(st['amp'])[:2].round(3).tolist()}, "
            f"bld_sd {np.asarray(st['bld_sd'])[:2].round(4).tolist()}, "
            f"unit_sd {np.asarray(st['unit_sd'])[:4].round(4).tolist()}, "
        )

    compile_seconds = 0.0
    t_first = time.perf_counter()
    for i in range(total):
        key, sub = jax.random.split(key)
        st, out = sweep(jax.random.split(sub, settings.chains), st)
        if i == 0:
            jax.block_until_ready(st)
            compile_seconds = time.perf_counter() - t_first
            t_first = time.perf_counter()
            log(f"first sweep (compile) {compile_seconds:.1f}s")
        if i == settings.warmup - 1 or (settings.warmup == 0 and i == 0):
            jax.block_until_ready(st)
            marks["warmup"] = time.perf_counter()
        if i >= settings.warmup:
            j = i - settings.warmup
            acc = welford(acc, st["v"][:, :U], j + 1.0)
            full = out | {k: st[k] for k in scales}
            for k in traced:
                trace[k].append(np.asarray(full[k]))
            if (j + 1) % settings.keep_every == 0:
                for k in kept_names:
                    kept[k].append(np.asarray(full[k]))
            if (j + 1) % per == 0:
                log(
                    f"draws {j + 1}/{settings.draws}: "
                    + scalars(st)
                    + f"tau {np.asarray(st['tau'])[:4].round(5)}, "
                    + (
                        f"gp_amp {np.asarray(st['gp_amp'])[:2].round(3).tolist()}, "
                        f"gp_ls {np.asarray(st['gp_ls'])[:2].round(3).tolist()}, "
                        if gp
                        else ""
                    )
                    + f"{time.perf_counter() - t0:.0f}s"
                )
                if j + 1 < settings.draws and checkpoint is not None and kept["beta"]:
                    checkpoint(output())
        elif (i + 1) % max(1, settings.warmup // 5) == 0:
            log(
                f"warmup {i + 1}/{settings.warmup}: "
                + scalars(st)
                + f"{time.perf_counter() - t0:.0f}s"
            )
    out = output()
    log(
        f"sampling {out['seconds']['sampling']:.0f}s, "
        f"{out['result']['gibbs']['seconds_per_sweep']:.3f}s a sweep of {settings.chains} chains"
    )
    return out


def diagnostics(trace: dict, names) -> dict:
    """The as-of floor model's convergence table, with the unit effects' sd."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = building_zones_floor_asof2.diagnostics(trace, names)
    rows = out["per_quantity"]
    x = np.asarray(trace["unit_sd"])
    if np.ptp(x) > 0:
        rows["unit_sd"] = {"rhat": split_rhat(x), "ess": ess(x)}
    worst = max(rows, key=lambda n: rows[n]["rhat"])
    least = min(rows, key=lambda n: rows[n]["ess"])
    return out | {
        "max_rhat": rows[worst]["rhat"],
        "max_rhat_name": worst,
        "min_ess": rows[least]["ess"],
        "min_ess_name": least,
        "passes": rows[worst]["rhat"] <= RHAT_GATE and rows[least]["ess"] > ESS_GATE,
    }


def summarize(kept: dict, names) -> dict:
    """The as-of floor model's summary, with the unit effects' sd."""
    out = building_zones_floor_asof2.summarize(kept, names)
    out["unit_effect"] = {"unit_sd": two_zone._q(np.asarray(kept["unit_sd"]))}
    return out


def run_record(d: Design) -> dict:
    """The as-of floor model's record on the corrected build, with the unit effects'
    settings."""
    return building_zones_floor_asof2.run_record(d) | {
        "unit_effect": {
            "key": "building and unit_id",
            "min_training_rows": MIN_UNIT_ROWS,
            "units": int(d.units),
            "sd_prior": f"HalfNormal({UNIT_SD_PRIOR})",
            "kept": "running mean and variance per chain (unit_mean, unit_var)",
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor-asof2-unit`: fit on the split's
    training rows and save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    building_zones_floor_asof.SPLIT = parser.parse_known_args(argv)[0].split
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
