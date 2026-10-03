"""Structured blocked Gibbs sampler for the model in `model.build_model`.

Scope: designs that are conditionally Gaussian given the Student-t mixing
weights and the scales, with every unit nested in one building.
`run.py --sampler gibbs` fits a design with it; `build_design` refuses the
rest: terms it has no exact update for (market drift, building trends,
Student-t or sum-to-zero walks, walk masks and anchors, line effects),
designs without every base term (trend, season, features, buildings, units),
and data where a unit's rows sit in more than one building.

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

import itertools
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
    # (walk_scale, walk) rescaling moves per iteration: no block solve, so
    # cheap; their step size adapts during warmup (target acceptance 0.44).
    rescale_steps: int = 20
    rescale_step_sd: float = 0.01  # on log c (initial)
    trace_groups: int = 32
    # Collapsed Metropolis update of all group scales (latents integrated
    # out); proposal sd = collapse_scale * sd(log scale) / sqrt(#scales),
    # sized from the first half of warmup.
    collapse: bool = True
    collapse_scale: float = 2.38
    # Joint collapsed proposal along the log-scales' warmup covariance
    # (Cholesky factor) instead of independent per-scale steps: correlated
    # scales (walk, unit, noise) then move together.
    collapse_cov: bool = True
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
    fslope_local: list  # local indices of per-building feature slopes
    fslope_cols: list  # their feature columns
    knot_start: int | None  # local index of walk knot 1 (knot 0 is fixed at 0)
    walk_months: int  # months between walk knots
    n_features: int
    n_months: int
    n_units: int
    n_buildings: int
    n_local: int
    prior_sd: dict
    nu_fixed: float | None = None
    unit_t: bool = False
    unit_nu_fixed: float | None = None
    unit_drift: bool = False
    unit_time: jnp.ndarray | None = None
    # a'Wa by structure: every global column except the features is a
    # function of the row's (bedroom group, month) key, so the Gram matrix is
    # a dense feature block plus per-key sums through a small basis.
    gram_key: jnp.ndarray | None = None  # (N,) key per row
    gram_n_keys: int = 0
    gram_basis: jnp.ndarray | None = None  # (keys, keyed columns)
    gram_feat: jnp.ndarray | None = None  # (N, F) feature columns of a
    gram_fcols: np.ndarray | None = None
    gram_kcols: np.ndarray | None = None
    # Walk knots no row touches are integrated out (`compact_walk`): each
    # building's block holds its fixed slots and the knots its rows touch,
    # in buckets of buildings with similar counts; `fill` redraws the rest.
    buckets: tuple = ()
    fill: dict | None = None
    walk_rank: int = 0  # touched knots over all buildings (the walk's rank)
    # (12, 2K) Fourier basis of the season (`season_harmonics`); None for 12
    # month effects.
    season_basis: jnp.ndarray | None = None

    @property
    def scale_names(self):
        drift = ("unit_drift_scale",) if self.unit_drift else ()
        return (
            "sigma",
            "unit_scale",
            *drift,
            *self.global_blocks,
            *self.local_structures,
        )


def _rw1_anchored(n):
    d = np.diff(np.eye(n + 1), axis=0)[:, 1:]  # steps from a fixed 0
    return d.T @ d


@dataclass
class Bucket:
    """Buildings whose blocks share one compact width."""

    buildings: jnp.ndarray  # (K_b,) building ids
    rows: jnp.ndarray  # (n_b,) their training rows
    bld: jnp.ndarray  # (n_b,) row -> index within the bucket
    slots: jnp.ndarray  # (n_b, S) compact slots
    values: jnp.ndarray  # (n_b, S)
    units: jnp.ndarray  # (J_b,) unit ids
    unit: jnp.ndarray  # (n_b,) row -> unit index within the bucket
    width: int  # compact block size
    walk: jnp.ndarray  # (K_b, width, width) walk precision over touched knots
    pad: jnp.ndarray  # (K_b, width) 1 on unused slots (a fixed unit prior)
    knot: jnp.ndarray  # (K_b, width - n_fixed) knot of each walk slot (k: unused)


# At most this many compact widths: one batched elimination per bucket.
MAX_BUCKETS = 4


def _bucket_widths(sizes, max_buckets=MAX_BUCKETS):
    """Widths (largest touched-knot count per bucket) minimising the summed
    block size: the cost of the global Schur product is linear in it."""
    distinct = np.unique(sizes)
    count = np.array([(sizes == v).sum() for v in distinct])
    best = (np.inf, None)
    top = len(distinct) - 1
    for cuts in itertools.combinations(range(top), min(max_buckets, len(distinct)) - 1):
        ends = [*cuts, top]
        cost, lo = 0.0, 0
        for e in ends:
            cost += count[lo : e + 1].sum() * distinct[e]
            lo = e + 1
        best = min(best, (cost, tuple(distinct[e] for e in ends)), key=lambda t: t[0])
    return best[1]


def compact_walk(
    slots,
    values,
    building,
    unit,
    unit_building,
    n_buildings,
    n_units,
    knot_start,
    n_local,
    max_buckets=MAX_BUCKETS,
):
    """Buckets and fill rules that integrate out the walk knots no row touches.

    Under the anchored RW1 prior a building's touched knots t_1 < ... < t_m
    (knot 0 fixed at 0) have independent steps x_{t_i} - x_{t_{i-1}} with
    variance walk_scale^2 (t_i - t_{i-1}). The other knots enter no
    likelihood term. Given the touched knots they are a random-walk bridge
    between their neighbours, or a free walk after the last one, and `fill`
    holds what draws them: the left and right touched knot of every knot and
    its interpolation weight.
    """
    n_fixed, k = knot_start, n_local - knot_start + 1  # knots 0..k-1
    walk_cols = slice(slots.shape[1] - 2, slots.shape[1])
    touched = np.zeros((n_buildings, k), bool)
    touched[building[:, None], slots[:, walk_cols] - knot_start + 1] = True
    touched[:, 0] = False  # the fixed anchor is not a variable
    sizes = touched.sum(1)
    widths = _bucket_widths(sizes, max_buckets)
    knots = np.arange(k)
    # Left and right touched (or anchor) knot of every knot, and the weight.
    left = np.zeros((n_buildings, k), np.int32)
    right = np.zeros((n_buildings, k), np.int32)
    alpha = np.zeros((n_buildings, k))
    for b in range(n_buildings):
        t = np.r_[0, np.flatnonzero(touched[b])]
        li = np.searchsorted(t, knots, side="right") - 1
        left[b] = t[li]
        has_right = li + 1 < len(t)
        r = np.where(has_right, t[np.minimum(li + 1, len(t) - 1)], t[li])
        right[b] = r
        gap = r - left[b]
        alpha[b] = np.where(gap > 0, (knots - left[b]) / np.maximum(gap, 1), 0.0)
    buckets, lo = [], -1
    order = np.argsort(sizes, kind="stable")
    for wmax in widths:
        members = order[(sizes[order] > lo) & (sizes[order] <= wmax)]
        lo = wmax
        if len(members) == 0:
            continue
        width = n_fixed + int(wmax)
        index = np.full(n_buildings, -1)
        index[members] = np.arange(len(members))
        rows = np.flatnonzero(index[building] >= 0)
        pos = np.full((n_buildings, k), -1)
        walk = np.zeros((len(members), width, width))
        pad = np.zeros((len(members), width))
        knot = np.full((len(members), width - n_fixed), k)
        for i, b in enumerate(members):
            t = np.flatnonzero(touched[b])
            pos[b, t] = n_fixed + np.arange(len(t))
            knot[i, : len(t)] = t
            steps = np.diff(np.r_[0, t])
            diff = np.eye(len(t)) - np.eye(len(t), k=-1)  # x_t_i - x_t_(i-1)
            walk[i, n_fixed : n_fixed + len(t), n_fixed : n_fixed + len(t)] = (
                diff.T @ np.diag(1.0 / steps) @ diff
            )
            pad[i, n_fixed + len(t) :] = 1.0
        cs = slots[rows].copy()
        cs[:, walk_cols] = pos[
            building[rows][:, None], slots[rows, walk_cols] - knot_start + 1
        ]
        units = np.flatnonzero(index[unit_building] >= 0)
        uidx = np.full(n_units, -1)
        uidx[units] = np.arange(len(units))
        buckets.append(
            Bucket(
                buildings=jnp.asarray(members, jnp.int32),
                rows=jnp.asarray(rows, jnp.int32),
                bld=jnp.asarray(index[building[rows]], jnp.int32),
                slots=jnp.asarray(cs, jnp.int32),
                values=jnp.asarray(values[rows]),
                units=jnp.asarray(units, jnp.int32),
                unit=jnp.asarray(uidx[unit[rows]], jnp.int32),
                width=width,
                walk=jnp.asarray(walk),
                pad=jnp.asarray(pad),
                knot=jnp.asarray(knot, jnp.int32),
            )
        )
    fill = {
        "left": jnp.asarray(left),
        "right": jnp.asarray(right),
        "alpha": jnp.asarray(alpha),
    }
    return tuple(buckets), fill, int(sizes.sum())


def fill_walk(d: Design, x_touched, scale, z_f=None):
    """The full walk (K, k) from its touched knots (K, k: other knots 0), with
    every other knot drawn given them (`compact_walk`): x_j = x_l + a (x_r - x_l)
    + scale (B_j - B_l - a (B_r - B_l)) for a free standard walk B."""
    f = d.fill
    rows = jnp.arange(x_touched.shape[0])[:, None]
    xl, xr = x_touched[rows, f["left"]], x_touched[rows, f["right"]]
    x = xl + f["alpha"] * (xr - xl)
    if z_f is not None:
        walk = jnp.concatenate(
            [jnp.zeros((z_f.shape[0], 1)), jnp.cumsum(z_f[:, 1:], axis=1)], axis=1
        )
        bl, br = walk[rows, f["left"]], walk[rows, f["right"]]
        x = x + scale * (walk - bl - f["alpha"] * (br - bl))
    return x


def build_design(
    prep: model_module.Prepared,
    config: model_module.ModelConfig,
    compact: bool = True,
) -> Design:
    base = ("trend", "season", "features", "buildings", "units")
    if (
        not all(getattr(config, t) for t in base)
        or config.market_drift
        or config.building_trend
        or config.walk_t
        or config.walk_min_rows_per_knot
        or config.walk_anchor_data
        or config.line_effects
        or config.walk_zero_sum
    ):
        raise ValueError(
            f"{config.name}: the Gibbs sampler needs every base term and no market "
            "drift, building trend, line effects or walk options (t steps, "
            "mask, anchor, zero-sum); "
            "fit these designs with --sampler nuts"
        )
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
    n_season = 2 * config.season_harmonics if config.season_harmonics else 12
    season = slice(trend.stop, trend.stop + n_season)
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
    if config.season_harmonics:
        # Fourier season: the basis at the row's calendar month (centred).
        a[:, season] = model_module.season_basis(config.season_harmonics)[tr.calendar]
    else:
        # Season enters as season_raw - mean(season_raw), as in the NumPyro model.
        a[:, season] = -1.0 / 12
        a[np.arange(n), season.start + tr.calendar] += 1.0
    blocks = {
        "trend_scale": (trend, _rw1_anchored(nt)),
        "season_scale": (
            season,
            np.diag(model_module.season_shrink(config.season_harmonics) ** 2)
            if config.season_harmonics
            else np.eye(12),
        ),
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
    # Keyed columns (all but the features) as a function of (bed group, month).
    gram_n_keys = 4 * t
    gram_key = np.minimum(tr.bed_group, 3) * t + tr.month
    fcols = np.arange(1, 1 + f)
    kcols = np.setdiff1d(np.arange(p), fcols)
    gram_basis = np.zeros((gram_n_keys, len(kcols)))
    gram_basis[gram_key] = a[:, kcols]
    if not np.array_equal(gram_basis[gram_key], a[:, kcols]):
        raise AssertionError("keyed global columns are not a function of the key")
    fixed = np.zeros(p)
    fixed[0] = 1.0
    fixed[1 : 1 + f] = 1.0 / (config.beta_sd * prep.features.prior_scale) ** 2
    unit_building = np.zeros(len(prep.units), dtype=np.int32)
    unit_building[tr.unit] = tr.building
    if not np.array_equal(unit_building[tr.unit], tr.building):
        raise ValueError(
            "the Gibbs sampler needs every unit nested in one building; "
            "some units have rows in more than one building"
        )

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
    fslope_local = []
    fslope_cols = [prep.features.names.index(nm) for nm in config.feature_slopes]
    for i, col in enumerate(fslope_cols):
        fslope_local.append(n_local)
        columns.append((np.full(n, n_local, np.int32), tr.x[:, col].astype(float)))
        structures[f"fslope_scale_{i}"] = [n_local]
        n_local += 1
    if config.building_walk:
        # Knots every config.walk_knot_months months (6 up to m8; coarser knots
        # leave fewer knots that a lone row pins).
        k = model_module.n_knots(t, config.walk_knot_months)
        knot_start = n_local
        lo, frac = (
            np.asarray(v)
            for v in model_module.walk_position(tr, config.walk_knot_months)
        )
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
    buckets, fill, walk_rank = (), None, 0
    if compact and config.building_walk and not config.unit_drift:
        buckets, fill, walk_rank = compact_walk(
            slots,
            values,
            tr.building,
            tr.unit,
            unit_building,
            len(prep.buildings),
            len(prep.units),
            knot_start,
            n_local,
        )

    prior_sd = {
        "sigma": config.noise_scale_sd,
        "unit_scale": config.unit_scale_sd,
        "building_scale": config.building_scale_sd,
        "trend_scale": config.trend_scale_sd,
        "season_scale": config.season_scale_sd,
        "walk_scale": config.walk_scale_sd,
        "bedroom_time_scale": config.bedroom_time_scale_sd,
        "bedroom_slope_scale": config.bedroom_slope_scale_sd,
        "unit_drift_scale": config.unit_drift_scale_sd,
        **{
            f"fslope_scale_{i}": config.feature_slope_scale_sd
            for i in range(len(fslope_cols))
        },
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
        season_basis=jnp.asarray(model_module.season_basis(config.season_harmonics))
        if config.season_harmonics
        else None,
        bedroom_time=bedroom_time,
        trend_basis=jnp.asarray(trend_basis),
        bedroom_time_basis=jnp.asarray(bed_basis),
        slope_index=slope_index,
        fslope_local=fslope_local,
        fslope_cols=fslope_cols,
        knot_start=knot_start,
        walk_months=config.walk_knot_months,
        n_features=f,
        n_months=t,
        n_units=len(prep.units),
        n_buildings=len(prep.buildings),
        n_local=n_local,
        prior_sd=prior_sd,
        nu_fixed=config.nu_fixed,
        unit_t=config.unit_t,
        unit_nu_fixed=config.unit_nu_fixed,
        unit_drift=config.unit_drift,
        unit_time=jnp.asarray(tr.unit_time, jnp.float64),
        gram_key=jnp.asarray(gram_key, jnp.int32),
        gram_n_keys=gram_n_keys,
        gram_basis=jnp.asarray(gram_basis),
        gram_feat=jnp.asarray(a[:, fcols]),
        gram_fcols=fcols,
        gram_kcols=kcols,
        buckets=buckets,
        fill=fill,
        walk_rank=walk_rank,
    )


def gram(d: Design, w):
    """a' diag(w) a, from the feature block and per-key sums (exact)."""
    feat, e = d.gram_feat, d.gram_basis
    wf = w[:, None] * feat
    m = jax.ops.segment_sum(wf, d.gram_key, d.gram_n_keys)  # (keys, F)
    wk = jax.ops.segment_sum(w, d.gram_key, d.gram_n_keys)
    ff = feat.T @ wf
    fk = m.T @ e
    kk = e.T @ (wk[:, None] * e)
    p = d.a.shape[1]
    q = jnp.zeros((p, p))
    fc, kc = jnp.asarray(d.gram_fcols), jnp.asarray(d.gram_kcols)
    q = q.at[fc[:, None], fc[None, :]].set(ff)
    q = q.at[fc[:, None], kc[None, :]].set(fk)
    q = q.at[kc[:, None], fc[None, :]].set(fk.T)
    q = q.at[kc[:, None], kc[None, :]].set(kk)
    return q


def _update_scale(key, current, q, rank, prior_sd):
    """tau | x for x ~ N(0, tau^2 R^-1) with rank(R) = rank, half-normal prior."""
    k1, k2 = jax.random.split(key)
    proposal = jnp.sqrt((q / 2) / jax.random.gamma(k1, (rank - 1) / 2))
    log_accept = -(proposal**2 - current**2) / (2 * prior_sd**2)
    return jnp.where(jnp.log(jax.random.uniform(k2)) < log_accept, proposal, current)


def local_value(theta_l, building, slots, values):
    return jnp.sum(theta_l[building[:, None], slots] * values, axis=1)


# The scales `block_parts` reads. The rest (the global and local prior scales)
# enter only `block_solve`, so a proposal that changes only those reuses the
# parts: the row sums over every row, about half of a block draw's cost.
PART_SCALES = frozenset({"sigma", "unit_scale", "unit_drift_scale"})


def gaussian_block(d: Design, lam, s, z_g, z_l, z_u, kappa=None, z_f=None):
    """Joint draw of (global, building blocks, units) given lam and scales `s`.

    With zero noise vectors it returns the conditional posterior mean.
    """
    return block_solve(d, block_parts(d, lam, s, kappa), s, z_g, z_l, z_u, z_f)


def block_parts(d: Design, lam, s, kappa=None) -> dict:
    """The precision and right-hand-side sums of `gaussian_block` before the
    prior scales outside PART_SCALES are added: the units integrated out and
    the building cells summed over rows."""
    J, K, L = d.n_units, d.n_buildings, d.n_local
    y, a, bld, slots, vals = d.y, d.a, d.building, d.slots, d.slot_values
    n_slots = slots.shape[1]
    w = lam / s["sigma"] ** 2
    seg_u = lambda v: jax.ops.segment_sum(v, d.unit, J)
    sw = seg_u(w)
    # Unit prior precision kappa_j / unit_scale^2 (kappa = 1: Gaussian units;
    # Student-t units are a Gamma scale mixture over kappa).
    kappa = jnp.ones(J) if kappa is None else kappa
    wa = w[:, None] * a
    n = a.shape[0]
    if d.buckets and not d.unit_drift:
        return _compact_parts(d, w, kappa, s)
    a_l = jnp.zeros((n, L)).at[jnp.arange(n)[:, None], slots].add(vals)
    if d.unit_drift:
        # Unit block [level, drift]: z_i = (1, t_i), t_i in years from the
        # unit's mean training date. Per-unit 2x2 precision
        # M_j = sum_i w_i z_i z_i' + diag(kappa_j / tau^2, 1 / tau_d^2).
        zr = jnp.stack([jnp.ones(n), d.unit_time], axis=1)
        wz = w[:, None] * zr
        m2 = seg_u(wz[:, :, None] * zr[:, None, :])
        m2 = m2.at[:, 0, 0].add(kappa / s["unit_scale"] ** 2)
        m2 = m2.at[:, 1, 1].add(1.0 / s["unit_drift_scale"] ** 2)
        det = m2[:, 0, 0] * m2[:, 1, 1] - m2[:, 0, 1] * m2[:, 1, 0]
        cu = (
            jnp.stack(
                [
                    jnp.stack([m2[:, 1, 1], -m2[:, 0, 1]], axis=1),
                    jnp.stack([-m2[:, 1, 0], m2[:, 0, 0]], axis=1),
                ],
                axis=1,
            )
            / det[:, None, None]
        )  # (J, 2, 2) unit posterior covariance given the rest
        hu = seg_u(wz * y[:, None])  # (J, 2)
        gu = seg_u(wz[:, :, None] * a[:, None, :])  # (J, 2, P)
        glu = jnp.zeros((J, 2, L))
        for k_ in range(2):
            for m in range(n_slots):
                glu = glu.at[d.unit, k_, slots[:, m]].add(wz[:, k_] * vals[:, m])
        cg = jnp.einsum("jkl,jlp->jkp", cu, gu)
        ch = jnp.einsum("jkl,jl->jk", cu, hu)
        unit = {"wz": wz, "cu": cu, "hu": hu, "ch": ch, "det": det}
        q = gram(d, w) - jnp.einsum("jkp,jkq->pq", gu, cg) + jnp.diag(d.prior_fixed)
        rhs_g = wa.T @ y - jnp.einsum("jkp,jk->p", gu, ch)
        cgl = jnp.einsum("jkl,jlm->jkm", cu, glu)
        adj = a_l - jnp.einsum("ik,ikm->im", zr, cgl[d.unit])
        a_t = a - jnp.einsum("ik,ikp->ip", zr, cg[d.unit])
    else:
        c = 1.0 / (
            kappa / s["unit_scale"] ** 2 + sw
        )  # unit posterior variance given rest
        h = seg_u(w * y)
        g = seg_u(wa)  # (J, P) unit sums of weighted global rows
        gl = jnp.zeros((J, L))  # unit sums of weighted local rows
        for m in range(n_slots):
            gl = gl.at[d.unit, slots[:, m]].add(w * vals[:, m])
        q = gram(d, w) - g.T @ (c[:, None] * g) + jnp.diag(d.prior_fixed)
        rhs_g = wa.T @ y - g.T @ (c * h)
        adj = a_l - (c[:, None] * gl)[d.unit]
        a_t = a - (c[:, None] * g)[d.unit]
        unit = {"c": c, "h": h}

    # Building blocks, with units integrated out (units nest in buildings).
    # With adj_i = a_L,i - (unit correction) and a~_i = a_i - (unit
    # correction) the rows' local and global designs with their unit
    # integrated out,
    #   Q_ll[b] = sum_{i in b} w_i adj_i a_L,i^T = sum_{i in b} w_i a_L,i adj_i^T,
    #   Q_lg[b] = sum_{i in b} w_i adj_i a_i^T   = sum_{i in b} w_i a_L,i a~_i^T,
    # (the unit terms cancel the same way in both forms). a_L,i has only
    # n_slots non-zeros (building level, two walk knots, slopes), so each sum
    # is one segment sum per slot into (building, local index) cells instead
    # of one per local column.
    wadj = w[:, None] * adj
    seg_b = lambda v: jax.ops.segment_sum(v, bld, K)
    q_ll = jnp.zeros((K * L, L))
    q_lg = jnp.zeros((K * L, a.shape[1]))
    for m in range(n_slots):
        cell = bld * L + slots[:, m]
        wv = (w * vals[:, m])[:, None]
        q_ll = q_ll + jax.ops.segment_sum(wv * adj, cell, K * L)
        q_lg = q_lg + jax.ops.segment_sum(wv * a_t, cell, K * L)
    q_ll = q_ll.reshape(K, L, L)
    q_lg = q_lg.reshape(K, L, a.shape[1])
    q_ll = 0.5 * (q_ll + jnp.swapaxes(q_ll, 1, 2))
    r_l = seg_b(wadj * y[:, None])
    return {
        "w": w,
        "kappa": kappa,
        "q": q,
        "rhs_g": rhs_g,
        "q_ll": q_ll,
        "q_lg": q_lg,
        "r_l": r_l,
        **unit,
    }


def _compact_parts(d: Design, w, kappa, s) -> dict:
    """`block_parts` with the untouched walk knots integrated out: the building
    cells per bucket at its compact width (`compact_walk`)."""
    J = d.n_units
    y, a = d.y, d.a
    seg_u = lambda v: jax.ops.segment_sum(v, d.unit, J)
    c = 1.0 / (kappa / s["unit_scale"] ** 2 + seg_u(w))
    h = seg_u(w * y)
    wa = w[:, None] * a
    g = seg_u(wa)
    q = gram(d, w) - g.T @ (c[:, None] * g) + jnp.diag(d.prior_fixed)
    rhs_g = wa.T @ y - g.T @ (c * h)
    a_t = a - (c[:, None] * g)[d.unit]
    cells = []
    for bk in d.buckets:
        kb, width, nb = bk.buildings.shape[0], bk.width, bk.rows.shape[0]
        wb, yb, at_b = w[bk.rows], y[bk.rows], a_t[bk.rows]
        a_l = (
            jnp.zeros((nb, width)).at[jnp.arange(nb)[:, None], bk.slots].add(bk.values)
        )
        gl = jnp.zeros((bk.units.shape[0], width))
        for m in range(bk.slots.shape[1]):
            gl = gl.at[bk.unit, bk.slots[:, m]].add(wb * bk.values[:, m])
        adj = a_l - (c[bk.units][:, None] * gl)[bk.unit]
        q_ll = jnp.zeros((kb * width, width))
        q_lg = jnp.zeros((kb * width, a.shape[1]))
        for m in range(bk.slots.shape[1]):
            cell = bk.bld * width + bk.slots[:, m]
            wv = (wb * bk.values[:, m])[:, None]
            q_ll = q_ll + jax.ops.segment_sum(wv * adj, cell, kb * width)
            q_lg = q_lg + jax.ops.segment_sum(wv * at_b, cell, kb * width)
        q_ll = q_ll.reshape(kb, width, width)
        cells.append(
            {
                "q_ll": 0.5 * (q_ll + jnp.swapaxes(q_ll, 1, 2)),
                "q_lg": q_lg.reshape(kb, width, a.shape[1]),
                "r_l": jax.ops.segment_sum((wb * yb)[:, None] * adj, bk.bld, kb),
            }
        )
    return {
        "w": w,
        "kappa": kappa,
        "q": q,
        "rhs_g": rhs_g,
        "c": c,
        "h": h,
        "buckets": tuple(cells),
    }


def _compact_solve(d: Design, parts, s, q, rhs_g, z_g, z_l, z_f):
    """The building eliminations and draws per bucket, then the full walk
    (`fill_walk`). Returns theta, the full local block and its quad and
    log-determinant pieces."""
    n_fixed = d.knot_start
    k = d.n_local - n_fixed + 1
    shared = sum(
        d.local_structures[n] / s[n] ** 2
        for n in d.local_structures
        if n != "walk_scale"
    )
    schur, r_s, per = q, rhs_g, []
    quad_l = logdet_l = 0.0
    for bk, cell in zip(d.buckets, parts["buckets"]):
        width = bk.width
        prior = (
            shared[:width, :width][None]
            + bk.walk / s["walk_scale"] ** 2
            + jax.vmap(jnp.diag)(bk.pad)
        )
        chol_b = jnp.linalg.cholesky(cell["q_ll"] + prior)
        inv_b = solve_triangular(
            chol_b,
            jnp.broadcast_to(jnp.eye(width), (bk.buildings.shape[0], width, width)),
            lower=True,
        )
        v = inv_b @ cell["q_lg"]
        vr = solve_triangular(chol_b, cell["r_l"][..., None], lower=True)[..., 0]
        schur = schur - jnp.einsum("klp,klq->pq", v, v)
        r_s = r_s - jnp.einsum("klp,kl->p", v, vr)
        quad_l = quad_l + jnp.sum(vr * vr)
        logdet_l = logdet_l + 2 * jnp.sum(
            jnp.log(jnp.diagonal(chol_b, axis1=1, axis2=2))
        )
        per.append((chol_b, v, vr))
    chol = jnp.linalg.cholesky(schur)
    white = solve_triangular(chol, r_s, lower=True)
    theta = solve_triangular(chol.T, white + z_g, lower=False)
    fixed_l = jnp.zeros((d.n_buildings, n_fixed))
    x = jnp.zeros((d.n_buildings, k + 1))  # column k takes the unused slots
    for bk, (chol_b, v, vr) in zip(d.buckets, per):
        rhs = vr - jnp.einsum("klp,p->kl", v, theta) + z_l[bk.buildings, : bk.width]
        tc = solve_triangular(jnp.swapaxes(chol_b, 1, 2), rhs[..., None], lower=False)[
            ..., 0
        ]
        fixed_l = fixed_l.at[bk.buildings].set(tc[:, :n_fixed])
        x = x.at[bk.buildings[:, None], bk.knot].set(tc[:, n_fixed:])
    walk = fill_walk(d, x[:, :k], s["walk_scale"], z_f)
    theta_l = jnp.concatenate([fixed_l, walk[:, 1:]], axis=1)
    return (
        theta,
        theta_l,
        quad_l + jnp.sum(white * white),
        logdet_l + 2 * jnp.sum(jnp.log(jnp.diagonal(chol))),
    )


def block_solve(d: Design, parts: dict, s, z_g, z_l, z_u, z_f=None):
    """`gaussian_block` from its parts: adds the prior scales outside
    PART_SCALES, eliminates the building blocks, then the global block.
    `z_f` draws the walk knots no row touches (compact designs; None: their
    conditional mean)."""
    J, K = d.n_units, d.n_buildings
    y, a, bld, slots, vals = d.y, d.a, d.building, d.slots, d.slot_values
    w, kappa, q, rhs_g = parts["w"], parts["kappa"], parts["q"], parts["rhs_g"]
    L = d.n_local
    seg_u = lambda v: jax.ops.segment_sum(v, d.unit, J)

    # Global prior blocks.
    for name, (sl, r) in d.global_blocks.items():
        q = q.at[sl, sl].add(r / s[name] ** 2)
    if "buckets" in parts:
        theta, theta_l, quad_lg, logdet_lg = _compact_solve(
            d, parts, s, q, rhs_g, z_g, z_l, z_f
        )
    else:
        q_lg, r_l = parts["q_lg"], parts["r_l"]
        prior_l = sum(d.local_structures[n] / s[n] ** 2 for n in d.local_structures)
        q_ll = parts["q_ll"] + prior_l[None]

        # Eliminate building blocks (batched Cholesky), then the global block.
        chol_l = jnp.linalg.cholesky(q_ll)
        # L_k^-1 once per building (L columns), then one batched product:
        # cheaper than a triangular solve against all P global columns.
        inv_l = solve_triangular(
            chol_l, jnp.broadcast_to(jnp.eye(L), (K, L, L)), lower=True
        )
        v = inv_l @ q_lg  # (K, L, P)
        vr = solve_triangular(chol_l, r_l[..., None], lower=True)[..., 0]
        schur = q - jnp.einsum("klp,klq->pq", v, v)
        r_s = rhs_g - jnp.einsum("klp,kl->p", v, vr)
        chol = jnp.linalg.cholesky(schur)
        white = solve_triangular(chol, r_s, lower=True)
        theta = solve_triangular(chol.T, white + z_g, lower=False)
        rhs = vr - jnp.einsum("klp,p->kl", v, theta) + z_l
        theta_l = solve_triangular(
            jnp.swapaxes(chol_l, 1, 2), rhs[..., None], lower=False
        )[..., 0]
        quad_lg = jnp.sum(vr * vr) + jnp.sum(white * white)
        logdet_lg = 2 * jnp.sum(
            jnp.log(jnp.diagonal(chol_l, axis1=1, axis2=2))
        ) + 2 * jnp.sum(jnp.log(jnp.diagonal(chol)))
    fixed = a @ theta + local_value(theta_l, bld, slots, vals)
    if d.unit_drift:
        wz, cu, hu, ch, det = (parts[k] for k in ("wz", "cu", "hu", "ch", "det"))
        mean_u = jnp.einsum("jkl,jl->jk", cu, hu - seg_u(wz * fixed[:, None]))
        l11 = jnp.sqrt(cu[:, 0, 0])
        l21 = cu[:, 1, 0] / l11
        l22 = jnp.sqrt(jnp.maximum(cu[:, 1, 1] - l21**2, 0.0))
        u = mean_u[:, 0] + l11 * z_u[:, 0]
        drift = mean_u[:, 1] + l21 * z_u[:, 0] + l22 * z_u[:, 1]
        fixed = fixed + drift[d.unit] * d.unit_time  # drift joins the non-level part
        quad_u = jnp.sum(hu * ch)
        logdet_u = jnp.sum(jnp.log(det))
    else:
        c, h = parts["c"], parts["h"]
        u = c * (h - seg_u(w * fixed)) + jnp.sqrt(c) * z_u
        drift = jnp.zeros(J)
        quad_u = jnp.sum(c * h * h)
        logdet_u = -jnp.sum(jnp.log(c))

    # Log marginal likelihood of y given lam and the scales, with every
    # Gaussian latent integrated out, up to terms that do not depend on the
    # group scales:  1/2 b'Q^-1 b - 1/2 log|Q_post| + 1/2 log|Q_prior|.
    # The block elimination order (units, buildings, global) splits both the
    # quadratic form and the determinant into per-level pieces.
    quad = quad_u + quad_lg
    logdet_post = logdet_u + logdet_lg
    logdet_prior = jnp.sum(jnp.log(kappa)) - 2 * J * jnp.log(s["unit_scale"])
    if d.unit_drift:
        logdet_prior = logdet_prior - 2 * J * jnp.log(s["unit_drift_scale"])
    for name, rank in d.global_ranks.items():
        logdet_prior = logdet_prior - 2 * rank * jnp.log(s[name])
    for name, rank in d.local_ranks.items():
        # With the untouched knots integrated out the walk's rank is the
        # number of touched knots.
        total = d.walk_rank if name == "walk_scale" and d.buckets else K * rank
        logdet_prior = logdet_prior - 2 * total * jnp.log(s[name])
    # Terms that depend on sigma through W = lam / sigma^2.
    logdet_w = jnp.sum(jnp.log(w))
    logml = 0.5 * (quad - logdet_post + logdet_prior + logdet_w - jnp.sum(w * y * y))
    return theta, theta_l, u, fixed, drift, logml


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
        "season_raw": theta[d.season]
        if d.season_basis is None
        else d.season_basis @ theta[d.season],
        "building": theta_l[:, 0],
        "unit": state["unit"],
        "nu": state["nu"],
        **({"unit_nu": state["unit_nu"]} if d.unit_t else {}),
        **({"unit_drift": state["drift"]} if d.unit_drift else {}),
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
    if d.fslope_local:
        out["fslope"] = theta_l[:, jnp.asarray(d.fslope_local)]
        out["fslope_scales"] = jnp.stack(
            [state[f"fslope_scale_{i}"] for i in range(len(d.fslope_local))]
        )
        out["fslope_index"] = jnp.asarray(d.fslope_cols, dtype=jnp.int32)
    if d.knot_start is not None:
        out["walk_step"] = steps(theta_l[:, d.knot_start :])
        # The spacing linear_predictor interpolates the walk with (held-out scores).
        out["walk_knot_months"] = d.walk_months
    return out


def make_step(d: Design):
    n = d.y.shape[0]
    rank = {
        "sigma": n,
        "unit_scale": d.n_units,
        "unit_drift_scale": d.n_units,
        **d.global_ranks,
        **{k: r * d.n_buildings for k, r in d.local_ranks.items()},
    }

    hier = list(d.scale_names)  # collapsed update covers sigma and every group scale

    def step(key, state, cfg, prop_sd=None, solo_sd=None):
        """One iteration. `cfg` holds the step sizes; with `prop_sd` (one
        proposal sd per hierarchical log-scale) the scales are first updated
        by a collapsed Metropolis step that integrates out every latent."""
        (
            noise_steps,
            sigma_step_sd,
            nu_step_sd,
            rescale_steps,
            rescale_step_sd,
            unit_rescale_step_sd,
        ) = cfg
        keys = jax.random.split(key, 14)
        s = {k: state[k] for k in d.scale_names}
        z = (
            jax.random.normal(keys[0], (d.a.shape[1],)),
            jax.random.normal(keys[1], (d.n_buildings, d.n_local)),
            jax.random.normal(
                keys[2], (d.n_units, 2) if d.unit_drift else (d.n_units,)
            ),
            # The walk knots no row touches (compact designs).
            jax.random.normal(keys[8], (d.n_buildings, d.n_local - d.knot_start + 1))
            if d.buckets
            else None,
        )
        parts = block_parts(d, state["lam"], s, state["kappa"])
        out = block_solve(d, parts, s, *z)
        info = {}
        if prop_sd is not None:
            # Collapsed scale update: p(scales | lam, sigma, y) with all
            # Gaussian latents integrated out, random-walk on log scales. The
            # latents are then drawn from whichever factorisation is kept.
            k1, k2 = jax.random.split(keys[11])
            normal = jax.random.normal(k1, (len(hier),))
            # prop_sd: per-scale sds, or a lower-triangular factor (full
            # covariance proposal).
            step_ = prop_sd @ normal if prop_sd.ndim == 2 else prop_sd * normal
            s_new = dict(s)
            for i, name in enumerate(hier):
                s_new[name] = s[name] * jnp.exp(step_[i])
            parts_new = block_parts(d, state["lam"], s_new, state["kappa"])
            out_new = block_solve(d, parts_new, s_new, *z)

            def log_prior(sc):
                return sum(
                    -(sc[k] ** 2) / (2 * d.prior_sd[k] ** 2) + jnp.log(sc[k])
                    for k in hier
                )

            log_ratio = out_new[-1] - out[-1] + log_prior(s_new) - log_prior(s)
            ok = jnp.log(jax.random.uniform(k2)) < log_ratio
            out = jax.tree.map(lambda a, b, ok=ok: jnp.where(ok, b, a), out, out_new)
            s = {k: jnp.where(ok, s_new[k], s[k]) for k in s}
            solos = solo_sd or {}

            def keep(ok, old, new):
                return jax.tree.map(lambda a, b: jnp.where(ok, b, a), old, new)

            if solos:
                # The solo updates below reuse the parts of the kept scales.
                parts = keep(ok, parts, parts_new)
            info["collapsed_accept"] = ok.astype(jnp.float64)
            # One-dimensional collapsed updates for the slowest scales, each
            # with its own proposal size (a joint step must use the smallest).
            for i, (name, sd_i) in enumerate(solos.items()):
                k1, k2 = jax.random.split(jax.random.fold_in(keys[11], 100 + i))
                s_new = dict(s)
                s_new[name] = s[name] * jnp.exp(sd_i * jax.random.normal(k1))
                # Only a solo on a scale in PART_SCALES needs new row sums.
                parts_new = (
                    block_parts(d, state["lam"], s_new, state["kappa"])
                    if name in PART_SCALES
                    else parts
                )
                out_new = block_solve(d, parts_new, s_new, *z)
                log_ratio = (
                    out_new[-1]
                    - out[-1]
                    - (s_new[name] ** 2 - s[name] ** 2) / (2 * d.prior_sd[name] ** 2)
                    + jnp.log(s_new[name] / s[name])
                )
                ok = jnp.log(jax.random.uniform(k2)) < log_ratio
                out = jax.tree.map(
                    lambda a, b, ok=ok: jnp.where(ok, b, a), out, out_new
                )
                s = {k: jnp.where(ok, s_new[k], s[k]) for k in s}
                if name in PART_SCALES:
                    parts = keep(ok, parts, parts_new)
                info[f"solo_accept_{name}"] = ok.astype(jnp.float64)
        theta, theta_l, u, fixed, drift, _ = out
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

        step_sd = jnp.asarray(
            [sigma_step_sd, 0.0 if d.nu_fixed is not None else nu_step_sd]
        )

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
        # Student-t units: (unit_scale, unit_nu) | u jointly with kappa
        # integrated out (random-walk Metropolis on the logs; the scale and
        # tail weight trade off, so they are moved together), then kappa.
        kappa, unit_nu = state["kappa"], state["unit_nu"]
        if d.unit_t:
            nu_step = 0.0 if d.unit_nu_fixed is not None else 0.05

            def unit_target(z_):
                tau_, nu_u = jnp.exp(z_[0]), jnp.exp(z_[1])
                return (
                    jnp.sum(collect_module.student_t_logpdf(u, nu_u, tau_))
                    - tau_**2 / (2 * d.prior_sd["unit_scale"] ** 2)
                    + jax.scipy.stats.gamma.logpdf(nu_u, 2.0, scale=10.0)
                    + z_[0]
                    + z_[1]
                )

            unit_sd = jnp.asarray([0.01, nu_step])

            def unit_mh(carry, k):
                z_, lt, acc = carry
                k1, k2 = jax.random.split(k)
                prop = z_ + unit_sd * jax.random.normal(k1, (2,))
                lp = unit_target(prop)
                ok = jnp.log(jax.random.uniform(k2)) < lp - lt
                return (jnp.where(ok, prop, z_), jnp.where(ok, lp, lt), acc + ok), None

            z0 = jnp.log(jnp.stack([s["unit_scale"], unit_nu]))
            (z_un, _, u_acc), _ = jax.lax.scan(
                unit_mh,
                (z0, unit_target(z0), jnp.zeros(())),
                jax.random.split(keys[12], 10),
            )
            s["unit_scale"], unit_nu = jnp.exp(z_un[0]), jnp.exp(z_un[1])
            info["unit_nu_accept"] = u_acc / 10
            tau = s["unit_scale"]
            kappa = jax.random.gamma(keys[13], (unit_nu + 1) / 2, (d.n_units,)) / (
                (unit_nu + (u / tau) ** 2) / 2
            )
            # Collapsed per-unit update of kappa_j with u_j integrated out:
            # the unit's residuals r (excluding u_j) have covariance
            # D + (tau^2 / kappa_j) 11', so by Sherman-Morrison
            #   log p(r | kappa_j) = -1/2 log(1 + tau^2 s_j / kappa_j)
            #                        + 1/2 c_j h_j^2 + const,
            # c_j = 1 / (kappa_j / tau^2 + s_j). Random-walk Metropolis on
            # log kappa_j (all units at once), then u_j | kappa_j. This breaks
            # the u_j <-> kappa_j coupling for units with one or two rows.
            w_now = lam / sigma**2
            resid = d.y - fixed
            s_u = jax.ops.segment_sum(w_now, d.unit, d.n_units)
            h_u = jax.ops.segment_sum(w_now * resid, d.unit, d.n_units)

            def kappa_target(log_k):
                k_ = jnp.exp(log_k)
                c_ = 1.0 / (k_ / tau**2 + s_u)
                return (
                    -0.5 * jnp.log1p(tau**2 * s_u / k_)
                    + 0.5 * c_ * h_u**2
                    + (unit_nu / 2) * log_k
                    - (unit_nu / 2) * k_
                )

            def kappa_mh(carry, k):
                lk, lt = carry
                k1, k2 = jax.random.split(k)
                prop = lk + jax.random.normal(k1, lk.shape)
                lp = kappa_target(prop)
                ok = jnp.log(jax.random.uniform(k2, lk.shape)) < lp - lt
                return (jnp.where(ok, prop, lk), jnp.where(ok, lp, lt)), ok.mean()

            lk0 = jnp.log(kappa)
            (lk, _), k_acc = jax.lax.scan(
                kappa_mh,
                (lk0, kappa_target(lk0)),
                jax.random.split(jax.random.fold_in(keys[13], 1), 4),
            )
            kappa = jnp.exp(lk)
            c_u = 1.0 / (kappa / tau**2 + s_u)
            u = c_u * h_u + jnp.sqrt(c_u) * jax.random.normal(
                jax.random.fold_in(keys[13], 2), (d.n_units,)
            )
            info["kappa_accept"] = k_acc.mean()

            # Mode hop for each unit: is an unusual price an unusual unit or
            # unusual listings? Target u_j with every row weight and kappa_j
            # integrated out: prod_i t(r_i - u_j; nu, sigma) * t(u_j; nu_u, tau).
            # Independence proposal from a two-part mixture (near 0, near the
            # unit's mean residual); then lam and kappa are redrawn exactly.
            count = jax.ops.segment_sum(jnp.ones_like(resid), d.unit, d.n_units)
            rbar = jax.ops.segment_sum(resid, d.unit, d.n_units) / count

            def log_f(uu):
                rows = collect_module.student_t_logpdf(resid - uu[d.unit], nu, sigma)
                return jax.ops.segment_sum(
                    rows, d.unit, d.n_units
                ) + collect_module.student_t_logpdf(uu, unit_nu, tau)

            def log_q(uu):
                a_ = jax.scipy.stats.norm.logpdf(uu, 0.0, 2 * tau)
                b_ = jax.scipy.stats.norm.logpdf(uu, rbar, 2 * sigma)
                return jnp.logaddexp(a_, b_) - jnp.log(2.0)

            kh = jax.random.split(jax.random.fold_in(keys[13], 3), 3)
            pick = jax.random.bernoulli(kh[0], 0.5, (d.n_units,))
            prop = jnp.where(
                pick,
                2 * tau * jax.random.normal(kh[1], (d.n_units,)),
                rbar + 2 * sigma * jax.random.normal(kh[2], (d.n_units,)),
            )
            log_ratio = log_f(prop) - log_f(u) + log_q(u) - log_q(prop)
            hop = (
                jnp.log(
                    jax.random.uniform(jax.random.fold_in(keys[13], 4), (d.n_units,))
                )
                < log_ratio
            )
            u = jnp.where(hop, prop, u)
            info["hop_accept"] = hop.mean()
            e = d.y - fixed - u[d.unit]
            lam = jax.random.gamma(
                jax.random.fold_in(keys[4], 1), (nu + 1) / 2, (n,)
            ) / ((nu + (e / sigma) ** 2) / 2)
            kappa = jax.random.gamma(
                jax.random.fold_in(keys[13], 5), (unit_nu + 1) / 2, (d.n_units,)
            ) / ((unit_nu + (u / tau) ** 2) / 2)
        new["unit_scale"] = _update_scale(
            keys[5],
            s["unit_scale"],
            jnp.sum(kappa * u * u),
            rank["unit_scale"],
            d.prior_sd["unit_scale"],
        )
        if d.unit_drift:
            new["unit_drift_scale"] = _update_scale(
                jax.random.fold_in(keys[5], 1),
                s["unit_drift_scale"],
                jnp.sum(drift * drift),
                rank["unit_drift_scale"],
                d.prior_sd["unit_drift_scale"],
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
        # Rescaling moves on (scale, effects) ridges: (tau, v) -> (c tau, c v).
        # Given the effects, tau is pinned down tightly, and vice versa, so
        # plain Gibbs moves along the ridge slowly. For a symmetric step on
        # log c the acceptance ratio is
        #   lik(c v) / lik(v) * prior(c tau) / prior(tau) * c
        # (the location-scale prior of v and the Jacobian cancel all but one
        # c), with the Gaussian likelihood given lam, sigma and all other
        # latents. No block solve: each step is one weighted residual sum.
        wts = lam / sigma**2
        if d.knot_start is not None:
            walk_only = (
                jnp.zeros_like(theta_l)
                .at[:, d.knot_start :]
                .set(theta_l[:, d.knot_start :])
            )
            contrib = local_value(walk_only, d.building, d.slots, d.slot_values)
            c_tot, tau, acc = _rescale(
                keys[10],
                e,
                wts,
                contrib,
                new["walk_scale"],
                d.prior_sd["walk_scale"],
                rescale_step_sd,
                rescale_steps,
            )
            new["walk_scale"] = tau
            theta_l = theta_l.at[:, d.knot_start :].multiply(c_tot)
            e = e - (c_tot - 1.0) * contrib
            info["rescale_accept"] = acc / rescale_steps
        c_u, tau_u, acc_u = _rescale(
            jax.random.fold_in(keys[10], 1),
            e,
            wts,
            u[d.unit],
            new["unit_scale"],
            d.prior_sd["unit_scale"],
            unit_rescale_step_sd,
            rescale_steps,
        )
        new["unit_scale"] = tau_u
        u = u * c_u
        info["unit_rescale_accept"] = acc_u / rescale_steps
        state = {
            "theta": theta,
            "local": theta_l,
            "unit": u,
            "lam": lam,
            "nu": nu,
            "kappa": kappa,
            "drift": drift,
            "unit_nu": unit_nu,
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
    "unit_drift_scale": 0.02,
}


def init_states(d: Design, key, chains):
    """Overdispersed starting scales; latents are drawn in the first step."""
    names = d.scale_names
    start = {**START, **{n: 0.05 for n in names if n.startswith("fslope_scale_")}}
    k1, _ = jax.random.split(key)
    jitter = jnp.exp(0.7 * jax.random.normal(k1, (chains, len(names) + 1)))
    state = {n: start[n] * jitter[:, i] for i, n in enumerate(names)}
    state["nu"] = (
        5.0 * jitter[:, -1] if d.nu_fixed is None else jnp.full((chains,), d.nu_fixed)
    )
    state["theta"] = jnp.zeros((chains, d.a.shape[1]))
    state["local"] = jnp.zeros((chains, d.n_buildings, d.n_local))
    state["unit"] = jnp.zeros((chains, d.n_units))
    state["lam"] = jnp.ones((chains, d.y.shape[0]))
    state["kappa"] = jnp.ones((chains, d.n_units))
    state["drift"] = jnp.zeros((chains, d.n_units))
    state["unit_nu"] = (
        jnp.full((chains,), d.unit_nu_fixed if d.unit_nu_fixed is not None else 5.0)
        if d.unit_t
        else jnp.zeros((chains,))
    )
    return state


batched = collect_module.batched  # shared with NUTS; kept here for old callers


def _rescale(key, e, wts, contrib, tau, prior_sd, step_sd, steps):
    """Random-walk Metropolis on log c for (tau, v) -> (c tau, c v); `contrib`
    is v's contribution to the fit and `e` the residual with it included."""

    def body(carry, k):
        c_tot, tau_, acc = carry
        k1, k2 = jax.random.split(k)
        log_c = step_sd * jax.random.normal(k1)
        c = jnp.exp(log_c)
        r_now = e - (c_tot - 1.0) * contrib
        r_new = e - (c_tot * c - 1.0) * contrib
        log_ratio = (
            -0.5 * jnp.sum(wts * (r_new**2 - r_now**2))
            - ((c * tau_) ** 2 - tau_**2) / (2 * prior_sd**2)
            + log_c
        )
        ok = jnp.log(jax.random.uniform(k2)) < log_ratio
        return (
            jnp.where(ok, c_tot * c, c_tot),
            jnp.where(ok, c * tau_, tau_),
            acc + ok,
        ), None

    (c_tot, tau, acc), _ = jax.lax.scan(
        body, (jnp.ones(()), tau, jnp.zeros(())), jax.random.split(key, steps)
    )
    return c_tot, tau, acc


def _detrended_cov(x):
    """Covariance of (chains, draws, k) around each chain's linear trend,
    averaged over chains: (k, k)."""
    t = np.arange(x.shape[1], dtype=float)
    t = (t - t.mean())[None, :, None]
    xc = x - x.mean(axis=1, keepdims=True)
    slope = (t * xc).sum(axis=1, keepdims=True) / (t * t).sum()
    r = xc - slope * t
    return np.einsum("cdi,cdj->ij", r, r) / (x.shape[0] * x.shape[1])


def _step_sds(prop_sd):
    """Marginal step sd per scale of a diagonal or full-covariance proposal."""
    p = np.asarray(prop_sd)
    return np.sqrt((p * p).sum(axis=1)) if p.ndim == 2 else p


def _detrended_var(x):
    """Per-chain variance of (chains, draws, k) around each chain's linear trend."""
    t = np.arange(x.shape[1], dtype=float)
    t = (t - t.mean())[None, :, None]
    xc = x - x.mean(axis=1, keepdims=True)
    slope = (t * xc).sum(axis=1, keepdims=True) / (t * t).sum()
    return (xc - slope * t).var(axis=1)


def _adapt(acc, target):
    """Multiplicative step-size update for one warmup round."""
    return 0.3 if acc < 0.05 else float(np.exp(2.0 * (acc - target)))


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
        # Within-chain spread around a linear trend: robust to chains that
        # have not met yet (which would inflate a pooled estimate) and to
        # chains still drifting from their start (which would inflate a plain
        # within-chain variance in short warmups).
        sd = np.sqrt(_detrended_var(tail).mean(axis=0))
        if settings.collapse_cov:
            cov = _detrended_cov(tail[..., :-1]) + 1e-10 * np.eye(len(hier))
            prop_sd = jnp.asarray(
                settings.collapse_scale / np.sqrt(len(hier)) * np.linalg.cholesky(cov)
            )
        else:
            prop_sd = jnp.asarray(
                settings.collapse_scale * sd[:-1] / np.sqrt(len(hier))
            )
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
            settings.rescale_step_sd,
        )

        # Phase 2 in two halves. After the first, rescale each collapsed step
        # toward its target acceptance (0.44 for 1-D steps, 0.23 for the
        # joint step): a scale's conditional spread given the others can be
        # much tighter than its marginal spread, which sized the steps above.
        n2 = settings.warmup - n1
        solo_names = list(solo_sd)

        def warm2(state, k, psd, ssd, length):
            ssd_dict = dict(zip(solo_names, ssd))

            def body(st, kk):
                st, info = step(kk, st, cfg, psd, ssd_dict)
                acc = jnp.stack(
                    [
                        info["collapsed_accept"],
                        *[info[f"solo_accept_{n}"] for n in solo_names],
                        info["noise_accept"],
                        info.get("rescale_accept", jnp.zeros(())),
                        info["unit_rescale_accept"],
                    ]
                )
                return st, acc

            state, acc = jax.lax.scan(body, state, jax.random.split(k, length))
            return state, acc.mean(axis=0)

        ssd = jnp.asarray([solo_sd[n] for n in solo_names])
        rounds = 3
        lengths = [n2 // rounds] * (rounds - 1) + [n2 - (rounds - 1) * (n2 // rounds)]
        for r, (phase_key, length) in enumerate(
            zip(jax.random.split(k_warm2, rounds), lengths)
        ):
            run2 = jax.jit(
                batched(
                    lambda st, k, _psd=prop_sd, _sd=ssd, _len=length: warm2(
                        st, k, _psd, _sd, _len
                    ),
                    settings.chains,
                    settings.chain_batch,
                )
            )
            states, acc = run2(states, jax.random.split(phase_key, settings.chains))
            acc = np.asarray(acc).mean(axis=0)
            log(
                f"warmup round {r} acceptance "
                + ", ".join(
                    f"{n}={a:.2f}"
                    for n, a in zip(
                        ["joint", *solo_names, "noise", "rescale", "unit_rescale"], acc
                    )
                )
            )
            if r < rounds - 1:
                # Damped Robbins-Monro step on the log step sizes, toward 0.23
                # (joint), 0.44 (1-D) and 0.3 (2-D noise); a step that is
                # almost never accepted is cut hard instead.
                prop_sd = prop_sd * _adapt(acc[0], 0.23)
                ssd = ssd * jnp.asarray([_adapt(a, 0.44) for a in acc[1:-3]])
                noise = _adapt(acc[-3], 0.3)
                rescale = _adapt(acc[-2], 0.44) if d.knot_start is not None else 1.0
                cfg = (
                    cfg[0],
                    cfg[1] * noise,
                    cfg[2] * noise,
                    cfg[3],
                    cfg[4] * rescale,
                    cfg[5] * _adapt(acc[-1], 0.44),
                )
        solo_sd = {n: float(v) for n, v in zip(solo_names, np.asarray(ssd))}
    jax.block_until_ready(states)
    warmup_seconds = time.perf_counter() - t0
    log(
        f"warmup {warmup_seconds:.1f}s "
        + " ".join(
            f"{n}={float(np.median(states[n])):.4f}" for n in (*d.scale_names, "nu")
        )
        + (
            f" collapsed proposal sd {dict(zip(hier, np.round(_step_sds(prop_sd), 4)))}"
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
        None if prop_sd is None else dict(zip(hier, _step_sds(prop_sd).tolist()))
    )
    out["noise_step_sd"] = {
        "sigma": cfg[1],
        "nu": cfg[2],
        "rescale": cfg[4],
        "unit_rescale": cfg[5],
    }
    out["solo_proposal_sd"] = solo_sd
    return out
