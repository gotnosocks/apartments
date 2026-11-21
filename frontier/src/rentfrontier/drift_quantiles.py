"""Quantiles of a drift fit's predictive mixtures by inverting the cdf, with no sampling.

`rentfrontier.drift_score` and `rentfrontier.drift_today` describe a row's predictive
distribution as an equal-weight mixture over components (kept draws, or kept sweeps of
kept draws), where given component d the row's log rent is

    y = loc_d + usd_d z + sigma_d t,   z ~ Normal(0, 1),  t ~ StudentT(nu_d).

The sum of a Normal and a Student-t has no closed-form cdf. `drift_score` writes the
Student-t as a scale mixture of Normals and integrates its mixing scale on a fixed grid
(`drift_score.mixture`), which makes each component a mixture of `NODES` Normals and the
row's cdf

    F(y) = mean_d sum_k w_dk Phi((y - loc_d) / sqrt(usd_d^2 + sigma_d^2 / lam_dk)),

the `cdf` the Deals table's `below_share` is. `cdf` evaluates F with the same grid and
`exact` solves F(q) = p for q, so its quantiles agree with `below_share` and carry no seed.

The solver. F is smooth and increasing, and its probit g(y) = Phi^-1(F(y)) is close to a
line, so each quantile is found by Newton's method on g, kept inside a bracket: every
evaluation of a row's F, for any of its levels, narrows the bracket of each of the row's
levels, and a step that would leave its bracket is replaced by the bracket's midpoint, a
bisection step. A level is done once it has taken a Newton step shorter than `TOL`.
Newton's error after a step is of the order of the step squared, so the error left is far
below 1e-6: on the served run's ads the quantiles are within 1e-9 of the ones a tolerance
of 1e-12 gives. A level takes about three evaluations of F.

The quadrature. With `drift_score.NODES` nodes the quantiles are within 2e-9 in log rent
of the ones 768 nodes give, so the grid's error is far below the tolerance too.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
from scipy.special import ndtr, ndtri

from . import drift_score

# A quantile is done when it has taken a Newton step shorter than this, in log rent, or
# its bracket is a tenth as wide. The error after such a step is of the order of TOL squared.
TOL = 1e-5
# Evaluations of a level before the solver gives up. Bisection alone halves a bracket a
# few log units wide to TOL in about 30.
MAX_ITER = 80
# Elements of a block's (components, rows, nodes) work arrays, of which about four are
# held at once by each thread: 5e5 doubles are 4 MB, which stays in a core's cache. Blocks
# of 8e6 took a fifth longer.
BLOCK_ELEMENTS = 500_000
# The levels of `quantiles`: `drift_score.Q` and the median.
LEVELS = (*drift_score.Q, 0.5)


def _evaluate(x, loc, isd, w):
    """The mixture's cdf and density at `x` (rows,): `loc` (components, rows), `isd`
    (components, rows, nodes) one over each Normal's sd, `w` (components, nodes)."""
    z = x[None, :, None] - loc[:, :, None]
    z = z * isd
    n = loc.shape[0]
    cdf = np.einsum("drk,dk->r", ndtr(z), w) / n
    np.square(z, out=z)
    z *= -0.5
    np.exp(z, out=z)
    z *= isd
    return cdf, np.einsum("drk,dk->r", z, w) / (n * np.sqrt(2 * np.pi))


def _inverse_sd(usd, sigma, inv_lam):
    """One over the sd of each Normal: (components, rows, nodes)."""
    var = (sigma * sigma)[:, :, None] * inv_lam[:, None, :]
    var += (usd * usd)[:, :, None]
    np.sqrt(var, out=var)
    return np.reciprocal(var, out=var)


def _grid(nu, nodes):
    lam, logw = drift_score.mixture(nu, nodes)
    return 1.0 / lam, np.exp(logw)


def _block(loc, nodes: int) -> int:
    return max(1, BLOCK_ELEMENTS // (loc.shape[0] * nodes))


def cdf(y, loc, usd, sigma, nu, nodes: int = drift_score.NODES) -> np.ndarray:
    """The predictive probability of a log rent below `y` (rows,) or (rows, levels), as
    `drift_score.score_rows` gives it: `loc`, `usd` and `sigma` (components, rows), `nu`
    (components,)."""
    loc, usd, sigma = (np.asarray(v, float) for v in (loc, usd, sigma))
    y = np.asarray(y, float)
    cols = y.reshape(len(y), -1)
    inv_lam, w = _grid(nu, nodes)
    out = np.empty(cols.shape)
    step = _block(loc, nodes)
    for a in range(0, cols.shape[0], step):
        sl = slice(a, a + step)
        isd = _inverse_sd(usd[:, sl], sigma[:, sl], inv_lam)
        for j in range(cols.shape[1]):
            out[sl, j] = _evaluate(cols[sl, j], loc[:, sl], isd, w)[0]
    return out.reshape(y.shape)


def _solve(loc, usd, sigma, inv_lam, w, p, tol, max_iter):
    """`exact` for one block of rows."""
    rows, levels = loc.shape[1], len(p)
    zp = ndtri(p)
    # The start: each level's place in a Normal with the mixture's mean and a spread from
    # the components' locations and their two scales.
    centre = loc.mean(axis=0)
    spread = np.sqrt(loc.var(axis=0) + (usd * usd + sigma * sigma).mean(axis=0))
    isd = _inverse_sd(usd, sigma, inv_lam)
    x = centre[:, None] + spread[:, None] * zp[None, :]
    lo = np.full((rows, levels), -np.inf)
    hi = np.full((rows, levels), np.inf)
    active = np.ones((rows, levels), bool)
    for _ in range(max_iter):
        for j in range(levels):
            at = np.flatnonzero(active[:, j])
            if not len(at):
                continue
            xj = x[at, j]
            whole = len(at) == rows
            F, f = _evaluate(
                xj, loc if whole else loc[:, at], isd if whole else isd[:, at], w
            )
            # The point bounds every level of its row from one side.
            below = F[:, None] < p[None, :]
            above = F[:, None] > p[None, :]
            lo[at] = np.where(below, np.maximum(lo[at], xj[:, None]), lo[at])
            hi[at] = np.where(above, np.minimum(hi[at], xj[:, None]), hi[at])
            with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
                g = ndtri(F)
                slope = f * np.sqrt(2 * np.pi) * np.exp(0.5 * g * g)
                step = (zp[j] - g) / slope
            new = xj + step
            a, b = lo[at, j], hi[at, j]
            inside = np.isfinite(new) & (new >= a) & (new <= b)
            both = np.isfinite(a) & np.isfinite(b)
            # Where F is 0 or 1 to machine precision and one side is still open, walk
            # towards the centre by the row's spread.
            walk = np.where(np.isfinite(a), a + spread[at], b - spread[at])
            new = np.where(inside, new, np.where(both, 0.5 * (a + b), walk))
            done = (inside & (np.abs(step) < tol)) | (both & (b - a < 0.1 * tol))
            done |= F == p[j]
            x[at, j] = np.where(F == p[j], xj, new)
            active[at[done], j] = False
        if not active.any():
            return x
    raise RuntimeError(
        f"{int(active.sum())} quantiles did not converge in {max_iter} evaluations"
    )


def exact(
    loc,
    usd,
    sigma,
    nu,
    p=LEVELS,
    nodes: int = drift_score.NODES,
    tol: float = TOL,
    max_iter: int = MAX_ITER,
    workers: int = 1,
) -> np.ndarray:
    """The predictive quantiles at the levels `p` of rows whose components are
    (`loc`, `usd`, `sigma`), each (components, rows), with noise degrees of freedom `nu`
    (components,): (rows, len(p)). They solve `cdf`(q) = p, each to well within 1e-6 in
    log rent at the default `tol`. The rows are worked in blocks of `BLOCK_ELEMENTS`
    work-array elements, on `workers` threads. The threads change nothing, and the
    blocks only the order of the sums: a row's quantile moves by about 1e-14 with them."""
    loc, usd, sigma = (np.asarray(v, float) for v in (loc, usd, sigma))
    p = np.asarray(p, float)
    if not ((p > 0) & (p < 1)).all():
        raise ValueError("the levels lie strictly between 0 and 1")
    inv_lam, w = _grid(nu, nodes)
    step = _block(loc, nodes)

    def block(a):
        sl = slice(a, a + step)
        return _solve(
            loc[:, sl], usd[:, sl], sigma[:, sl], inv_lam, w, p, tol, max_iter
        )

    starts = range(0, loc.shape[1], step)
    if workers > 1:
        with ThreadPoolExecutor(workers) as pool:
            parts = list(pool.map(block, starts))
    else:
        parts = [block(a) for a in starts]
    return np.concatenate(parts) if parts else np.empty((0, len(p)))


def quantiles(loc, usd, sigma, nu, nodes: int = drift_score.NODES, workers: int = 1):
    """The exact quantiles at `drift_score.Q`, (rows, len(Q)), and the exact median,
    (rows,): what `drift_today.quantiles` and `drift_score.score_rows` sample."""
    q = exact(loc, usd, sigma, nu, LEVELS, nodes, workers=workers)
    return q[:, :-1], q[:, -1]
