"""B0: the rent baseline with bedrooms, baths, a damped trend and a season, and nothing else.

For row i, with y_i the log of its net-effective latest ask, dated at its latest ask's day t_i:

    y_i = alpha + Bed_i + Bath_i + T(t_i) + Season(t_i) + Flags_i + e_i,
    e_i ~ Student-t(nu, 0, sigma_g(i)), one sigma per bedroom group (studio, 1, 2, 3+).

- Bed_i: cumulative steps delta_k * 1[beds >= k] for k = 1..5, with 5 or more capped at 5.
- Bath_i: phi_k * 1[full baths >= k] for k = 2..4, beta_half * 1[half baths >= 1] and
  beta_bath_unknown when the full count is missing.
- T: a damped local linear trend on a weekly grid, read at t_i by linear interpolation:
      L_w = L_{w-1} + S_{w-1},  L_0 = 0,
      S_w = g + rho (S_{w-1} - g) + eta_w,  eta_w | lambda_w ~ N(0, tau^2 / lambda_w),
      lambda_w ~ Gamma(nu_T / 2, nu_T / 2),  S_0 ~ N(g, tau^2 / (1 - rho^2)),
  with rho = 0.5^(1 / h) for a half-life h in weeks.
- Season: two harmonics of the day of the year.
- Flags: offsets for furnished, short-term, room-share, income-restricted and rent-stabilized ads.

`design` leaves out any indicator no row sets. On the 2026-10-18 build those are the furnished
and short-term flags (the pipeline drops such ads) and the unknown bath count (every row has
one).

The sampler is a blocked Gibbs sampler in JAX, with every chain a lane of `jax.vmap`:

1. Given the residual weights w, the scales and the trend's lambda, tau and rho, I draw the
   coefficients, g and L_1..L_W jointly from their Gaussian conditional, by a dense Cholesky
   factor of its precision (about 900 by 900).
2. With w integrated out, I update nu and the four sigmas by slice sampling on the Student-t
   likelihood of the residuals. Then I draw each w_i from its Gamma conditional.
3. With lambda integrated out, I update h, tau and nu_T by slice sampling on the trend's
   Student-t innovations. tau and nu_T trade off there (a smaller scale with heavier tails),
   so I also slice along a random direction in (log tau, log nu_T). Then I draw each lambda_w
   from its Gamma conditional.
4. I redraw tau once more with the standardized slope deviations (S - g) / tau held fixed, an
   interweaving step: given those, tau scales the trend at every row, and the rows' likelihood
   pins it down where the centered update in step 3 crawls.

Updating the scales and tail weights with the latent weights integrated out keeps nu and nu_T
from sticking to their latent draws, which are 1.7 million and 900 strong.

    python -m rentfrontier.b0 prior DATASET [--rows N]
    python -m rentfrontier.run --model b0 --split latest --name NAME [--chains ...]
    python -m rentfrontier.loo NAME

`rentfrontier.run --model b0` hands its arguments to `main_run`, which reads the dataset
folder in FRONTIER_DATASET (written by `rentfrontier.b0data`). `rentfrontier.loo` hands a B0
run to `score`, which writes PSIS-LOO over the training rows and the held-out rows' predictive
medians, intervals and coverage.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, splits

NAME = "b0"
FLAGS = (
    "furnished",
    "short_term",
    "shared_space",
    "income_restricted",
    "rent_stabilized",
)
BED_STEPS = (1, 2, 3, 4, 5)
BATH_STEPS = (2, 3, 4)
HARMONICS = 2
YEAR_DAYS = 365.25
EPOCH = pd.Timestamp(
    "2000-01-03"
)  # a Monday; the weekly grid starts on the data's first week
# Rows of a block while summing over all rows, so the (chains, block, coefficients) arrays stay
# well under a gigabyte.
BLOCK = 1 << 18
LOO_BLOCK = 50_000  # rows per (draws, rows) log-density block while scoring


@dataclass(frozen=True)
class Priors:
    alpha: tuple = (math.log(2800), 0.5)
    bed: tuple = (0.15, 0.3)
    bath: tuple = (0.1, 0.2)
    half: tuple = (0.03, 0.05)
    bath_unknown: tuple = (0.0, 0.3)
    season: tuple = (0.0, 0.05)
    flag: tuple = (0.0, 0.5)
    # Weekly drift: 3% a year, sd 3% a year.
    g: tuple = (0.03 / 52, 0.03 / 52)
    # Half-life of a slope shock, in weeks: LogNormal(log 52, 0.5).
    log_h: tuple = (math.log(52), 0.5)
    # PC prior on tau: P(tau > tau_u) = tau_alpha. A shock of 0.0003 a week moves the yearly
    # growth rate by 1.6 points. With tau_u = 0.001 the prior trend over 2010..2026 ends
    # beyond +-5 log points in a tenth of draws, and a quarter of prior rents fall outside
    # $1,000..$30,000 on the 2026-10-18 rows. At 0.0003 a tenth do.
    tau_u: float = 0.0003
    tau_alpha: float = 0.01
    # Gamma(shape, rate)
    nu: tuple = (2.0, 0.1)
    nu_t: tuple = (2.0, 1.0)
    nu_t_min: float = 1.0
    sigma: float = 0.3  # HalfNormal scale

    def to_dict(self):
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Settings:
    chains: int = 4
    warmup: int = 1000
    draws: int = 1000
    keep_every: int = 10
    seed: int = 20261018

    def to_dict(self):
        return dataclasses.asdict(self)


@dataclass
class Design:
    """The fit's arrays: rows in the frame's order, training and held-out masks apart."""

    y: np.ndarray  # log latest ask
    x: np.ndarray  # (rows, coefficients) fixed design
    group: np.ndarray  # bedroom group 0..3
    week: np.ndarray  # grid point at or before the row's day
    frac: np.ndarray  # fraction of the week from that point
    weeks: int  # grid points after L_0
    names: list
    start: pd.Timestamp  # the day of grid point 0
    count: dict


def coefficient_names():
    names = ["alpha"]
    names += [f"bed>={k}" for k in BED_STEPS]
    names += [f"full>={k}" for k in BATH_STEPS]
    names += ["half>=1", "bath_unknown"]
    for k in range(1, HARMONICS + 1):
        names += [f"sin{k}", f"cos{k}"]
    names += [f"flag:{f}" for f in FLAGS]
    return names


def prior_arrays(priors: Priors, names):
    mean, sd = np.zeros(len(names)), np.zeros(len(names))
    for j, n in enumerate(names):
        if n == "alpha":
            m, s = priors.alpha
        elif n.startswith("bed>="):
            m, s = priors.bed
        elif n.startswith("full>="):
            m, s = priors.bath
        elif n == "half>=1":
            m, s = priors.half
        elif n == "bath_unknown":
            m, s = priors.bath_unknown
        elif n.startswith(("sin", "cos")):
            m, s = priors.season
        else:
            m, s = priors.flag
        mean[j], sd[j] = m, s
    return mean, sd


def load_frame(dataset: Path | None = None) -> pd.DataFrame:
    dataset = Path(dataset or os.environ["FRONTIER_DATASET"])
    frame = pd.read_parquet(dataset / "rows.parquet")
    frame.attrs["dataset"] = str(dataset)
    frame.attrs["source_sha256"] = json.loads((dataset / "manifest.json").read_text())[
        "rows_sha256"
    ]
    return frame


def design(frame: pd.DataFrame, start: pd.Timestamp | None = None) -> Design:
    """The B0 design of `frame`'s rows. The weekly grid starts at the Monday on or before
    `start`, the frame's earliest latest-ask day unless given."""
    day = pd.to_datetime(frame.latest_day)
    if start is None:
        start = day.min()
    start = EPOCH + pd.Timedelta(weeks=int((start - EPOCH).days // 7))
    u = (day - start).dt.days.to_numpy() / 7.0
    if (u < 0).any():
        raise ValueError("a row falls before the weekly grid's start")
    week = np.floor(u).astype(np.int64)
    frac = u - week
    beds = np.clip(np.round(frame.bedrooms.to_numpy(float)), 0, None)
    if np.isnan(beds).any():
        raise ValueError("B0 needs every row's bedroom count")
    full = frame.full_baths.to_numpy(float)
    half = np.nan_to_num(frame.half_baths.to_numpy(float), nan=0.0)
    known = ~np.isnan(full)
    doy = day.dt.dayofyear.to_numpy() - 1 + 0.5
    cols = [np.ones(len(frame))]
    cols += [(beds >= k).astype(float) for k in BED_STEPS]
    cols += [(known & (np.nan_to_num(full) >= k)).astype(float) for k in BATH_STEPS]
    cols += [(half >= 1).astype(float), (~known).astype(float)]
    for k in range(1, HARMONICS + 1):
        angle = 2 * np.pi * k * doy / YEAR_DAYS
        cols += [np.sin(angle), np.cos(angle)]
    cols += [frame[f].fillna(False).to_numpy(bool).astype(float) for f in FLAGS]
    x = np.column_stack(cols)
    names = coefficient_names()
    count = {n: int(x[:, j].sum()) for j, n in enumerate(names) if n != "alpha"}
    # An indicator no row sets (the pipeline drops furnished and short-term ads, and every
    # row has a full-bath count) has only its prior, so I leave it out of the design.
    keep = [
        j
        for j, n in enumerate(names)
        if n == "alpha" or n.startswith(("sin", "cos")) or count[n] > 0
    ]
    x, names = x[:, keep], [names[j] for j in keep]
    return Design(
        y=np.log(frame.latest_ask.to_numpy(float)),
        x=x,
        group=np.minimum(beds, 3).astype(np.int32),
        week=week,
        frac=frac,
        weeks=int(week.max()) + 1,
        names=names,
        start=start,
        count=count,
    )


def subset(d: Design, mask: np.ndarray) -> Design:
    return dataclasses.replace(
        d,
        y=d.y[mask],
        x=d.x[mask],
        group=d.group[mask],
        week=d.week[mask],
        frac=d.frac[mask],
    )


# ------------------------------------------------------------------ the sampler (JAX)


def _jax():
    import jax

    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jnp

    return jax, jnp


def t_logpdf(r, nu, sigma):
    """Student-t log density of r with nu degrees of freedom and scale sigma."""
    from jax.scipy.special import gammaln

    _, jnp = _jax()
    z = r / sigma
    return (
        gammaln((nu + 1) / 2)
        - gammaln(nu / 2)
        - 0.5 * jnp.log(nu * jnp.pi)
        - jnp.log(sigma)
        - (nu + 1) / 2 * jnp.log1p(z * z / nu)
    )


def slice_vec(key, x0, logp, width, steps_out=12, shrink=64):
    """One slice-sampling update of each coordinate of x0, coordinates conditionally
    independent, logp mapping a vector to a vector of log densities. Stepping out goes up to
    `steps_out` widths on each side, shrinkage up to `shrink` tries."""
    jax, jnp = _jax()
    k1, k2, k3 = jax.random.split(key, 3)
    k = x0.shape[0]
    level = logp(x0) - jax.random.exponential(k1, (k,))
    left = x0 - width * jax.random.uniform(k2, (k,))
    right = left + width

    def out(i, lr):
        lo, hi = lr
        lo = jnp.where(logp(lo) > level, lo - width, lo)
        hi = jnp.where(logp(hi) > level, hi + width, hi)
        return lo, hi

    left, right = jax.lax.fori_loop(0, steps_out, out, (left, right))

    def cond(s):
        i, _, _, _, done, _ = s
        return (i < shrink) & ~jnp.all(done)

    def body(s):
        i, lo, hi, x, done, key = s
        key, sub = jax.random.split(key)
        prop = lo + (hi - lo) * jax.random.uniform(sub, (k,))
        ok = logp(prop) > level
        take = ok & ~done
        x = jnp.where(take, prop, x)
        lo = jnp.where(~ok & ~done & (prop < x0), prop, lo)
        hi = jnp.where(~ok & ~done & (prop >= x0), prop, hi)
        return i + 1, lo, hi, x, done | ok, key

    _, _, _, x, done, _ = jax.lax.while_loop(
        cond, body, (0, left, right, x0, jnp.zeros(k, bool), k3)
    )
    return jnp.where(done, x, x0)


def make_sampler(d: Design, priors: Priors, settings: Settings):
    """The jitted sweep and initial state for design `d`, vmapped over chains."""
    jax, jnp = _jax()
    n, p = d.x.shape
    W = d.weeks  # unknown grid points L_1..L_W
    D = p + 1 + W  # coefficients, g, L
    m_beta, s_beta = prior_arrays(priors, d.names)
    m_g, s_g = priors.g
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    blocks = [(lo, min(lo + BLOCK, n)) for lo in range(0, n, BLOCK)]
    xs = [jnp.asarray(d.x[lo:hi]) for lo, hi in blocks]
    ys = [jnp.asarray(d.y[lo:hi]) for lo, hi in blocks]
    gs = [jnp.asarray(d.group[lo:hi]) for lo, hi in blocks]
    wk = [jnp.asarray(d.week[lo:hi]) for lo, hi in blocks]
    fr = [jnp.asarray(d.frac[lo:hi]) for lo, hi in blocks]
    group_n = np.bincount(d.group, minlength=4)

    def trend_rows(L_full, j):
        """The trend at block j's rows, from the grid L_0..L_W."""
        return (1 - fr[j]) * L_full[wk[j]] + fr[j] * L_full[wk[j] + 1]

    def mean_rows(beta, L_full, j):
        return xs[j] @ beta + trend_rows(L_full, j)

    def ar_precision(rho, tau, lam):
        """Precision of z = S - g: z_0 stationary, z_w = rho z_{w-1} + eta_w (lam[0] unused)."""
        prec = jnp.concatenate([((1 - rho**2) / tau**2)[None], lam[1:] / tau**2])
        # B z = innovations: B[w, w] = 1, B[w, w-1] = -rho.
        B = jnp.eye(W) - rho * jnp.eye(W, k=-1)
        return B, prec

    def draw_theta(key, st):
        w, sigma = st["w"], st["sigma"]
        P = jnp.zeros((D, D))
        b = jnp.zeros(D)
        PL = jnp.zeros((W + 1, W + 1))
        bL = jnp.zeros(W + 1)
        XL = jnp.zeros((W + 1, p))
        XX = jnp.zeros((p, p))
        Xy = jnp.zeros(p)
        for j, (lo, hi) in enumerate(blocks):
            c = w[lo:hi] / sigma[gs[j]] ** 2
            a0, a1 = 1 - fr[j], fr[j]
            XX = XX + (xs[j] * c[:, None]).T @ xs[j]
            Xy = Xy + xs[j].T @ (c * ys[j])
            seg = lambda v, idx: jax.ops.segment_sum(v, idx, num_segments=W + 1)  # noqa: E731
            diag = seg(c * a0 * a0, wk[j]) + seg(c * a1 * a1, wk[j] + 1)
            off = seg(c * a0 * a1, wk[j])
            PL = PL + jnp.diag(diag) + jnp.diag(off[:-1], 1) + jnp.diag(off[:-1], -1)
            bL = bL + seg(c * a0 * ys[j], wk[j]) + seg(c * a1 * ys[j], wk[j] + 1)
            XL = (
                XL
                + seg((c * a0)[:, None] * xs[j], wk[j])
                + seg((c * a1)[:, None] * xs[j], wk[j] + 1)
            )
        # L_0 = 0: drop grid point 0.
        PL, bL, XL = PL[1:, 1:], bL[1:], XL[1:]
        # Prior on (g, L): z = S - g, S_j = L_{j+1} - L_j over grid points 0..W.
        B, prec = ar_precision(st["rho"], st["tau"], st["lam"])
        Dm = jnp.eye(W) - jnp.eye(W, k=-1)  # S = Dm L over L_1..L_W
        M = jnp.concatenate([-jnp.ones((W, 1)), Dm], axis=1)  # z = M (g, L)
        E = B @ M
        prior_gl = (E * prec[:, None]).T @ E
        sl_b = slice(0, p)
        sl_g = p
        sl_L = slice(p + 1, D)
        P = P.at[sl_b, sl_b].set(XX + jnp.diag(1 / jnp.asarray(s_beta) ** 2))
        P = P.at[sl_b, sl_L].set(XL.T)
        P = P.at[sl_L, sl_b].set(XL)
        P = P.at[p:, p:].add(prior_gl)
        P = P.at[sl_L, sl_L].add(PL)
        P = P.at[sl_g, sl_g].add(1 / s_g**2)
        b = b.at[sl_b].set(Xy + jnp.asarray(m_beta) / jnp.asarray(s_beta) ** 2)
        b = b.at[sl_L].set(bL)
        b = b.at[sl_g].add(m_g / s_g**2)
        # Scale to unit diagonal before factoring.
        s = 1 / jnp.sqrt(jnp.diag(P))
        Ps = P * s[:, None] * s[None, :]
        C = jnp.linalg.cholesky(Ps)
        mean = jax.scipy.linalg.cho_solve((C, True), b * s)
        z = jax.random.normal(key, (D,))
        dev = jax.scipy.linalg.solve_triangular(C.T, z, lower=False)
        theta = (mean + dev) * s
        return theta[sl_b], theta[sl_g], jnp.concatenate([jnp.zeros(1), theta[sl_L]])

    def residuals(beta, L_full):
        return jnp.concatenate(
            [ys[j] - mean_rows(beta, L_full, j) for j in range(len(blocks))]
        )

    group_all = jnp.asarray(d.group)

    def update_noise(key, st, r):
        k1, k2, k3 = jax.random.split(key, 3)
        a_nu, b_nu = priors.nu

        def logp_nu(lnu):
            nu = jnp.exp(lnu[0])
            ll = jnp.sum(t_logpdf(r, nu, st["sigma"][group_all]))
            return (ll + a_nu * lnu[0] - b_nu * nu)[None]

        lnu = slice_vec(k1, jnp.log(st["nu"])[None], logp_nu, 0.2)
        nu = jnp.exp(lnu[0])

        def logp_sigma(ls):
            sig = jnp.exp(ls)
            ll = jax.ops.segment_sum(
                t_logpdf(r, nu, sig[group_all]), group_all, num_segments=4
            )
            return ll - sig**2 / (2 * priors.sigma**2) + ls

        ls = slice_vec(k2, jnp.log(st["sigma"]), logp_sigma, 0.05)
        sigma = jnp.exp(ls)
        z2 = (r / sigma[group_all]) ** 2
        w = jax.random.gamma(k3, (nu + 1) / 2, (n,)) / ((nu + z2) / 2)
        return nu, sigma, w

    def update_trend(key, st, g, L_full):
        k1, k2, k3, k4 = jax.random.split(key, 4)
        S = jnp.diff(L_full)  # S_0..S_{W-1}
        z = S - g
        a_t, b_t = priors.nu_t

        def ll(rho, tau, nu_t):
            eta = z[1:] - rho * z[:-1]
            stat = 0.5 * jnp.log((1 - rho**2) / (2 * jnp.pi * tau**2)) - (
                (1 - rho**2) * z[0] ** 2 / (2 * tau**2)
            )
            return stat + jnp.sum(t_logpdf(eta, nu_t, tau))

        def rho_of(lh):
            return 0.5 ** (1 / jnp.exp(lh))

        mu_h, sd_h = priors.log_h

        def logp_h(lh):
            return (
                ll(rho_of(lh[0]), st["tau"], st["nu_t"])
                - (lh[0] - mu_h) ** 2 / (2 * sd_h**2)
            )[None]

        lh = slice_vec(k1, jnp.log(st["h"])[None], logp_h, 0.3)[0]
        rho = rho_of(lh)

        def logp_tau(lt):
            tau = jnp.exp(lt[0])
            return (ll(rho, tau, st["nu_t"]) - tau_rate * tau + lt[0])[None]

        tau = jnp.exp(slice_vec(k2, jnp.log(st["tau"])[None], logp_tau, 0.3)[0])

        def logp_nut(ln):
            nu_t = jnp.exp(ln[0])
            lp = ll(rho, tau, nu_t) + a_t * ln[0] - b_t * nu_t
            return jnp.where(nu_t > priors.nu_t_min, lp, -jnp.inf)[None]

        nu_t = jnp.exp(slice_vec(k3, jnp.log(st["nu_t"])[None], logp_nut, 0.3)[0])

        # tau and nu_T trade off in the shocks' t-likelihood (a smaller scale with heavier
        # tails), so I also slice along a random direction in (log tau, log nu_T).
        k4, k5, k6 = jax.random.split(k4, 3)
        angle = jax.random.uniform(k5, (), maxval=2 * jnp.pi)
        u = jnp.stack([jnp.cos(angle), jnp.sin(angle)])
        x0 = jnp.log(jnp.stack([tau, nu_t]))

        def logp_joint(s):
            lt, ln = x0 + s[0] * u
            tau_, nu_ = jnp.exp(lt), jnp.exp(ln)
            lp = ll(rho, tau_, nu_) - tau_rate * tau_ + lt + a_t * ln - b_t * nu_
            return jnp.where(nu_ > priors.nu_t_min, lp, -jnp.inf)[None]

        s = slice_vec(k6, jnp.zeros(1), logp_joint, 0.3)[0]
        tau, nu_t = jnp.exp(x0 + s * u)
        eta = z[1:] - rho * z[:-1]
        lam_rest = jax.random.gamma(k4, (nu_t + 1) / 2, (W - 1,)) / (
            (nu_t + (eta / tau) ** 2) / 2
        )
        lam = jnp.concatenate([jnp.ones(1), lam_rest])
        return jnp.exp(lh), rho, tau, nu_t, lam, eta

    def interweave_tau(key, r, w, sigma, g, L_full, tau, eta):
        """Redraw tau with the standardized slope deviations zeta = (S - g) / tau held fixed.
        The trend is then L_k = g k + tau Z_k with Z the running sum of zeta, so given the
        residual weights the rows' Gaussian likelihood is quadratic in tau."""
        zeta = (jnp.diff(L_full) - g) / tau
        Z = jnp.concatenate([jnp.zeros(1), jnp.cumsum(zeta)])
        A = jnp.zeros(())
        Bs = jnp.zeros(())
        for j, (lo, hi) in enumerate(blocks):
            c = w[lo:hi] / sigma[gs[j]] ** 2
            b = trend_rows(Z, j)
            r0 = r[lo:hi] + tau * b
            A = A + jnp.sum(c * b * b)
            Bs = Bs + jnp.sum(c * b * r0)

        def logp(lt):
            t = jnp.exp(lt[0])
            return (-(A * t * t - 2 * Bs * t) / 2 - tau_rate * t + lt[0])[None]

        new = jnp.exp(slice_vec(key, jnp.log(tau)[None], logp, 0.3)[0])
        grid = jnp.arange(W + 1, dtype=L_full.dtype)
        return new, g * grid + new * Z, eta * (new / tau)

    def sweep(key, st):
        k1, k2, k3, k4 = jax.random.split(key, 4)
        beta, g, L_full = draw_theta(k1, st)
        r = residuals(beta, L_full)
        nu, sigma, w = update_noise(k2, st, r)
        h, rho, tau, nu_t, lam, eta = update_trend(
            k3, {**st, "nu": nu, "sigma": sigma}, g, L_full
        )
        tau, L_full, eta = interweave_tau(k4, r, w, sigma, g, L_full, tau, eta)
        new = dict(
            st,
            beta=beta,
            g=g,
            L=L_full,
            nu=nu,
            sigma=sigma,
            w=w,
            h=h,
            rho=rho,
            tau=tau,
            nu_t=nu_t,
            lam=lam,
            eta=eta,
        )
        return new

    def init(key):
        k = jax.random.split(key, 6)
        beta = jnp.asarray(m_beta).at[0].set(float(np.mean(d.y)))
        h = 52 * jnp.exp(0.3 * jax.random.normal(k[0]))
        return dict(
            beta=beta + 0.01 * jax.random.normal(k[1], (p,)),
            g=jnp.asarray(m_g),
            L=jnp.zeros(W + 1),
            nu=10 * jnp.exp(0.3 * jax.random.normal(k[2])),
            sigma=0.3 * jnp.exp(0.2 * jax.random.normal(k[3], (4,))),
            w=jnp.ones(n),
            h=h,
            rho=0.5 ** (1 / h),
            tau=2e-4 * jnp.exp(0.3 * jax.random.normal(k[4])),
            nu_t=4.0 * jnp.exp(0.2 * jax.random.normal(k[5])),
            lam=jnp.ones(W),
            eta=jnp.zeros(W - 1),
        )

    del group_n
    return jax.jit(jax.vmap(sweep)), jax.jit(jax.vmap(init))


KEPT = ("beta", "g", "L", "nu", "sigma", "h", "rho", "tau", "nu_t", "eta", "lam")
TRACED = ("beta", "g", "nu", "sigma", "h", "tau", "nu_t")


def run(d: Design, priors: Priors, settings: Settings, log=print) -> dict:
    """Sample the posterior of design `d`. Returns kept draws (chains, kept, ...), the trace of
    every post-warmup draw for the scalar parameters and the coefficients, and timings."""
    jax, jnp = _jax()
    t0 = time.perf_counter()
    sweep, init = make_sampler(d, priors, settings)
    key = jax.random.PRNGKey(settings.seed)
    key, sub = jax.random.split(key)
    st = init(jax.random.split(sub, settings.chains))
    jax.block_until_ready(st)
    compile_start = time.perf_counter()
    trace = {k: [] for k in TRACED}
    kept = {k: [] for k in KEPT}
    total = settings.warmup + settings.draws
    every = max(1, total // 20)
    for i in range(total):
        key, sub = jax.random.split(key)
        st = sweep(jax.random.split(sub, settings.chains), st)
        if i == 0:
            jax.block_until_ready(st)
            log(f"first sweep (compile) {time.perf_counter() - compile_start:.1f}s")
        if i >= settings.warmup:
            j = i - settings.warmup
            for k in TRACED:
                trace[k].append(np.asarray(st[k]))
            if (j + 1) % settings.keep_every == 0:
                for k in KEPT:
                    kept[k].append(np.asarray(st[k]))
        if (i + 1) % every == 0:
            log(
                f"sweep {i + 1}/{total}: nu {np.asarray(st['nu']).round(2)}, "
                f"sigma[1] {np.asarray(st['sigma'])[:, 1].round(4)}, "
                f"h {np.asarray(st['h']).round(1)}, tau {np.asarray(st['tau'])}, "
                f"{time.perf_counter() - t0:.0f}s"
            )
    seconds = time.perf_counter() - t0
    stack = lambda v: np.stack(v, axis=1)  # noqa: E731  (chains, draws, ...)
    return {
        "trace": {k: stack(v) for k, v in trace.items()},
        "kept": {k: stack(v) for k, v in kept.items()},
        "seconds": {"sampling": seconds},
    }


# ------------------------------------------------------------------ prior predictive


def prior_draws(d: Design, priors: Priors, draws: int, seed: int = 0) -> dict:
    """Parameters drawn from the priors, the trend simulated forward on the grid."""
    rng = np.random.default_rng(seed)
    m_beta, s_beta = prior_arrays(priors, d.names)
    W = d.weeks
    beta = rng.normal(m_beta, s_beta, (draws, len(m_beta)))
    g = rng.normal(*priors.g, draws)
    h = np.exp(rng.normal(*priors.log_h, draws))
    rho = 0.5 ** (1 / h)
    tau = rng.exponential(priors.tau_u / -math.log(priors.tau_alpha), draws)
    nu_t = np.empty(draws)
    for i in range(draws):
        while True:
            v = rng.gamma(priors.nu_t[0], 1 / priors.nu_t[1])
            if v > priors.nu_t_min:
                nu_t[i] = v
                break
    lam = rng.gamma(nu_t[:, None] / 2, 2 / nu_t[:, None], (draws, W))
    eta = rng.normal(0, tau[:, None] / np.sqrt(lam))
    z = np.empty((draws, W))
    z[:, 0] = rng.normal(0, tau / np.sqrt(1 - rho**2))
    for w in range(1, W):
        z[:, w] = rho * z[:, w - 1] + eta[:, w]
    S = g[:, None] + z
    L = np.concatenate([np.zeros((draws, 1)), np.cumsum(S, axis=1)], axis=1)
    nu = rng.gamma(priors.nu[0], 1 / priors.nu[1], draws)
    sigma = np.abs(rng.normal(0, priors.sigma, (draws, 4)))
    return dict(
        beta=beta, g=g, h=h, rho=rho, tau=tau, nu_t=nu_t, L=L, nu=nu, sigma=sigma
    )


def prior_predictive(d: Design, priors: Priors, draws=200, rows=50_000, seed=0) -> dict:
    """Rents simulated from the prior at a sample of the design's rows: quantiles and the
    share between $1,000 and $30,000."""
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(d.y), size=min(rows, len(d.y)), replace=False)
    s = subset(d, np.isin(np.arange(len(d.y)), pick))
    pr = prior_draws(s, priors, draws, seed)
    trend = (1 - s.frac) * pr["L"][:, s.week] + s.frac * pr["L"][:, s.week + 1]
    mu = pr["beta"] @ s.x.T + trend
    eps = rng.standard_t(pr["nu"][:, None], mu.shape) * pr["sigma"][:, s.group]
    rent = np.exp(mu + eps)
    q = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    return {
        "draws": draws,
        "rows": len(s.y),
        "rent_quantiles": dict(
            zip(map(str, q), np.quantile(rent, q).round(0).tolist())
        ),
        "share_1000_30000": float(np.mean((rent >= 1000) & (rent <= 30000))),
        "observed_quantiles": dict(
            zip(map(str, q), np.quantile(np.exp(s.y), q).round(0).tolist())
        ),
        "trend_end_quantiles": dict(
            zip(map(str, q), np.quantile(pr["L"][:, -1], q).round(3).tolist())
        ),
    }


# ------------------------------------------------------------------ scoring


def loglik_rows(d: Design, kept: dict, lo: int, hi: int) -> np.ndarray:
    """(draws, rows) Student-t log densities of rows lo..hi under the kept draws."""
    beta = kept["beta"].reshape(-1, kept["beta"].shape[-1])
    L = kept["L"].reshape(-1, kept["L"].shape[-1])
    nu = kept["nu"].reshape(-1)
    sigma = kept["sigma"].reshape(-1, 4)
    wk, f = d.week[lo:hi], d.frac[lo:hi]
    mu = beta @ d.x[lo:hi].T + (1 - f) * L[:, wk] + f * L[:, wk + 1]
    from scipy.stats import t as student

    return student.logpdf(
        d.y[lo:hi][None, :] - mu, nu[:, None], scale=sigma[:, d.group[lo:hi]]
    )


def predictive(d: Design, kept: dict, per_draw=10, seed=0, block=5_000) -> dict:
    """Held-out rows' predictive medians and 80%/95% intervals of log rent, by simulation."""
    rng = np.random.default_rng(seed)
    beta = kept["beta"].reshape(-1, kept["beta"].shape[-1])
    L = kept["L"].reshape(-1, kept["L"].shape[-1])
    nu = kept["nu"].reshape(-1)
    sigma = kept["sigma"].reshape(-1, 4)
    q = np.array([0.025, 0.1, 0.5, 0.9, 0.975])
    out = np.empty((len(d.y), len(q)))
    for lo in range(0, len(d.y), block):
        hi = min(lo + block, len(d.y))
        wk, f = d.week[lo:hi], d.frac[lo:hi]
        mu = beta @ d.x[lo:hi].T + (1 - f) * L[:, wk] + f * L[:, wk + 1]
        sims = (
            mu[None]
            + rng.standard_t(np.broadcast_to(nu[None, :, None], (per_draw, *mu.shape)))
            * sigma[:, d.group[lo:hi]][None]
        )
        out[lo:hi] = np.quantile(sims.reshape(-1, hi - lo), q, axis=0).T
    return {"quantiles": q, "values": out}


def coverage(d: Design, pred: dict) -> dict:
    v = pred["values"]
    y = d.y
    err = y - v[:, 2]
    return {
        "rows": len(y),
        "coverage_80": float(np.mean((y >= v[:, 1]) & (y <= v[:, 3]))),
        "coverage_95": float(np.mean((y >= v[:, 0]) & (y <= v[:, 4]))),
        "median_abs_error_pct": float(100 * np.median(np.abs(np.expm1(err)))),
        "bias_pct": float(100 * np.expm1(np.median(err))),
    }


def summarize(kept: dict, names) -> dict:
    """Posterior medians and 95% intervals: coefficients as % premiums, hyperparameters as
    they are."""

    def q(x):
        lo, med, hi = np.quantile(np.asarray(x).reshape(-1), [0.025, 0.5, 0.975])
        return {"median": float(med), "lo": float(lo), "hi": float(hi)}

    beta = kept["beta"].reshape(-1, kept["beta"].shape[-1])
    coef = {}
    for j, n in enumerate(names):
        if n == "alpha":
            coef[n] = {k: float(math.exp(v)) for k, v in q(beta[:, j]).items()}
        elif n.startswith(("sin", "cos")):
            coef[n] = q(beta[:, j])
        else:
            coef[n] = {k: 100 * math.expm1(v) for k, v in q(beta[:, j]).items()}
    full2 = beta[:, names.index("full>=2")]
    half = beta[:, names.index("half>=1")]
    hyper = {
        "nu": q(kept["nu"]),
        **{f"sigma[{i}]": q(kept["sigma"][..., i]) for i in range(4)},
        "g_yearly_pct": q(100 * np.expm1(52 * kept["g"])),
        "h_months": q(kept["h"] * 12 / 52),
        "tau": q(kept["tau"]),
        "nu_t": q(kept["nu_t"]),
        "half_over_full2": q(half / full2),
    }
    return {"coefficients": coef, "hyper": hyper}


def season_curve(kept: dict, names, days=np.arange(365)) -> dict:
    beta = kept["beta"].reshape(-1, kept["beta"].shape[-1])
    cols = []
    for k in range(1, HARMONICS + 1):
        angle = 2 * np.pi * k * (days + 0.5) / YEAR_DAYS
        cols += [np.sin(angle), np.cos(angle)]
    basis = np.column_stack(cols)
    j0 = names.index("sin1")
    curve = beta[:, j0 : j0 + 2 * HARMONICS] @ basis.T  # (draws, days)
    peak = days[np.argmax(curve, axis=1)]
    p2t = np.expm1(curve.max(axis=1) - curve.min(axis=1)) * 100
    return {
        "days": days,
        "curve": curve,
        "peak_day": peak,
        "peak_to_trough_pct": p2t,
    }


def scorecard(summary, season, trend) -> list:
    """The pre-registered predictions 2 to 9, each with the measured value and hit or miss."""
    c, h = summary["coefficients"], summary["hyper"]
    rows = []

    def add(n, claim, value, hit):
        rows.append({"n": n, "claim": claim, "value": value, "hit": bool(hit)})

    d2 = c["bed>=2"]["median"]
    add(2, "delta_2 is +25% to +45%", f"{d2:+.1f}%", 25 <= d2 <= 45)
    f2 = c["full>=2"]["median"]
    add(3, "phi_2 is +8% to +20%", f"{f2:+.1f}%", 8 <= f2 <= 20)
    ratio = h["half_over_full2"]["median"]
    add(4, "half bath is 0.3 to 0.6 of phi_2", f"{ratio:.2f}", 0.3 <= ratio <= 0.6)
    peak = float(np.median(season["peak_day"]))
    p2t = float(np.median(season["peak_to_trough_pct"]))
    month = (pd.Timestamp("2001-01-01") + pd.Timedelta(days=peak)).month
    add(
        5,
        "season peaks June to August, peak-to-trough 2% to 6%",
        f"peak day {peak:.0f} (month {month}), {p2t:.1f}%",
        6 <= month <= 8 and 2 <= p2t <= 6,
    )
    drop = trend["covid_drop_pct"]["median"]
    add(6, "2020 trough at least 10% below early 2020", f"{drop:.1f}%", drop <= -10)
    g = h["g_yearly_pct"]["median"]
    hm = h["h_months"]["median"]
    nt = h["nu_t"]["median"]
    add(
        7,
        "g +2% to +4% a year, h 6 to 24 months, nu_T < 4",
        f"g {g:+.2f}%/yr, h {hm:.1f} months, nu_T {nt:.2f}",
        2 <= g <= 4 and 6 <= hm <= 24 and nt < 4,
    )
    outside = trend["outside_covid"]
    add(
        8,
        "at most 2 of the 10 largest slope shocks outside Mar 2020 to Dec 2022",
        f"{outside} outside",
        outside <= 2,
    )
    nu = h["nu"]["median"]
    add(9, "residual nu < 3", f"{nu:.2f}", nu < 3)
    return rows


def trend_summary(kept: dict, start: pd.Timestamp, weeks: int) -> dict:
    """The trend's weekly medians and 95% bands, the 2020 drop, and the largest slope shocks."""
    L = kept["L"].reshape(-1, kept["L"].shape[-1])
    dates = start + pd.to_timedelta(np.arange(weeks + 1) * 7, unit="D")
    early = (dates >= "2020-01-01") & (dates < "2020-03-01")
    in2020_21 = (dates >= "2020-03-01") & (dates < "2021-07-01")
    out = {}
    if early.any() and in2020_21.any():
        base = L[:, early].mean(axis=1)
        trough = L[:, in2020_21].min(axis=1)
        drop = 100 * np.expm1(trough - base)
        lo, med, hi = np.quantile(drop, [0.025, 0.5, 0.975])
        out["covid_drop_pct"] = {"median": float(med), "lo": float(lo), "hi": float(hi)}
        tw = dates[in2020_21][np.argmin(np.median(L[:, in2020_21], axis=0))]
        out["trough_week"] = str(tw.date())
    eta = kept["eta"].reshape(-1, kept["eta"].shape[-1])
    tau = kept["tau"].reshape(-1)
    size = np.median(np.abs(eta) / tau[:, None], axis=0)  # shocks in units of tau
    top = np.argsort(size)[::-1][:10]
    # eta[j] is the shock to S_{j+1}, the slope out of grid point j+1.
    shock_dates = dates[top + 1]
    inside = (shock_dates >= "2020-03-01") & (shock_dates < "2023-01-01")
    out["shocks"] = [
        {"week": str(dt.date()), "size_tau": float(size[j]), "covid": bool(c)}
        for dt, j, c in zip(shock_dates, top, inside)
    ]
    out["outside_covid"] = int((~inside).sum())
    out["dates"] = [str(x.date()) for x in dates]
    out["L"] = np.quantile(L, [0.025, 0.5, 0.975], axis=0)
    return out


# ------------------------------------------------------------------ run and score entry points


def run_parser():
    p = argparse.ArgumentParser(prog="rentfrontier.run --model b0")
    p.add_argument("--split", choices=sorted(splits.SPLITS), required=True)
    p.add_argument("--model", default=NAME)
    p.add_argument("--name", required=True)
    p.add_argument("--chains", type=int)
    p.add_argument("--warmup", type=int)
    p.add_argument("--draws", type=int)
    p.add_argument("--keep-every", type=int)
    # ops/modal/fit.py passes it to every fit; B0 vectorizes all its chains at once.
    p.add_argument("--chain-batch", type=int)
    p.add_argument("--seed", type=int)
    p.add_argument("--tier", default="full", choices=("full", "exploration"))
    p.add_argument("--dev", action="store_true")
    return p


def main_run(argv) -> None:
    """`rentfrontier.run --model b0`: fit B0 on the split's training rows and save the run."""
    from . import run as runmod

    args, ignored = run_parser().parse_known_args(argv)
    commit = os.environ.get("FRONTIER_COMMIT")
    dirty = "" if commit else runmod.git("status", "--porcelain")
    commit = commit or runmod.git("rev-parse", "HEAD")
    if dirty and not args.dev:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    out_dir = runmod.RUNS / args.name
    if (out_dir / "result.json").exists():
        raise SystemExit(f"{out_dir} already has a result; choose a new --name")
    settings = Settings(
        **{
            k: v
            for k, v in {
                "chains": args.chains,
                "warmup": args.warmup,
                "draws": args.draws,
                "keep_every": args.keep_every,
                "seed": args.seed,
            }.items()
            if v is not None
        }
    )
    priors = Priors()
    started = time.time()
    t0 = time.perf_counter()
    frame = load_frame()
    heldout = splits.SPLITS[args.split](frame)
    full = design(frame)
    train = subset(full, ~heldout)
    test = subset(full, heldout)
    prep_seconds = time.perf_counter() - t0
    log_lines = []

    def log(msg):
        print(msg, flush=True)
        log_lines.append(msg)

    log(
        f"{args.name}: {args.split} split, {len(train.y)} training rows, "
        f"{len(test.y)} held out, {full.weeks} weeks from {full.start.date()}"
        + (f"; ignored {' '.join(ignored)}" if ignored else "")
    )
    out = run(train, priors, settings, log=log)
    diag = diagnostics(out["trace"], full.names)
    log(
        f"diagnostics: max R-hat {diag['max_rhat']:.4f} ({diag['max_rhat_name']}), "
        f"min ESS {diag['min_ess']:.0f} ({diag['min_ess_name']})"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    flat = {f"kept/{k}": v for k, v in out["kept"].items()}
    flat |= {f"trace/{k}": v for k, v in out["trace"].items()}
    flat["names"] = np.asarray(full.names)
    flat["heldout"] = heldout
    np.savez_compressed(out_dir / "posterior.npz", **flat)
    result = {
        "name": args.name,
        "reportable": not dirty,
        "commit": commit,
        "dirty": bool(dirty),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "dataset": frame.attrs["dataset"],
        "dataset_observations_sha256": frame.attrs["source_sha256"],
        "split": args.split,
        "split_seed": splits.SEED,
        "feature_set": NAME,
        "data_rules": [],
        "model": {"name": NAME, "priors": priors.to_dict()},
        "sampler": NAME,
        "line": "baseline",
        "tier": args.tier,
        "sampler_settings": settings.to_dict(),
        "sizes": {
            "train": len(train.y),
            "heldout": len(test.y),
            "weeks": full.weeks,
            "coefficients": len(full.names),
        },
        "grid_start": str(full.start.date()),
        "counts": full.count,
        "hardware": runmod.hardware(),
        "seconds": {"prepare": prep_seconds, **out["seconds"]},
        "cost_usd": None,
        "diagnostics": diag,
        "log": log_lines,
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"wrote {out_dir}")


def diagnostics(trace: dict, names) -> dict:
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    quantities = {f"beta[{n}]": trace["beta"][..., j] for j, n in enumerate(names)}
    quantities |= {k: trace[k] for k in ("g", "nu", "h", "tau", "nu_t")}
    quantities |= {f"sigma[{i}]": trace["sigma"][..., i] for i in range(4)}
    rows = {
        n: {"rhat": split_rhat(np.asarray(x)), "ess": ess(np.asarray(x))}
        for n, x in quantities.items()
        if np.ptp(x) > 0
    }
    worst = max(rows, key=lambda n: rows[n]["rhat"])
    least = min(rows, key=lambda n: rows[n]["ess"])
    return {
        "per_quantity": rows,
        "max_rhat": rows[worst]["rhat"],
        "max_rhat_name": worst,
        "min_ess": rows[least]["ess"],
        "min_ess_name": least,
        "passes": rows[worst]["rhat"] <= RHAT_GATE and rows[least]["ess"] > ESS_GATE,
    }


def score(name: str) -> tuple[dict, dict]:
    """PSIS-LOO over the run's training rows, and the held-out rows' predictive medians,
    intervals and coverage, as `rentfrontier.loo` writes them: (record, pointwise arrays)."""
    from . import clusterse, loo
    from . import run as runmod

    rdir = runmod.RUNS / name
    result = json.loads((rdir / "result.json").read_text())
    post = np.load(rdir / "posterior.npz")
    kept = {k.split("/", 1)[1]: post[k] for k in post.files if k.startswith("kept/")}
    names = [str(n) for n in post["names"]]
    heldout = post["heldout"]
    frame = load_frame(result["dataset"])
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("the dataset changed since the run")
    full = design(frame, pd.Timestamp(result["grid_start"]))
    train, test = subset(full, ~heldout), subset(full, heldout)
    t0 = time.perf_counter()
    elpd, k, mcse, lp = [], [], [], []
    for lo in range(0, len(train.y), LOO_BLOCK):
        ll = loglik_rows(train, kept, lo, min(lo + LOO_BLOCK, len(train.y)))
        e, kk, m = loo.psis_loo(ll)
        elpd.append(e)
        k.append(kk)
        mcse.append(m)
        lp.append(loo.lppd(ll))
    elpd, k, mcse, lp = map(np.concatenate, (elpd, k, mcse, lp))
    n = len(elpd)
    draws = int(kept["nu"].size)
    threshold = loo.k_threshold(draws)
    buildings = frame.building.astype(str).to_numpy()[~heldout]
    record = {
        "run": name,
        "model": NAME,
        "elpd_loo": float(elpd.sum()),
        "elpd_loo_se": float(elpd.std(ddof=1) * math.sqrt(n)),
        "elpd_loo_building_se": clusterse.cluster_se(elpd, buildings),
        "elpd_loo_mcse": float(math.sqrt(np.sum(mcse**2))),
        "p_loo": float(lp.sum() - elpd.sum()),
        "rows": n,
        "draws": draws,
        "pareto_k": {
            "threshold": threshold,
            "max": float(k.max()),
            "over_0.7": int((k > 0.7).sum()),
            "over_threshold": int((k > threshold).sum()),
        },
        "loo_seconds": time.perf_counter() - t0,
    }
    t0 = time.perf_counter()
    pred = predictive(test, kept)
    ll_test = [
        loo.lppd(loglik_rows(test, kept, lo, min(lo + LOO_BLOCK, len(test.y))))
        for lo in range(0, len(test.y), LOO_BLOCK)
    ]
    record["heldout"] = coverage(test, pred) | {
        "elpd": float(np.concatenate(ll_test).sum()) if ll_test else None
    }
    record["heldout_seconds"] = time.perf_counter() - t0
    summary = summarize(kept, names)
    season = season_curve(kept, names)
    trend = trend_summary(kept, full.start, full.weeks)
    record["summary"] = summary
    record["season"] = {
        "peak_day_median": float(np.median(season["peak_day"])),
        "peak_to_trough_pct": {
            "median": float(np.median(season["peak_to_trough_pct"])),
            "lo": float(np.quantile(season["peak_to_trough_pct"], 0.025)),
            "hi": float(np.quantile(season["peak_to_trough_pct"], 0.975)),
        },
    }
    record["trend"] = {k: v for k, v in trend.items() if k not in ("dates", "L")}
    record["scorecard"] = scorecard(summary, season, trend)
    record["descriptive_share"] = 0.0
    pointwise = dict(
        audit_id=frame.audit_id.to_numpy()[~heldout].astype(str),
        elpd_loo=elpd,
        pareto_k=k,
        heldout_audit_id=frame.audit_id.to_numpy()[heldout].astype(str),
        heldout_quantiles=pred["values"],
        heldout_y=test.y,
        trend_dates=np.asarray(trend["dates"]),
        trend_L=trend["L"],
        season_days=season["days"],
        season_curve=np.quantile(season["curve"], [0.025, 0.5, 0.975], axis=0),
    )
    return record, pointwise


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("prior", help="prior predictive check")
    pp.add_argument("dataset", type=Path)
    pp.add_argument("--rows", type=int, default=50_000)
    pp.add_argument("--draws", type=int, default=200)
    args = p.parse_args(argv)
    if args.cmd == "prior":
        frame = load_frame(args.dataset)
        print(
            json.dumps(
                prior_predictive(design(frame), Priors(), args.draws, args.rows),
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
