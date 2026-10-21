"""Building zones on a blocked Gibbs sampler in place of ChEES-HMC.

The model is building zones' (`rentfrontier.building_zones`), unchanged:

    y ~ StudentT(nu, x beta + eta_site + L(t), sigma_group)
    eta_s ~ Normal(F(s), b_z)        F = Bc w,  w_j ~ Normal(0, amp_z sd_j)

with the walk, the noise and every prior as there. On all data, ChEES fitted its trajectory
to the 73k building levels and moved the waves, amplitudes and walk too little to mix. Here I
write the Student-t as a scale mixture, y_i ~ Normal(mean_i, sigma_g^2 / lam_i) with
lam_i ~ Gamma(nu / 2, nu / 2), so that given the scales every location and level term is
Gaussian. A sweep then runs these steps in order:

1. I draw the global block theta = (beta without alpha, the walk's levels M_0..M_W, g, the
   216 wave coefficients w) from its conditional with the building levels integrated out.
   Each level meets only its own rows and its prior, so its precision is the scalar
   P_s = sum_i c_i + 1 / b_z^2 with c_i = lam_i / sigma_g^2, and I eliminate the levels one
   building at a time (`global_system`). The 922 x 922 Schur complement is dense and I
   factor it whole.
2. I draw each zone's building spread b_z with the levels still integrated out, from each
   building's marginal likelihood given theta (`update_spread`).
3. I draw every building's level eta_s given theta and b_z, independently, centred on F(s).
4. I draw nu and sigma with lam integrated out, from the Student-t likelihood of the
   residuals, then lam given them.
5. I draw tau given the walk and each zone's amplitude given its waves.
6. With Gaussian process priors on some coefficients (`make_sampler`'s `gp`), I draw each
   process's amplitude and lengthscale given its coefficients.

Steps 1 to 3 draw (theta, b, eta) with eta marginalised until it is drawn last, and steps 4
draw (nu, sigma, lam) the same way, so every step leaves the posterior unchanged. The walk
is in the levels M with alpha = M_0 and L = M - M_0, as the NumPyro model writes it from
its flat totals D = M + Bs beta_season, whose map to (beta, M) has Jacobian 1.

    python -m rentfrontier.run --model building-zones-gibbs --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import math
import sys
import time
from dataclasses import dataclass

import numpy as np

from . import b0, building_zones, normal_walk
from .building_zones import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    design,
    diagnostics,
    site_rows,
    site_zone,
    split_index,
    subset,
    summarize,
    wave_matrix,
)
from .two_zone import site_share

NAME = "building-zones-gibbs"
# The nugget on a Gaussian process prior's covariance, in units of its amplitude squared:
# each coefficient's own variation of sd amp / 100 on top of the smooth curve. It keeps the
# covariance of closely spaced inputs invertible.
GP_NUGGET = 1e-4


@dataclass(frozen=True)
class Settings:
    chains: int = 4
    warmup: int = 500
    draws: int = 1000
    keep_every: int = 10
    seed: int = 20261020
    # Buildings per block of the Schur complement's dense products.
    site_block: int = 4096
    # Rounds of draws between progress lines and checkpoints.
    chunks: int = 10

    def to_dict(self):
        return dataclasses.asdict(self)


def run_record(d: Design) -> dict:
    """Building zones' record, without its ChEES settings, with the global block's size."""
    out = building_zones.run_record(d)
    for k in ("length_floor", "min_leapfrog_steps"):
        out.pop(k)
    _, sds = wave_matrix(d)
    out["gibbs"] = {"global_block": len(d.names) - 1 + d.weeks + 1 + 1 + len(sds)}
    return out


def gp_cov(jnp, x, ls):
    """The unit-amplitude squared exponential covariance of a process at inputs `x`, given
    its value 0 at input 0, with a nugget of GP_NUGGET on the diagonal."""
    K = jnp.exp(-0.5 * (x[:, None] - x[None, :]) ** 2 / ls**2)
    k0 = jnp.exp(-0.5 * x**2 / ls**2)
    return K - jnp.outer(k0, k0) + GP_NUGGET * jnp.eye(x.shape[0])


def _prior_vectors(d: Design, priors: Priors):
    """Prior means and sds of the coefficients other than alpha, in `names` order, and
    alpha's mean and sd."""
    m_fix, s_fix = normal_walk.prior_arrays(priors, d.names)
    fixed, steps, _ = split_index(d.names)
    alpha = d.names.index("alpha")
    pos = {int(j): k for k, j in enumerate(fixed)}
    m, s = [], []
    for j in range(len(d.names)):
        if j == alpha:
            continue
        if j in steps:
            m.append(priors.bath[0])
            s.append(priors.bath[1])
        else:
            m.append(m_fix[pos[j]])
            s.append(s_fix[pos[j]])
    return (
        np.asarray(m),
        np.asarray(s),
        float(m_fix[pos[alpha]]),
        float(s_fix[pos[alpha]]),
    )


def make_sampler(d: Design, priors: Priors, settings: Settings, gp=None):
    """The jitted sweep, the initial state and the global system for design `d`. The sweep and
    the initial state are vmapped over chains; `global_system` takes one chain's state.

    `gp` (optional) gives some coefficients a Gaussian process prior in place of their own
    Normal priors. It is a sequence of dicts, one per process, with
    - `cols`: the coefficients' names in `d.names`;
    - `x`: each coefficient's input, a float array as long as `cols`;
    - `amp`: the HalfNormal scale of the process's amplitude;
    - `ls`: the (mean, sd) of the log of its lengthscale.
    Each process has a squared exponential kernel pinned to 0 at input 0 (`gp_cov`), so the
    coefficients are the process at their inputs, measured from its value at 0. I draw them in
    the global block with prior precision Kc^-1 / amp^2, then each process's amplitude and
    lengthscale given them (`update_gp`), into the state's `gp_amp` and `gp_ls`."""
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
    # The coefficients' own prior precision and linear term, without those under a process.
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
    S = len(zone)
    rows_per_site = site_rows(d)
    n = len(d.y)

    # Rows sorted by building, and the buildings with rows in blocks of `site_block`.
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
    # The rows' data goes to the jitted sweep as an argument: closed over, it would be
    # compiled in as constants, which on all rows took over 12 GB of host memory.
    x, y = d.x[order][:, others], d.y[order]
    data = dict(
        xs=[jnp.asarray(x[r0:r1]) for _, _, r0, r1 in blocks],
        ys=[jnp.asarray(y[r0:r1]) for _, _, r0, r1 in blocks],
        wk=[jnp.asarray(d.week[order][r0:r1]) for _, _, r0, r1 in blocks],
        fr=[jnp.asarray(d.frac[order][r0:r1]) for _, _, r0, r1 in blocks],
        loc=[jnp.asarray(arank[r0:r1] - q0) for q0, _, r0, r1 in blocks],
        Bact=[jnp.asarray(Bc[active[q0:q1]]) for q0, q1, _, _ in blocks],
        y=jnp.asarray(y),
        group=jnp.asarray(d.group[order]),
        site=jnp.asarray(site_sorted),
        Bc=jnp.asarray(Bc),
    )
    del x, y
    active_j = jnp.asarray(active)
    zone_j = jnp.asarray(zone)
    which_j = jnp.asarray(which)
    sds_j = jnp.asarray(sds)
    prec_b, lin_b = jnp.asarray(prec_b), jnp.asarray(lin_b)
    # The walk's prior on (M, g): E (M, g) = diff(M) - g.
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

    def global_system(D, st):
        """The precision and linear term of theta given the scales, with every building's
        level integrated out, and each building's sum of row weights C_s."""
        xs, ys, wk, fr, loc, Bact = (
            D[k] for k in ("xs", "ys", "wk", "fr", "loc", "Bact")
        )
        y_all, group_all, site_all = D["y"], D["group"], D["site"]
        bsd2 = st["bld_sd"][zone_j] ** 2
        c_all = st["lam"] / st["sigma"][group_all] ** 2
        C = seg(c_all, site_all, num_segments=S)
        h_eta = seg(c_all * y_all, site_all, num_segments=S)
        P = C + 1 / bsd2
        R = pb + W1
        XX = jnp.zeros((R, R))
        hR = jnp.zeros(R)
        Rw = jnp.zeros((R, K))
        ww = jnp.zeros((K, K))
        hw = jnp.zeros(K)
        off = 0
        for j, (q0, q1, r0, r1) in enumerate(blocks):
            c = c_all[off : off + (r1 - r0)]
            off += r1 - r0
            a0, a1 = 1 - fr[j], fr[j]
            nq = q1 - q0
            # Each row's coefficients on (beta, M): its x and its two interpolation weights.
            CX = seg(c[:, None] * xs[j], loc[j], num_segments=nq)
            flat = loc[j] * W1 + wk[j]
            CM = (
                seg(c * a0, flat, num_segments=nq * W1)
                + seg(c * a1, flat + 1, num_segments=nq * W1)
            ).reshape(nq, W1)
            CR = jnp.concatenate([CX, CM], axis=1)
            # The rows' own precision on (beta, M).
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
            hR = hR.at[:pb].add(xs[j].T @ (c * ys[j]))
            hR = hR.at[pb:].add(
                seg(c * a0 * ys[j], wk[j], num_segments=W1)
                + seg(c * a1 * ys[j], wk[j] + 1, num_segments=W1)
            )
            # Minus what the building levels take: C_R' P^-1 C_R and its cross terms.
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
        # Priors: beta, alpha on M_0, the walk on (M, g), and g.
        A = A.at[sl_b, sl_b].add(jnp.diag(prec_b))
        h = h.at[sl_b].add(lin_b)
        for k, (pos, x, _, _) in enumerate(gps):
            Lk = jnp.linalg.cholesky(gp_cov(jnp, x, st["gp_ls"][k]))
            Ki = jax.scipy.linalg.cho_solve((Lk, True), jnp.eye(len(pos)))
            A = A.at[np.ix_(pos, pos)].add(Ki / st["gp_amp"][k] ** 2)
        A = A.at[pb, pb].add(1 / s_a**2)
        h = h.at[pb].add(m_a / s_a**2)
        A = A.at[pb : i_g + 1, pb : i_g + 1].add(EtE / st["tau"] ** 2)
        A = A.at[i_g, i_g].add(1 / s_g**2)
        h = h.at[i_g].add(m_g / s_g**2)
        return A, h, C

    def draw_theta(D, key, st):
        A, h, C = global_system(D, st)
        s = 1 / jnp.sqrt(jnp.diag(A))
        Cf = jnp.linalg.cholesky(A * s[:, None] * s[None, :])
        mean = jax.scipy.linalg.cho_solve((Cf, True), h * s)
        dev = jax.scipy.linalg.solve_triangular(
            Cf.T, jax.random.normal(key, (G,)), lower=False
        )
        return (mean + dev) * s, C

    def site_sums(D, theta, st):
        """Each row's mean without its building level, and per building the weighted sum of
        the rows' remainders R_s = sum_i c_i (y_i - mean_i)."""
        m = jnp.concatenate([row_mean(D, theta, j) for j in range(len(blocks))])
        c_all = st["lam"] / st["sigma"][D["group"]] ** 2
        return m, seg(c_all * (D["y"] - m), D["site"], num_segments=S)

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
        """Each process's amplitude, then its lengthscale, given its coefficients f:
        f ~ Normal(0, amp^2 Kc(ls)), amp ~ HalfNormal, log ls ~ Normal."""
        k1, k2 = jax.random.split(key)
        f = [theta[sl_b][pos] for pos, _, _, _ in gps]

        def quad(k, ls):
            Lk = jnp.linalg.cholesky(gp_cov(jnp, gps[k][1], ls))
            z = jax.scipy.linalg.solve_triangular(Lk, f[k], lower=True)
            return z @ z, 2 * jnp.sum(jnp.log(jnp.diag(Lk)))

        q = jnp.stack([quad(k, st["gp_ls"][k])[0] for k in range(len(gps))])
        cnt = jnp.asarray([len(pos) for pos, _, _, _ in gps], dtype=theta.dtype)
        scale = jnp.asarray([a for _, _, a, _ in gps])

        def logp_amp(la):
            a = jnp.exp(la)
            return -cnt * la - q / (2 * a * a) - a * a / (2 * scale**2) + la

        amp = jnp.exp(b0.slice_vec(k1, jnp.log(st["gp_amp"]), logp_amp, 0.2))
        mu = jnp.asarray([m for _, _, _, (m, _) in gps])
        sd = jnp.asarray([s for _, _, _, (_, s) in gps])

        def logp_ls(ll):
            parts = [quad(k, jnp.exp(ll[k])) for k in range(len(gps))]
            qq = jnp.stack([p[0] for p in parts])
            ld = jnp.stack([p[1] for p in parts])
            return -qq / (2 * amp**2) - ld / 2 - (ll - mu) ** 2 / (2 * sd**2)

        ls = jnp.exp(b0.slice_vec(k2, jnp.log(st["gp_ls"]), logp_ls, 0.2))
        return amp, ls

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
        k1, k2, k3, k4, k5, k6 = jax.random.split(key, 6)
        theta, C = draw_theta(D, k1, st)
        w = theta[sl_w]
        F = D["Bc"] @ w
        m, Rs = site_sums(D, theta, st)
        bsd = update_spread(k2, st, C, Rs, F)
        b2 = bsd[zone_j] ** 2
        P = C + 1 / b2
        lev = (Rs + F / b2) / P + jax.random.normal(k3, (S,)) / jnp.sqrt(P)
        r = D["y"] - m - lev[D["site"]]
        nu, sigma, lam = update_noise(k4, st, r, D["group"])
        tau = update_tau(k5, st, theta[sl_M], theta[i_g])
        amp = update_amp(k6, st, w)
        new = dict(
            theta=theta,
            lev=lev,
            bld_sd=bsd,
            nu=nu,
            sigma=sigma,
            lam=lam,
            tau=tau,
            amp=amp,
        )
        if gps:
            new["gp_amp"], new["gp_ls"] = update_gp(
                jax.random.fold_in(key, 7), st, theta
            )
        return new, outputs(theta, lev, F)

    def init(key):
        k = jax.random.split(key, 5)
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
        )
        if gps:
            kg = jax.random.split(jax.random.fold_in(key, 7))
            out["gp_amp"] = jnp.asarray([a for _, _, a, _ in gps]) * jit(
                kg[0], (len(gps),), 0.2
            )
            out["gp_ls"] = jnp.exp(jnp.asarray([m for _, _, _, (m, _) in gps])) * jit(
                kg[1], (len(gps),), 0.2
            )
        return out

    swept = jax.jit(jax.vmap(sweep, in_axes=(None, 0, 0)))
    return (
        lambda keys, st: swept(data, keys, st),
        jax.jit(jax.vmap(init)),
        dict(global_system=lambda st: global_system(data, st), order=order, G=G),
    )


def run(
    d: Design,
    priors: Priors,
    settings: Settings,
    log=print,
    checkpoint=None,
    gp=None,
):
    """Sample the posterior of design `d` with the blocked Gibbs sweep. Returns the kept draws
    and the trace as building zones' ChEES run does, (chains, draws, ...), and timings.
    `checkpoint` (if given) gets the same for the draws so far after each round. With `gp`
    (see `make_sampler`) the trace and the kept draws also carry `gp_amp` and `gp_ls`."""
    jax, _ = b0._jax()
    t0 = time.perf_counter()
    sweep, init, _ = make_sampler(d, priors, settings, gp=gp)
    scales = ("nu", "sigma", "tau", "amp", "bld_sd") + (
        ("gp_amp", "gp_ls") if gp else ()
    )
    traced = TRACED + (("gp_amp", "gp_ls") if gp else ())
    kept_names = KEPT + (("gp_amp", "gp_ls") if gp else ())
    key = jax.random.PRNGKey(settings.seed)
    key, sub = jax.random.split(key)
    st = init(jax.random.split(sub, settings.chains))
    jax.block_until_ready(st)
    setup_seconds = time.perf_counter() - t0
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
        return {
            "trace": {k: stack(v) for k, v in trace.items()},
            "kept": {k: stack(v) for k, v in kept.items()},
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
            full = out | {k: st[k] for k in scales}
            for k in traced:
                trace[k].append(np.asarray(full[k]))
            if (j + 1) % settings.keep_every == 0:
                for k in kept_names:
                    kept[k].append(np.asarray(full[k]))
            if (j + 1) % per == 0:
                log(
                    f"draws {j + 1}/{settings.draws}: nu {np.asarray(st['nu'])[:4].round(3)}, "
                    f"tau {np.asarray(st['tau'])[:4].round(5)}, "
                    f"amp {np.asarray(st['amp'])[:2].round(3).tolist()}, "
                    f"bld_sd {np.asarray(st['bld_sd'])[:2].round(4).tolist()}, "
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
                f"warmup {i + 1}/{settings.warmup}: nu {np.asarray(st['nu'])[:4].round(3)}, "
                f"amp {np.asarray(st['amp'])[:2].round(3).tolist()}, "
                f"bld_sd {np.asarray(st['bld_sd'])[:2].round(4).tolist()}, "
                f"{time.perf_counter() - t0:.0f}s"
            )
    out = output()
    log(
        f"sampling {out['seconds']['sampling']:.0f}s, "
        f"{out['result']['gibbs']['seconds_per_sweep']:.3f}s a sweep of {settings.chains} chains"
    )
    return out


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-gibbs`: fit on the split's training rows and
    save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
