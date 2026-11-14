"""The drift model's sampler with a level for each line of a building, between the
building's level and the unit's.

A line is the units of one building with the same bedrooms and full baths. Each unit's
lasting level centers on its line's level,

    s_k ~ Normal(l_line(k), ss^2),    l_m ~ Normal(0, line_sd^2),

and every other term is `drift`'s. The screen of 2026-11-12
(docs/notes/line-level-screen-2026-11-12.md) moved L1's held-out predictions by the mean
residual of the earlier held-out ads of other units in the same line, and gained 750 elpd
(SE 83).

Lines. `line_index` gives each unit a single line: the (bedrooms, full baths) pair most of
its rows carry, ties going to the pair of the latest row. A held-out row's own bedrooms and
baths count toward its unit's pair, since they are columns of the row and not its rent. A
row with no `unit_id` is a unit of its own, with its own pair. Training lines are numbered in
sorted order of their keys, and a row whose line has no training row carries -1.

Sampler. `drift`'s building paths, drawn given the unit levels, left every chain creeping
until the building term was collapsed, and a line nests a building's units more tightly
still. So the sweep integrates the line levels out wherever `drift.make_sampler` integrates
out the buildings' levels and paths:

1. theta is drawn as in `drift`, with u and the buildings' levels integrated out and the
   line levels held at their last draw.
2. The scale step adds log line_sd to `drift`'s coordinates (after the phases' log factors)
   and slice samples them together, with u, the levels, the paths and the lines all
   integrated out. unit_sd and line_sd both carry the spread of a building's units, so they
   move together along the step's adapted directions.
3. The slow columns are redrawn, then each zone's spread and the path's (log sd, logit rho)
   by `drift`'s slice updates, then every building's level and path in one draw, all with
   the lines integrated out. The sampler then draws the line levels given those, with u
   integrated out.
4. u is drawn given the lines, then the rest of the sweep is `drift`'s.

Integrating the lines out costs little, because units nest in lines. Let C map the rows to
their lines and W be the units' precision, block-diagonal by unit. Then C'WC is diagonal,
with c_m the sum of W's row sums over line m's rows, and integrating the lines out of a
building's rows turns W into W - W C G C' W with G = diag(line_sd^2 / (1 + line_sd^2 c_m)).
The collapsed step reads W only through the building's sums H = B'WB and h = B'W tgt
(`drift.make_sampler`'s `cell_sums`), so the sampler corrects those sums in place:

    H_pq -= sum over lines m of v_pm G_m v_qm,    h_p -= sum over m of v_pm G_m hl_m,

where v_pm sums W's row sums over the rows of cell p in line m, and hl = C'W tgt. Every line
belongs to a single building, so the correction stays inside each building's block, and
`cell_system` takes the corrected sums as they are. The lines add

    sum over m of -log(1 + line_sd^2 c_m) / 2 + G_m hl_m^2 / 2

to the log density of the building's rows. That term holds no building spread or path
scale, so `drift`'s update of those runs unchanged on the corrected sums. Given a building's
level and path, line m's level is Normal(G_m (hl_m - c_m level - sum over p of v_pm path_p),
G_m).

The slow redraw of `drift`'s `update_slow` integrates the lines out too, and its columns
take the bedroom and bath columns besides the building amenities (`Settings`): those are
nearly constant within a line, and given the lines their coefficients would trade against
the lines' mean.

Predictions. A held-out row of a line with training rows adds that line's level in each
draw, on top of `drift`'s location. A row in a new line adds 0, and its line's prior
variance line_sd^2 joins its unit's variance in `pred_unit_sd`. `drift_score` reads both as
it reads L1's.

    python -m rentfrontier.run --model drift-building-phase-line --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import math
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import amp_joint, b0, building_zones_floor_asof, drift, two_zone
from .building_zones_gibbs import _prior_vectors, gp_cov
from .building_zones_kitchen_sink import (
    KEPT,
    TRACED,
    gp_spec,
    site_rows,
    wave_matrix,
)
from .drift import HYP, PHASE_PRIOR, UNIT_SD_PRIOR
from .two_zone import site_share

# The HalfNormal scale of line_sd, on log rent, the same as the unit scale's
# (`drift.UNIT_SD_PRIOR`). Lines of one building with the same columns rarely differ by more
# than 10 to 20% in rent, as its units rarely do, so 0.1 puts most of the prior mass below
# 0.2 and leaves 0 open. A line's level and a unit's lasting level both read the spread of a
# building's units, and the same prior on both leaves their split to the data.
LINE_SD_PRIOR = 0.1
# The slice interval's length along log line_sd until the warmup sets the directions, as
# along each unit scale's log.
LINE_WIDTH = drift.HYP_WIDTH
# line_sd's starting point, and what the sweep's key is folded with for the lines' draw.
LINE_SD_START = 0.05
LINE_KEY = 101
# The slow columns: the building amenity codes of `drift.Settings`, and the bedroom and
# bath columns, nearly constant within a line.
SLOW_COLUMNS = ("bld:", "bed>=", "full>=", "bed=", "bath_unknown")


@dataclass(frozen=True)
class Settings(drift.Settings):
    slow_columns: tuple[str, ...] = SLOW_COLUMNS


@dataclass
class Design(drift.Design):
    line: np.ndarray = (
        None  # (rows,) the row's line number, -1 for a line with no training row
    )
    lines: int = 0  # the number of lines with a training row


def unit_keys(frame: pd.DataFrame) -> np.ndarray:
    """Each row's unit key, as `drift.unit_index` builds it: building and `unit_id`, and for a
    row with no `unit_id` the building and the row's position."""
    building = frame.building.astype(str).to_numpy(object)
    none = frame.unit_id.isna().to_numpy()
    unit_id = np.where(none, "", frame.unit_id.astype(object).to_numpy()).astype(str)
    key = np.array([f"{b}|{u}" for b, u in zip(building, unit_id)], dtype=object)
    key[none] = [f"{b}|#row{i}" for i, b in zip(np.flatnonzero(none), building[none])]
    return key.astype(str)


def line_pair(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Each row's bedrooms, rounded and clipped at 0 as `b0.design` codes them, and full
    baths, rounded, with -1 for a missing count."""
    beds = np.clip(np.round(frame.bedrooms.to_numpy(float)), 0, None).astype(np.int64)
    full = frame.full_baths.to_numpy(float)
    full = np.where(np.isnan(full), -1, np.round(np.nan_to_num(full))).astype(np.int64)
    return beds, full


def line_index(frame: pd.DataFrame, held) -> tuple[np.ndarray, int]:
    """Each row's line number and the number of lines with a training row. A unit's line is
    its building with the (bedrooms, full baths) pair of most of its rows, training and
    held-out alike; among pairs with as many rows, the pair of the latest row by
    `latest_day`, then by position, wins."""
    key = unit_keys(frame)
    unit = pd.factorize(key)[0]
    beds, full = line_pair(frame)
    pair = beds * 1000 + (full + 1)
    day = pd.to_datetime(frame.latest_day).to_numpy().astype("datetime64[ns]")
    rows = pd.DataFrame(
        {
            "unit": unit,
            "pair": pair,
            "day": day.astype(np.int64),
            "pos": np.arange(len(frame)),
        }
    )
    count = (
        rows.groupby(["unit", "pair"], sort=False)
        .agg(n=("pos", "size"), day=("day", "max"), pos=("pos", "max"))
        .reset_index()
    )
    o = np.lexsort((-count.pos, -count.day, -count.n, count.unit))
    best = count.iloc[o].drop_duplicates("unit")
    mode = np.empty(unit.max(initial=-1) + 1, np.int64)
    mode[best.unit.to_numpy()] = best.pair.to_numpy()
    mine = mode[unit]
    building = frame.building.astype(str).to_numpy(object)
    lkey = np.array(
        [f"{b}|{p // 1000}|{p % 1000 - 1}" for b, p in zip(building, mine)], dtype=str
    )
    train = ~np.asarray(held, bool)
    keys = np.unique(lkey[train])
    return pd.Index(keys).get_indexer(lkey).astype(np.int64), len(keys)


def subset(d: Design, mask: np.ndarray) -> Design:
    """`drift.subset`, with each kept row's line and, for the rows to predict, theirs."""
    mask = np.asarray(mask, bool)
    out = drift.subset(d, mask)
    pred = None if out.pred is None else out.pred | {"line": d.line[~mask]}
    return dataclasses.replace(out, line=d.line[mask], pred=pred)


def line_layout(line, site, cell, col: dict, lines: int) -> dict:
    """The static index arrays of the lines inside the collapsed building term, for rows in
    the sampler's order: `line` and `site` are the rows' line and building, `cell` each row's
    place in the paths raveled as (buildings, steps), and `col` the term's
    `drift.cell_layout`.

    A pair is a line in one of its building's cells. Returns
    - `pair_of_row`: (rows,) each row's pair, with the pairs grouped by line;
    - `pair_line`, `pair_h`, `pair_cell`: each pair's line, its cell's place in the flat h
      of `cell_layout` and in the raveled paths;
    - `pp_a`, `pp_b`, `pp_H`, `pp_line`: for every ordered pair of pairs of one line, the
      two pairs, their two cells' place in the flat H, and the line;
    - `line_site`: (lines,) each line's building."""
    size_h = col["size_h"]
    n = len(line)
    pairs, pair_of_row = np.unique(line * size_h + col["h"], return_inverse=True)
    pair_line, pair_h = pairs // size_h, pairs % size_h
    any_row = np.zeros(len(pairs), np.int64)
    any_row[pair_of_row] = np.arange(n)
    off_h = np.array([b["off_h"] for b in col["buckets"]])
    off_H = np.array([b["off_H"] for b in col["buckets"]])
    m = np.array([b["gap"].shape[1] for b in col["buckets"]])
    k = np.searchsorted(off_h, pair_h, side="right") - 1
    local = pair_h - off_h[k]
    pos = local % m[k]
    base = off_H[k] + (local // m[k]) * m[k] * m[k]
    assert np.array_equal((base + pos * (m[k] + 1))[pair_of_row], col["H_d"]), (
        "a pair's cell must be its rows' cell"
    )
    count = np.bincount(pair_line, minlength=lines)
    start = np.r_[0, np.cumsum(count)[:-1]]
    sq = count * count
    pp_line = np.repeat(np.arange(lines), sq)
    within = np.arange(len(pp_line)) - np.repeat(np.r_[0, np.cumsum(sq)[:-1]], sq)
    pp_a = start[pp_line] + within // count[pp_line]
    pp_b = start[pp_line] + within % count[pp_line]
    assert np.array_equal(base[pp_a], base[pp_b]), "a line spans two buildings"
    line_site = np.zeros(lines, np.int64)
    line_site[line] = site
    return dict(
        pair_of_row=pair_of_row,
        pair_line=pair_line,
        pair_h=pair_h,
        pair_cell=cell[any_row],
        pp_a=pp_a,
        pp_b=pp_b,
        pp_H=base[pp_a] + pos[pp_a] * m[k[pp_a]] + pos[pp_b],
        pp_line=pp_line,
        line_site=line_site,
    )


# ------------------------------------------------------------------ the sampler (JAX)


def make_sampler(d: Design, priors, settings, gp=None, groups=None):
    """The jitted sweep, the initial state, the jitted prediction step and the sampler's
    parts for design `d`, as `drift.make_sampler` returns them, with the lines (see the
    module docstring). `groups` must hold the buildings' collapsed term first. The sweep
    reuses `drift.make_sampler`'s parts where the lines leave them unchanged."""
    _, init_base, _, base = drift.make_sampler(
        d, priors, settings, gp=gp, groups=groups
    )
    col = base["cell_layout"]
    assert col is not None, "the lines need the buildings' collapsed term"
    assert base["nu_free"] and not base["unit_t"], "the lines take drift's own nu"
    jax, jnp = b0._jax()
    seg = jax.ops.segment_sum
    data = base["data"]
    order = base["order"]
    ars = base["ars"]
    zone = base["zone"]
    slow = base["slow"]
    sl_b, sl_M, i_g, sl_w = base["slices"]
    (
        weights,
        unit_W,
        pair_weights,
        apply_W,
        offsets,
        all_means,
        unit_loglik,
        lam_moments,
        row_sd,
        cell_system,
        cell_loglik,
        update_cells,
        draw_u,
        draw_theta,
        update_noise,
        update_local,
    ) = (
        base[k]
        for k in (
            "weights",
            "unit_W",
            "pair_weights",
            "apply_W",
            "offsets",
            "all_means",
            "unit_loglik",
            "lam_moments",
            "row_sd",
            "cell_system",
            "cell_loglik",
            "update_cells",
            "draw_u",
            "draw_theta",
            "update_noise",
            "update_local",
        )
    )
    alpha = d.names.index("alpha")
    others = np.array([j for j in range(len(d.names)) if j != alpha])
    Bc, sds = wave_matrix(d)
    nz = len(d.surfaces)
    S = len(zone)
    n = len(d.y)
    NL = int(d.lines)
    m_b, s_b, _, _ = _prior_vectors(d, priors)
    prec_b, lin_b = 1 / s_b**2, m_b / s_b**2
    gps = []
    for spec in gp or ():
        pos = np.searchsorted(others, [d.names.index(c) for c in spec["cols"]])
        prec_b[pos], lin_b[pos] = 0.0, 0.0
        gps.append((pos, np.asarray(spec["x"], float), spec["amp"], spec["ls"]))
    prec_b, lin_b = jnp.asarray(prec_b), jnp.asarray(lin_b)
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    which = np.concatenate([np.full(len(s["sd"]), k) for k, s in enumerate(d.surfaces)])
    joint = (
        amp_joint.make_step(Bc, sds, which, zone, priors.amp)
        if settings.joint_amp
        else None
    )
    dof = settings.level_dof
    zone_j, which_j, sds_j = jnp.asarray(zone), jnp.asarray(which), jnp.asarray(sds)
    # The noise phases, as `drift.make_sampler` reads them.
    pmap = None if d.phase is None else d.phase_map
    if d.phase is None:
        free = 0
    elif pmap is not None:
        free = np.asarray(pmap).shape[1]
    else:
        free = len(d.phases) - 1
    phased = free > 0
    pmap_j = None if pmap is None else jnp.asarray(np.asarray(pmap, float))
    pf = 8
    group_rows = jnp.asarray(np.bincount(d.group, minlength=4), dtype=float)
    phase_rows = None
    if phased and pmap is None:
        phase_rows = jnp.asarray(
            np.bincount(d.phase, minlength=free + 1)[1:], dtype=float
        )
    elif phased:
        phase_rows = jnp.asarray(
            np.bincount(d.phase, minlength=len(d.phases)) @ np.asarray(pmap, float)
        )
    # The blocks' rows, from the design's blocks of columns.
    bounds = np.cumsum([0] + [int(x.shape[0]) for x in data["xs"]])
    rows_per_site = site_rows(d)
    share = site_share(d)
    surf = [slice(s["first"], s["first"] + s["sites"]) for s in d.surfaces]
    zone_share = [jnp.asarray(share[p] / max(share[p].sum(), 1e-300)) for p in surf]
    row_wgt = [
        jnp.asarray(rows_per_site[p] / max(rows_per_site[p].sum(), 1.0)) for p in surf
    ]

    # The lines in the sampler's row order.
    line = np.asarray(d.line, np.int64)
    assert (line >= 0).all() and line.max(initial=-1) < NL, "every training row's line"
    unit_line = np.unique(np.stack([d.unit, line]), axis=1)
    assert unit_line.shape[1] == len(np.unique(d.unit)), "each unit takes one line"
    line_row = line[order]
    lay = line_layout(
        line_row,
        d.site[order],
        np.asarray(data["ar_cell"][0]),
        col,
        NL,
    )
    NP = len(lay["pair_line"])
    pred_line = (
        np.asarray(d.pred["line"], np.int64)
        if d.pred is not None and "line" in d.pred
        else np.full(len((d.pred or {}).get("unit", ())), -1, np.int64)
    )
    data = data | {
        "line_row": jnp.asarray(line_row),
        "p_line": jnp.asarray(pred_line),
    }
    data |= {k: jnp.asarray(v) for k, v in lay.items()}

    def phase_factors(factor):
        if pmap_j is None:
            return jnp.concatenate([jnp.ones(1), factor])
        return jnp.exp(pmap_j @ jnp.log(factor))

    def site_var(bsd, kap=None):
        b2 = bsd[zone_j] ** 2
        return b2 if kap is None else b2 / kap

    def line_terms(D, om_d, om_off, tgt):
        """The collapsed term's raw sums and the lines' sums at the units' precisions
        (om_d, om_off) and `tgt`: the flat `H` = B'WB and `h` = B'W tgt of `cell_sums`,
        each pair's `v` (its rows' sum of W's row sums), each line's `cl` = C'WC and
        `hl` = C'W tgt."""
        cl_ = D["cells"]
        ctil = om_d + seg(om_off, D["pi"], num_segments=n)
        Wt = apply_W(D, om_d, om_off, tgt)
        H = seg(om_d, cl_["H_d"], num_segments=col["size_H"]) + seg(
            om_off, cl_["H_o"], num_segments=col["size_H"]
        )
        return dict(
            H=H,
            h=seg(Wt, cl_["h"], num_segments=col["size_h"]),
            v=seg(ctil, D["pair_of_row"], num_segments=NP),
            cl=seg(ctil, D["line_row"], num_segments=NL),
            hl=seg(Wt, D["line_row"], num_segments=NL),
        )

    def line_gain(lt, l2):
        """Each line's G = line_sd^2 / (1 + line_sd^2 c)."""
        return l2 / (1 + l2 * lt["cl"])

    def corrected(D, lt, l2):
        """The buckets' (H, h) of `cell_sums` with the lines integrated out."""
        gam = line_gain(lt, l2)
        v, pl = lt["v"], D["pair_line"]
        H = lt["H"] - seg(
            gam[D["pp_line"]] * v[D["pp_a"]] * v[D["pp_b"]],
            D["pp_H"],
            num_segments=col["size_H"],
        )
        h = lt["h"] - seg(
            v * gam[pl] * lt["hl"][pl], D["pair_h"], num_segments=col["size_h"]
        )
        out = []
        for b in col["buckets"]:
            nb, m = b["gap"].shape
            out.append(
                (
                    H[b["off_H"] : b["off_H"] + nb * m * m].reshape(nb, m, m),
                    h[b["off_h"] : b["off_h"] + nb * m].reshape(nb, m),
                )
            )
        return out

    def line_loglik(lt, l2):
        """What integrating the lines out adds to the log density of the rows."""
        gam = line_gain(lt, l2)
        return jnp.sum(-0.5 * jnp.log1p(l2 * lt["cl"]) + 0.5 * gam * lt["hl"] ** 2)

    def level_loglik(D, bsd, par, F, om_d, om_off, tgt, l2, kap=None):
        """`drift`'s `level_loglik` with the lines integrated out as well."""
        lt = line_terms(D, om_d, om_off, tgt)
        sums = corrected(D, lt, l2)
        return jnp.sum(cell_loglik(D, jnp.log(bsd), par, sums, F, kap)) + line_loglik(
            lt, l2
        )

    def line_cond(D, lt, l2, lev, path):
        """The lines' conditional mean and variance given the buildings' levels and paths,
        with u integrated out."""
        gam = line_gain(lt, l2)
        on_path = seg(
            lt["v"] * path.ravel()[D["pair_cell"]], D["pair_line"], num_segments=NL
        )
        return gam * (lt["hl"] - lt["cl"] * lev[D["line_site"]] - on_path), gam

    def draw_line(D, key, lt, l2, lev, path):
        mean, var = line_cond(D, lt, l2, lev, path)
        return mean + jnp.sqrt(var) * jax.random.normal(key, (NL,))

    def hyp_logp(D, hyp, c, e):
        ss, sd = jnp.exp(hyp[0]), jnp.exp(hyp[1])
        prior = (
            -(ss**2) / (2 * UNIT_SD_PRIOR**2)
            + hyp[0]
            - sd**2 / (2 * drift.DRIFT_SD_PRIOR**2)
            + hyp[1]
            - (hyp[2] - drift.TAU_LOG_PRIOR[0]) ** 2 / (2 * drift.TAU_LOG_PRIOR[1] ** 2)
        )
        return unit_loglik(D, hyp, c, e) + prior

    def scales_logp(D, x, eta, tgt, bsd, par, F, kap=None):
        """`drift`'s `scales_logp` at x = (log ss, log sd, log tau, log sigma of each
        group, log nu, the phases' log factors, log line_sd), with the lines integrated
        out alongside u, the buildings' levels and the collapsed paths."""
        ls = x[3:7]
        lnu = x[7]
        sig = jnp.exp(ls)
        a = jnp.exp(lnu) / 2
        m, sd = lam_moments(lnu)
        loglam = m + sd * eta
        lam = jnp.exp(loglam)
        lf = x[pf : pf + free]
        c = lam / row_sd(D, sig, jnp.exp(lf)) ** 2
        w1, Wb = unit_W(D, x[:3], c)
        om_d, om_off = pair_weights(D, w1, Wb)
        a_nu, b_nu = priors.nu
        l2 = jnp.exp(2 * x[-1])
        out = (
            hyp_logp(D, x[:3], c, tgt)
            + 0.5 * jnp.sum(loglam)
            - jnp.sum(group_rows * ls)
            + level_loglik(D, bsd, par, F, om_d, om_off, tgt, l2, kap)
            + n * (a * jnp.log(a) - jax.scipy.special.gammaln(a) + jnp.log(sd))
            + a * jnp.sum(loglam)
            - a * jnp.sum(lam)
            - jnp.sum(sig**2) / (2 * priors.sigma**2)
            + jnp.sum(ls)
            + a_nu * lnu
            - b_nu * 2 * a
            - l2 / (2 * LINE_SD_PRIOR**2)
            + x[-1]
        )
        if not phased:
            return out
        return out - jnp.sum(phase_rows * lf) - jnp.sum(lf**2) / (2 * PHASE_PRIOR**2)

    def scales_x(st):
        x = jnp.concatenate([st["hyp"], jnp.log(st["sigma"]), jnp.log(st["nu"])[None]])
        x = jnp.concatenate([x, jnp.log(st["phase_scale"])]) if phased else x
        return jnp.concatenate([x, jnp.log(st["line_sd"])[None]])

    def update_scales(D, key, st, tgt, F):
        """`drift`'s scale step with log line_sd as one more coordinate."""
        m, sd = lam_moments(jnp.log(st["nu"]))
        eta = (jnp.log(st["lam"]) - m) / sd
        bsd, par = st["bld_sd"], st["ar_par"][0]

        def logp(x):
            return scales_logp(D, x, eta, tgt, bsd, par, F, st.get("kap"))

        x = scales_x(st)
        x, _ = drift.slice_along(key, x, logp(x), logp, st["hyp_dirs"])
        m, sd = lam_moments(x[7])
        new = dict(
            hyp=x[:3],
            sigma=jnp.exp(x[3:7]),
            nu=jnp.exp(x[7]),
            lam=jnp.exp(m + sd * eta),
            line_sd=jnp.exp(x[-1]),
        )
        if phased:
            new["phase_scale"] = jnp.exp(x[pf : pf + free])
        return new

    def scales_curvature(D, st, h=drift.CURV_STEP):
        """`drift`'s `scales_curvature` for this model's `scales_logp`."""
        m, sd = lam_moments(jnp.log(st["nu"]))
        eta = (jnp.log(st["lam"]) - m) / sd
        F = D["Bc"] @ st["theta"][sl_w]
        tgt = D["y"] - offsets(D, st) - all_means(D, st["theta"])
        tgt = tgt + st["ar"][0].ravel()[D["ar_cell"][0]]
        x0 = scales_x(st)
        K = x0.shape[0]
        eye = jnp.eye(K)
        i, j = np.triu_indices(K, 1)
        corner = eye[i] + eye[j]
        pts = h * jnp.concatenate([jnp.zeros((1, K)), eye, -eye, corner, -corner])
        f = jax.lax.map(
            lambda a: scales_logp(
                D,
                x0 + st["hyp_dirs"] @ a,
                eta,
                tgt,
                st["bld_sd"],
                st["ar_par"][0],
                F,
                st.get("kap"),
            ),
            pts,
        )
        f0, up, down = f[0], f[1 : K + 1], f[K + 1 : 2 * K + 1]
        both = f[2 * K + 1 :].reshape(2, -1).sum(axis=0)
        ends = up + down
        H = (
            jnp.zeros((K, K))
            .at[i, j]
            .set((both - ends[i] - ends[j] + 2 * f0) / (2 * h**2))
        )
        return H + H.T + jnp.diag((up + down - 2 * f0) / h**2)

    def slow_system(D, st, om_d, om_off, lt, sums, tgt, F, l2):
        """`drift`'s `slow_system` with the lines integrated out: X' V X and X' V (tgt - F)
        for the rows' marginal precision V with the lines out as well. Also returns the
        raw G = B' W X, (columns, flat h), and g = C' W X, (columns, lines)."""
        cl_, xs = D["cells"], D["xs"]
        Wt = apply_W(D, om_d, om_off, tgt)
        gam = line_gain(lt, l2)

        def one(k):
            Wx = apply_W(D, om_d, om_off, jnp.concatenate([x[:, k] for x in xs]))
            xtw = sum(
                x[:, slow].T @ Wx[r0:r1]
                for x, r0, r1 in zip(xs, bounds[:-1], bounds[1:])
            )
            return (
                seg(Wx, cl_["h"], num_segments=col["size_h"]),
                seg(Wx, D["line_row"], num_segments=NL),
                xtw,
            )

        G, g, A = jax.lax.map(one, jnp.asarray(slow))
        lin = sum(
            x[:, slow].T @ Wt[r0:r1] for x, r0, r1 in zip(xs, bounds[:-1], bounds[1:])
        )
        A = A - (g * gam) @ g.T
        lin = lin - g @ (gam * lt["hl"])
        pl = D["pair_line"]
        Gc = (
            G
            - seg(
                (lt["v"] * gam[pl])[:, None] * g.T[pl],
                D["pair_h"],
                num_segments=col["size_h"],
            ).T
        )
        par = st["ar_par"][0]
        b2 = site_var(st["bld_sd"], st.get("kap"))
        for (H, h), b, ids, gap in zip(sums, col["buckets"], cl_["sites"], cl_["gap"]):
            nb, m = gap.shape
            Gb = Gc[:, b["off_h"] : b["off_h"] + nb * m].reshape(-1, nb, m)
            Gb = Gb.transpose(1, 2, 0)
            Gz = jnp.concatenate([Gb.sum(axis=1, keepdims=True), Gb], axis=1)
            L, x, _ = cell_system(par, b2[ids], F[ids], H, h, gap)
            Y = jax.vmap(
                lambda Lk, Gk: jax.scipy.linalg.solve_triangular(Lk, Gk, lower=True)
            )(L, Gz)
            A = A - jnp.einsum("bms,bmt->st", Y, Y)
            lin = lin - jnp.einsum("bms,bm->s", Y, x)
        return 0.5 * (A + A.T), lin, G, g

    def update_slow(D, key, st, theta, om_d, om_off, lt, tgt, F, l2):
        """`drift`'s `update_slow` with the lines integrated out as well. Returns theta,
        and `tgt` and the raw sums at the new coefficients."""
        sums = corrected(D, lt, l2)
        A, lin, G, g = slow_system(D, st, om_d, om_off, lt, sums, tgt, F, l2)
        cur = theta[sl_b][slow]
        Q = A + jnp.diag(prec_b[slow])
        rhs = lin + A @ cur + lin_b[slow]
        s = 1 / jnp.sqrt(jnp.diag(Q))
        Cf = jnp.linalg.cholesky(Q * s[:, None] * s[None, :])
        mean = jax.scipy.linalg.cho_solve((Cf, True), rhs * s)
        dev = jax.scipy.linalg.solve_triangular(
            Cf.T, jax.random.normal(key, (len(slow),)), lower=False
        )
        step = (mean + dev) * s - cur
        theta = theta.at[sl_b].set(theta[sl_b].at[slow].add(step))
        tgt = tgt - jnp.concatenate([x[:, slow] @ step for x in D["xs"]])
        lt = lt | {"h": lt["h"] - step @ G, "hl": lt["hl"] - step @ g}
        return theta, tgt, lt

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
        M = theta[sl_M]
        g = theta[i_g]
        beta = (
            jnp.zeros(len(d.names), theta.dtype)
            .at[jnp.asarray(others)]
            .set(theta[sl_b])
            .at[alpha]
            .set(M[0])
        )
        pieces = [F[p] for p in surf]
        b = lev - F
        var_f, var_b = [], []
        for p, wgt in zip(surf, row_wgt):
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
        # `drift`'s keys for `drift`'s steps, and one folded in for the lines' draw.
        ks = jax.random.split(key, 9 + len(ars))
        k1, k2, k3, k4, k5, k6, k7, k8, k_gp = ks[:9]
        c = weights(D, st)
        w1, Wb = unit_W(D, st["hyp"], c)
        y_eff = D["y"] - offsets(D, st)
        theta, _ = draw_theta(D, k1, st, c, w1, Wb, y_eff - st["line"][D["line_row"]])
        w = theta[sl_w]
        F = D["Bc"] @ w
        cell = D["ar_cell"][0]
        # y less every term but the buildings' levels, the collapsed paths, the lines and u.
        tgt = y_eff - all_means(D, theta) + st["ar"][0].ravel()[cell]
        st = st | update_scales(D, k8, st, tgt, F)
        hyp = st["hyp"]
        c = weights(D, st)
        w1, Wb = unit_W(D, hyp, c)
        om_d, om_off = pair_weights(D, w1, Wb)
        l2 = st["line_sd"] ** 2
        lt = line_terms(D, om_d, om_off, tgt)
        if len(slow):
            theta, tgt, lt = update_slow(D, k3, st, theta, om_d, om_off, lt, tgt, F, l2)
        bsd, lev, par, path = update_cells(D, k2, st, corrected(D, lt, l2), F)
        line = draw_line(D, jax.random.fold_in(key, LINE_KEY), lt, l2, lev, path)
        e = tgt - lev[D["site"]] - path.ravel()[cell] - line[D["line_row"]]
        st = st | {
            "ar": (path, *st["ar"][1:]),
            "ar_par": st["ar_par"].at[0].set(par),
        }
        u = draw_u(D, k7, hyp, c, w1, Wb, e)
        r, ar, ar_par = update_local(D, ks[9:], st, c, e - u, 1)
        nu, sigma, lam = update_noise(k4, st, r, D)
        tau = update_tau(k5, st, theta[sl_M], theta[i_g])
        if joint is None:
            amp = update_amp(k6, st, w)
        else:
            amp, w = joint(k6, lev, bsd, st["amp"], st.get("kap"))
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
            hyp=hyp,
            hyp_dirs=st["hyp_dirs"],
            cell_dirs=st["cell_dirs"],
            line=line,
            line_sd=st["line_sd"],
            ar=tuple(ar),
            ar_par=jnp.stack(ar_par),
        )
        if phased:
            new["phase_scale"] = st["phase_scale"]
        if dof is not None:
            z2 = (lev - F) ** 2 / bsd[zone_j] ** 2
            new["kap"] = jax.random.gamma(
                jax.random.fold_in(key, drift.KAP_KEY), (dof + 1) / 2, (S,)
            ) / ((dof + z2) / 2)
        if gps:
            new["gp_amp"], new["gp_ls"] = update_gp(k_gp, st, theta)
        ss, sd, tu = jnp.exp(hyp[0]), jnp.exp(hyp[1]), jnp.exp(hyp[2])
        out = outputs(theta, lev, F) | dict(
            unit_sd=ss, drift_sd=sd, drift_tau=tu, line_sd=st["line_sd"]
        )
        if phased:
            out["phase_scale"] = phase_factors(st["phase_scale"])
        for k, a in enumerate(ars):
            out[a["name"] + "_ar_sd"] = jnp.exp(ar_par[k][0])
            out[a["name"] + "_ar_rho"] = jax.nn.sigmoid(ar_par[k][1])
        return new, out

    def predict(D, st):
        """`drift`'s prediction with the lines: the training rows' remainders lose their
        lines' levels before u's mean is formed, a row of a line with training rows adds
        that line's level, and a row of a new line adds line_sd^2 to its unit's
        variance."""
        loc, sd, mean = base["predict"](
            D | {"y": D["y"] - st["line"][D["line_row"]]}, st
        )
        pl = D["p_line"]
        known = pl >= 0
        shift = jnp.where(known, st["line"][jnp.maximum(pl, 0)], 0.0)
        wide = jnp.sqrt(sd.astype(mean.dtype) ** 2 + st["line_sd"] ** 2)
        sd = jnp.where(known, sd, wide.astype(jnp.float32))
        return (loc + shift).astype(jnp.float32), sd, mean

    def init(keys):
        st = init_base(keys)
        C, K = keys.shape[0], st["hyp_dirs"].shape[-1]
        z = jax.vmap(lambda k: jax.random.normal(jax.random.fold_in(k, LINE_KEY), ()))(
            keys
        )
        dirs = (
            jnp.zeros((C, K + 1, K + 1))
            .at[:, :K, :K]
            .set(st["hyp_dirs"])
            .at[:, K, K]
            .set(LINE_WIDTH)
        )
        return st | dict(
            line=jnp.zeros((C, NL)),
            line_sd=LINE_SD_START * jnp.exp(0.2 * z),
            hyp_dirs=dirs,
        )

    swept = jax.jit(jax.vmap(sweep, in_axes=(None, 0, 0)))
    predicted = jax.jit(jax.vmap(predict, in_axes=(None, 0)))
    curved = jax.jit(jax.vmap(scales_curvature, in_axes=(None, 0)))
    return (
        lambda keys, st: swept(data, keys, st),
        init,
        lambda st: predicted(data, st),
        base
        | dict(
            data=data,
            line_layout=lay,
            lines=NL,
            line_terms=line_terms,
            line_gain=line_gain,
            corrected=corrected,
            line_loglik=line_loglik,
            level_loglik=level_loglik,
            line_cond=line_cond,
            draw_line=draw_line,
            scales_logp=scales_logp,
            scales_x=scales_x,
            update_scales=update_scales,
            scales_curvature=scales_curvature,
            curvature=lambda st: curved(data, st),
            slow_system=slow_system,
            update_slow=update_slow,
            sweep=sweep,
            predict=predict,
            phased=phased,
        ),
    )


# ------------------------------------------------------------------ the run


def run(
    d: Design, priors, settings, log=print, checkpoint=None, gp="spec", groups=None
):
    """`drift.run` with this module's sampler: the traced and kept arrays add `line_sd`, the
    warmup sets the scale step's directions with log line_sd last, and the progress lines
    log it."""
    jax, jnp = b0._jax()
    gp = gp_spec(d.names) if gp == "spec" else gp
    t0 = time.perf_counter()
    sweep, init, predict, parts = make_sampler(
        d, priors, settings, gp=gp, groups=groups
    )
    local = tuple(g["name"] + s for g in groups or () for s in ("_ar_sd", "_ar_rho"))
    scale_names = ("nu", "sigma", "tau", "amp", "bld_sd") + (
        ("gp_amp", "gp_ls") if gp else ()
    )
    phase = ("phase_scale",) if parts["phased"] else ()
    more = phase + ("line_sd",)
    traced = TRACED + HYP + local + (("gp_amp", "gp_ls") if gp else ()) + more
    kept_names = KEPT + HYP + local + (("gp_amp", "gp_ls") if gp else ()) + more
    key = jax.random.PRNGKey(settings.seed)
    key, sub = jax.random.split(key)
    st = init(jax.random.split(sub, settings.chains))
    jax.block_until_ready(st)
    setup_seconds = time.perf_counter() - t0

    trace = {k: [] for k in traced}
    kept = {k: [] for k in kept_names}
    preds = {"pred_loc": [], "pred_unit_sd": []}
    has_pred = d.pred is not None and len(d.pred["unit"]) > 0
    if not has_pred:
        log("the split leaves no row to predict: this fit will have no pred_loc")
    total = settings.warmup + settings.draws
    per = max(1, settings.draws // settings.chunks)
    marks = {"warmup": None}
    # `drift.run`'s two settings of the scale step's directions in the warmup.
    adapt_at = {
        (k * settings.warmup) // 3: (k * settings.warmup) // 3 - settings.warmup // 6
        for k in (1, 2)
    }
    warm_hyp, warm_cell = {}, {}

    def output(final=False):
        stack = lambda v: np.stack(v, axis=1)  # noqa: E731
        now = time.perf_counter()
        sampling = now - marks["warmup"] if marks["warmup"] else 0.0
        warm = (marks["warmup"] or now) - t_first
        done = len(trace[traced[0]])
        extra = {}
        if preds["pred_loc"]:
            extra = (
                {k: stack(v) for k, v in preds.items()}
                | {
                    "pred_y": np.asarray(d.pred["y"]),
                    "pred_group": np.asarray(d.pred["group"]),
                }
                | ({"pred_phase": np.asarray(d.pred["phase"])} if phase else {})
            )
        return {
            "trace": {k: stack(v) for k, v in trace.items()},
            "kept": {k: stack(v) for k, v in kept.items()} | extra,
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
                    "hyp_dirs": np.asarray(st["hyp_dirs"][0]).tolist(),
                    "cell_dirs": np.asarray(st["cell_dirs"][0]).tolist(),
                }
            },
        }

    def scalars(st):
        hyp = np.exp(np.asarray(st["hyp"]))
        return (
            f"nu {np.asarray(st['nu'])[:4].round(3)}, "
            f"amp {np.asarray(st['amp'])[:2].round(3).tolist()}, "
            f"bld_sd {np.asarray(st['bld_sd'])[:2].round(4).tolist()}, "
            f"unit_sd {hyp[:4, 0].round(4).tolist()}, "
            f"line_sd {np.asarray(st['line_sd'])[:4].round(4).tolist()}, "
            f"drift_sd {hyp[:4, 1].round(4).tolist()}, "
            f"drift_tau {hyp[:4, 2].round(3).tolist()}, "
            + (
                f"phase_scale {np.asarray(st['phase_scale'])[:2].round(4).tolist()}, "
                if phase
                else ""
            )
        ) + "".join(
            f"{g['name']} sd {np.exp(np.asarray(st['ar_par'])[:4, k, 0]).round(4).tolist()} "
            f"rho {(1 / (1 + np.exp(-np.asarray(st['ar_par'])[:4, k, 1]))).round(3).tolist()}, "
            for k, g in enumerate(groups or ())
        )

    log(f"{parts['lines']} lines with a training row")
    if parts["slow_shares"]:
        log(
            f"{len(parts['slow'])} of {len(parts['slow_shares'])} named columns are redrawn "
            "with the building paths and the lines integrated out; each one's share of "
            "variance within buildings: "
            f"{ {k: round(v, 4) for k, v in parts['slow_shares'].items()} }"
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
        if i < settings.warmup:
            warm_hyp[i] = np.concatenate(
                [
                    np.asarray(st["hyp"]),
                    np.log(np.asarray(st["sigma"])),
                    np.log(np.asarray(st["nu"]))[:, None],
                ]
                + ([np.log(np.asarray(st["phase_scale"]))] if phase else [])
                + [np.log(np.asarray(st["line_sd"]))[:, None]],
                axis=1,
            )
            warm_cell[i] = np.asarray(st["ar_par"])[:, 0]
        if i + 1 in adapt_at and i + 1 - adapt_at[i + 1] >= 10:
            window = [warm_hyp[j] for j in range(adapt_at[i + 1], i + 1)]
            dirs = drift.adapted_dirs(np.stack(window, axis=1))
            st = st | {
                "hyp_dirs": jnp.broadcast_to(jnp.asarray(dirs), st["hyp_dirs"].shape)
            }
            log(
                f"scales' slice directions set at sweep {i + 1}: {dirs.round(5).tolist()}"
            )
            H = np.asarray(parts["curvature"](st)).mean(axis=0)
            dirs, share = drift.conditional_dirs(dirs, H)
            if share is None:
                log(
                    "the scale step's curvature is not negative definite: directions kept"
                )
            else:
                st = st | {
                    "hyp_dirs": jnp.broadcast_to(
                        jnp.asarray(dirs), st["hyp_dirs"].shape
                    )
                }
                log(
                    "reset along the scale step's own curvature; its variance over the "
                    f"window's, by axis: {share.round(3).tolist()}"
                )
            window = [warm_cell[j] for j in range(adapt_at[i + 1], i + 1)]
            dirs = drift.adapted_dirs(np.stack(window, axis=1))
            st = st | {
                "cell_dirs": jnp.broadcast_to(jnp.asarray(dirs), st["cell_dirs"].shape)
            }
            log(f"the building path's slice directions: {dirs.round(5).tolist()}")
        if i == settings.warmup - 1 or (settings.warmup == 0 and i == 0):
            jax.block_until_ready(st)
            marks["warmup"] = time.perf_counter()
        if i >= settings.warmup:
            j = i - settings.warmup
            full = out | {k: st[k] for k in scale_names}
            for k in traced:
                trace[k].append(np.asarray(full[k]))
            if (j + 1) % settings.keep_every == 0:
                for k in kept_names:
                    kept[k].append(np.asarray(full[k]))
                if has_pred:
                    loc, s, _ = predict(st)
                    preds["pred_loc"].append(np.asarray(loc))
                    preds["pred_unit_sd"].append(np.asarray(s))
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
                mid = settings.checkpoints and j + 1 < settings.draws
                if mid and checkpoint is not None and kept["beta"]:
                    checkpoint(output())
            spent = time.perf_counter() - t_first
            if (
                settings.budget_seconds is not None
                and spent > settings.budget_seconds
                and (j + 1) % settings.keep_every == 0
                and j + 1 < settings.draws
            ):
                log(
                    f"stopping at draw {j + 1} of {settings.draws}: the sweeps have taken "
                    f"{spent:.0f}s of a budget of {settings.budget_seconds:.0f}s"
                )
                break
        elif (i + 1) % max(1, settings.warmup // 5) == 0:
            log(
                f"warmup {i + 1}/{settings.warmup}: "
                + scalars(st)
                + f"{time.perf_counter() - t0:.0f}s"
            )
    out = output(final=True)
    log(
        f"sampling {out['seconds']['sampling']:.0f}s, "
        f"{out['result']['gibbs']['seconds_per_sweep']:.3f}s a sweep of {settings.chains} chains"
    )
    return out


def diagnostics(trace: dict, names) -> dict:
    """`drift.diagnostics`, with line_sd among the gate's quantities."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = drift.diagnostics({k: v for k, v in trace.items() if k != "line_sd"}, names)
    rows = out["per_quantity"]
    x = np.asarray(trace["line_sd"])
    if np.ptp(x) > 0:
        rows["line_sd"] = {"rhat": split_rhat(x), "ess": ess(x)}
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
    """`drift.summarize`, with line_sd among the unit scales."""
    out = drift.summarize({k: v for k, v in kept.items() if k != "line_sd"}, names)
    out["unit"]["line_sd"] = two_zone._q(np.asarray(kept["line_sd"]))
    return out


def run_record(d: Design) -> dict:
    """The lines' part of a run's record."""
    return {
        "line": {
            "key": "building, bedrooms and full baths; a unit takes the pair of most of "
            "its rows, ties going to its latest row's",
            "lines": int(d.lines),
            "line_sd_prior": f"HalfNormal({LINE_SD_PRIOR})",
            "slow_columns": list(SLOW_COLUMNS),
            "pred": "a row of a line with training rows adds the line's level; a row of a "
            "new line adds line_sd^2 to pred_unit_sd's square",
        }
    }


def main_run(argv, name, sample, spec, level_dof=None) -> None:
    """`drift.main_run` with this module's `Settings`."""
    parser = drift.run_parser(name, level_dof)
    building_zones_floor_asof.SPLIT = parser.parse_known_args(argv)[0].split
    b0.main_run(
        argv,
        parser=parser,
        name=name,
        settings_cls=Settings,
        sample=sample,
        line="baseline",
        spec=spec,
    )
