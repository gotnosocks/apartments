"""Per-listing estimates of a recorded run: the input of the listings site.

    uv run --extra gpu python -m rentfrontier.summary <run-name>

Reads the run's kept joint draws and the dataset it was fit on; never fits.
Refuses a dirty tree, a changed dataset or feature source (the files the
feature set reads now, against the run's record), a unit-split run (rows of
unseen units would lose their unit prior), and a run that fails the
convergence gate (`--allow-failing` for experiments; the gate status is
recorded either way).

For every row of the dataset the run's data rules keep, in the fit or held out:

estimate      leave-own-row-out estimate of the row's latent rent exp(mu):
              the median ask of this apartment, in this building, that
              month, given every other row in the fit but not the row's
              own ask.
              - held-out rows (not in the fit): the posterior as is;
              - rows in the fit: the unit level is integrated given the
                unit's other rows, as in `loo`; per draw, a level is drawn
                from that conditional (on `loo`'s grid, uniform within the
                cell) and the draws are reweighted by Pareto-smoothed
                importance weights 1 / p(y_i | theta, y_{u,-i}). A unit
                listed once in the fit gets a draw from the unit prior.
                pareto_k above `loo.k_threshold` marks an unreliable
                estimate.
              Weighted mean, median and 95% interval; residual_usd is the
              ask less the mean, residual_pct the ask over the mean, less 1.
pit           where the ask falls in the leave-own-row-out predictive
              distribution (Student-t noise included): about 0.5 is typical,
              below 0.025 or above 0.975 unusual.
estimate_pred_lower/upper_95, _80
              quantiles of that same predictive distribution, in dollars:
              the range the ask is likely to fall in (95% and 80%). With
              `--range-atoms` (or FRONTIER_RANGE_ATOMS=1) these go and two
              columns take their place:
noise_group   the row's residual scale among the run's noise groups;
estimate_atoms  RANGE_ATOMS quantiles of the total log rent over the draws,
              weighted by the row's importance weights, at the probabilities
              (i + 0.5) / RANGE_ATOMS, as float32.
              The site works out the ranges from them when a listing's page
              asks (`apartments.site.ranges`). A chunk whose rows' noise
              scales differ from their group's scale gets the exact columns
              instead, since the group's table would not describe its noise.
fitted_rent   the in-sample posterior of exp(mu), mean and 95% interval (the
              fit saw the row's ask; a review signal, not an out-of-sample
              error).
<term>_usd    dollar contributions of the estimate: the LMDI decomposition of
              `explain`, per draw, against the market reference (a reference
              apartment in an average building that month). Weighted means
              add up to the estimate exactly; 95% intervals.
inputs        the row's nonzero model inputs, JSON {feature name: value}.

Writes /data1/apartments/frontier/summaries/<run>-<commit>/:

rows.parquet          one row per dataset row (the columns above plus
                      audit_id, unit_id after the run's data rules, building,
                      period, asking_rent, in_fit, unit_fit_rows).
market.parquet        per month: the market reference rent's median with the
                      calendar season, and its median and 95% interval
                      without it.
buildings.parquet     per building: level and yearly trend as percentages,
                      median, 95% interval, and training rows.
coefficients.parquet  per feature column: exp(beta) - 1, median, 95% interval
                      and probability positive.
terms.json            the contribution terms in display order, with labels.
design-parts.npz      the design's indexes and averages that the estimate kit
                      and the rent map read (`rentfrontier.design_parts`),
                      with the hash of the run's rows it was made from.
data-rule-<rule>.jsonl  a copy of each row-dropping rule's file (the run's
                      hash): the rows the bundle leaves out, with reasons.
complete.json         provenance (run, commits, dataset and feature-source
                      sha256, gate, PSIS-LOO score, draws) and the sha256 of
                      every file; written last.

`--range-atoms` also writes noise.json: for each noise group, the CDF of the
mixture over draws of Student-t(nu_s) noise of scale sigma_s,g on NOISE_GRID
points spaced evenly over NOISE_SPAN median scales on either side of zero,
as {"groups": {group: {"lower", "step", "cdf"}}}.

The ranges from the atoms approximate the exact ones. The site convolves the
row's marginal distribution of total log rent (its atoms) with the group's
noise mixture averaged evenly over draws. That drops the pairing within a
draw of the total with sigma and nu, and it leaves the row's importance
weights off the noise side. On NB9 (10% of buildings, 26,398 rows,
2026-10-17) the bounds differed from the exact solve by 0.00027 log units at
the median and 0.0032 at the 95th percentile, against a Monte Carlo error of
0.0013 at the median (half the gap between the solves on even and odd draws).

`--range-sample` (or FRONTIER_RANGE_SAMPLE=1) also writes range-sample.npz:
each draw's total log rent, importance weight and residual scale for a sample
of rows, with nu, so that a cheaper form of the predictive intervals can be
checked against the exact ones offline. A row goes in the sample when the
first 8 bytes of the sha256 of its audit_id, read as a number in [0, 1),
fall below its noise group's rate.
The rate is RANGE_SAMPLE_ROWS over the training rows, raised to
RANGE_SAMPLE_PER_GROUP over the group's training rows where that is higher
(with `--buildings`, counting only the sampled buildings' training rows),
so a sparse noise group has every row in the sample. The arrays:

    audit_id, group, in_fit   (rows,)
    total, weights, sigma     (rows, draws) float32
    nu                        (draws,)

`--buildings FRACTION --out DIR` summarizes the rows of a sample of buildings
and writes the bundle to DIR, for measuring how the summary's cost grows with
rows. A building goes in the sample when the first 8 bytes of the sha256 of
its id as a string, read as a number in [0, 1), fall below FRACTION, so the 1%
sample is a subset of the 4% sample, and both are subsets of the 16%. The sample
changes only which rows go through the per-row loop: the posterior, the market,
building and coefficient tables and each row's unit_fit_rows still come from
the whole run, and complete.json records the fraction. DIR has to be outside
the summaries directory, where the Modal steps look for whole bundles.

`--rows FILE --out DIR` summarizes the buildings of the listings named in
FILE, one audit id a line, and writes the bundle to DIR: for checking a few
thousand listings of a run too large to load whole. Whole buildings go in, so
each unit's leave-own-row-out level comes from all of its rows, as in a whole
summary. The kept draws are read from posterior.npz a few draws at a time,
and only those buildings' and their units' columns are kept, so memory
follows the listings' buildings, not the run. The buildings table holds only
those buildings; complete.json records how many ids FILE listed, how many the
dataset has, and the file's sha256. Line-effect runs are refused, since
their lines' draws are not cut down yet.

`--with-exact`, with `--range-atoms` and `--out`, writes the exact predictive
intervals beside the atoms, on the same draws, to compare the two.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from . import data, design, design_parts, explain, features, leaderboard, loo, model
from . import run as run_module
from .run import git, hardware

SUMMARIES = data.OUTPUT_ROOT / "summaries"
VERSION = "frontier-summary-v1"
SEED = 20260926
SPLITS = ("rows", "all")  # every held-out row's unit has rows in the fit
PROBABILITIES = (0.025, 0.5, 0.975)

# Display labels of the non-feature terms (feature groups are labelled by name).
TERM_LABELS = {
    "market": "Market reference",
    "bedroom_market_curve": "Bedroom-group market curve",
    "building": "Building",
    "building_drift": "Building over time",
    "line": "Line within building",
    "building_bedroom_premium": "Building bedroom premium",
    "building_feature_slopes": "Building size and bath slopes",
    "unit": "This unit",
    "price_basis": "Price basis",
    "unit label": "Unit label",
    "hvac": "HVAC",
    "facing": "Streets it looks onto",
    "noise": "Noise around the building",
    "relisting": "Time since its last listing",
    "previous listing": "Repricing of its last listing",
    "line facing": "Which way its line faces",
}
TERM_TEXT = {
    "neighbourhood": "West Village against Chelsea: the shift of every building's "
    "level in the West Village, before the building's own effect.",
    "relisting": "Time since the same apartment's previous listing (from that "
    "listing's date, so it includes its time on the market; only earlier listings "
    "count), or a flag for its first listing. A quick relist hints at a problem unit, a long gap at "
    "a renovation.",
    "previous listing": "How the same apartment's previous listing was repriced "
    "before this one was listed: how many times its price changed and, where the "
    "design has it, its last price over its first ask. A cut says the last ask was "
    "above what the apartment let for.",
    "line facing": "For an apartment whose own listings never say which way it faces: "
    "what the other apartments of its line (same building, same label letter or "
    "number) showed in earlier listings: the rear or a courtyard, the street, or both.",
    "location": "A smooth location surface over the map (Gaussian bumps about 250 "
    "m apart over the buildings' coordinates).",
    "transit": "The walk to the nearest subway station and the subway routes "
    "within a 10-minute walk, as of the listing's month.",
    "outdoor space": "Private outdoor space the listing's own record codes: a "
    "terrace, roof deck, garden, balcony or patio.",
    "rooms beyond bedrooms": "Rooms the listing's record counts beyond the "
    "bedrooms (0-1, 3, 4 or more, against 2, or not usable).",
    "market": "A reference apartment (one bedroom, one bath, every attribute at "
    "its reference level) in an average building that month: offset, "
    "intercept, market trend and calendar season.",
    "bedrooms": "Bedroom count, against a one-bedroom.",
    "bathrooms": "Full and half bathrooms, against one full bath.",
    "size": "Square feet against the typical size for the bedroom count, or "
    "size not stated.",
    "floor": "The floor, with steps above the 6th and 15th floors, and walk-up "
    "floors in buildings without an elevator.",
    "elevator": "Elevator in the building (or not stated).",
    "doorman": "Doorman: full-time, part-time, virtual, none or not stated.",
    "laundry": "Laundry in the unit (or not stated), against laundry in the "
    "building or none.",
    "hvac": "Central air or other heating and cooling, against not stated.",
    "pets": "The pet policy.",
    "views": "Views the listing states (city, park, water, skyline, ...).",
    "windows": "Window exposures the listing states.",
    "unit label": "Penthouse, garden and lower-level units, from the unit label.",
    "noise": "Noise complaints to 311 within about a block of the building in the "
    "year before the listing, street and nightlife (people, music, traffic, bars) "
    "and construction, each against Chelsea's average at the time.",
    "facing": "The streets the apartment's windows look onto (an avenue, a wide "
    "street such as 14th or 23rd, a side street, or the rear or a courtyard), and "
    "whether an apartment on floors 1-4 looks onto an avenue or a wide street, "
    "where traffic noise is loudest.",
    "price_basis": "A current capture's gross ask, against the first ask of a "
    "past advertisement.",
    "description": "Flags from the advertisement's own text (renovated, "
    "dishwasher, no fee, rent stabilized, ...), or no text.",
    "building era": "When the building was built (NYC MapPLUTO), against 1900-1929, "
    "or not usable.",
    "building size": "The building's height and number of apartments, the space "
    "per apartment and how densely the lot is built (MapPLUTO), or not usable.",
    "building class": "The building's type (MapPLUTO class): a walk-up, a "
    "condominium, a small mixed-use building of a few apartments over a store or "
    "office, or another type, against an elevator apartment building.",
    "building status": "Whether the building is a city landmark or in a historic "
    "district, and whether it has been altered since 2000 (NYC MapPLUTO); some "
    "versions of the model also use the 2015 flood map.",
    "building condition": "Hazardous housing-code violations the city (HPD) found "
    "in the building before the listing (the past year or the past five years, by "
    "version), per apartment and year: a few, or many, against none.",
    "bedroom_market_curve": "The bedroom group's own market-curve deviation.",
    "building": "The building's level against an average building.",
    "building_drift": "The building's own movement over time (walk or trend).",
    "line": "The unit's line (column) within its building.",
    "building_bedroom_premium": "The building's own bedroom slope.",
    "building_feature_slopes": "The building's own slopes on size and baths.",
    "unit": "The unit's own effect, from the unit's other listings only.",
}


# Kept draws indexed by building, or by unit, on the axis after the draws.
BUILDING_KEYS = (
    "building",
    "walk",
    "bedroom_slope",
    "fslope",
    "building_trend",
    "building_mean_month",
)
UNIT_KEYS = ("unit", "unit_drift")
# Kept draws on no building or unit axis, which `kept_subset` reads whole. It
# refuses any key in none of the three lists.
WHOLE_KEYS = (
    "alpha",
    "area_time",
    "area_time_scale",
    "bedroom_slope_scale",
    "bedroom_time",
    "bedroom_time_scale",
    "beta",
    "building_scale",
    "building_trend_scale",
    "fslope_scales",
    "line",
    "line_scale",
    "market_drift",
    "nu",
    "season",
    "season_daily_coef",
    "season_scale",
    "sigma",
    "trend",
    "trend_scale",
    "unit_drift_scale",
    "unit_nu",
    "unit_scale",
    "walk_nu",
    "walk_rho",
    "walk_scale",
)


def stand_ins(kept, n_buildings: int, n_units: int) -> set[str]:
    """The keys of BUILDING_KEYS and UNIT_KEYS in a whole run's kept draws
    that hold a one-element stand-in for a term the run leaves out."""
    sizes = {k: n_buildings for k in BUILDING_KEYS} | {k: n_units for k in UNIT_KEYS}
    return {
        k for k, size in sizes.items() if k in kept and kept[k].shape[1] == 1 != size
    }


def kept_subset(path: Path, buildings, units, n_buildings: int, n_units: int, block=20):
    """The kept draws of posterior.npz at `path`, as `explain.load_run` gives
    them ((draws, ...) float64), with the arrays of BUILDING_KEYS cut to the
    sorted building indexes `buildings` and those of UNIT_KEYS to `units`, and
    the set of stand-in keys (`stand_ins`), told apart by the archive's shapes
    since a cut array can be one element wide too. The cut arrays are read from
    the archive `block` draws at a time, so memory follows the subset."""
    import zipfile

    from numpy.lib import format as npy

    out, standing_in = {}, set()
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if not member.startswith("kept/"):
                continue
            key = member[len("kept/") : -len(".npy")]
            with archive.open(member) as fh:
                version = npy.read_magic(fh)
                header = (
                    npy.read_array_header_1_0
                    if version == (1, 0)
                    else npy.read_array_header_2_0
                )
                shape, fortran, dtype = header(fh)
                if key in BUILDING_KEYS:
                    index, size = np.asarray(buildings), n_buildings
                elif key in UNIT_KEYS:
                    index, size = np.asarray(units), n_units
                elif key in WHOLE_KEYS:
                    index = size = None
                else:
                    raise ValueError(f"{member} is in none of the summary's key lists")
                if index is not None and len(shape) >= 3 and shape[2] == 1 != size:
                    # A one-element stand-in for a term the run leaves out.
                    index = None
                    standing_in.add(key)
                if index is None:
                    order = "F" if fortran else "C"
                    value = np.frombuffer(fh.read(), dtype).reshape(shape, order=order)
                    out[key] = value.reshape(-1, *shape[2:]).astype(np.float64)
                    continue
                if fortran or dtype.hasobject or len(shape) < 3 or shape[2] != size:
                    raise ValueError(f"{member} is not (chains, blocks, {size}, ...)")
                draw = shape[2:]
                draws = shape[0] * shape[1]
                cut = np.empty((draws, len(index), *draw[1:]))
                per = int(np.prod(draw)) * dtype.itemsize
                for lo in range(0, draws, block):
                    n = min(block, draws - lo)
                    raw = fh.read(per * n)
                    if len(raw) != per * n:
                        raise ValueError(f"{member} ends early")
                    cut[lo : lo + n] = np.frombuffer(raw, dtype).reshape(n, *draw)[
                        :, index
                    ]
                out[key] = cut
    return out, standing_in


def cut_arrays(a: model.Arrays, index) -> model.Arrays:
    """Re-index the rows' buildings and units into kept draws cut to the sorted
    indexes `index.buildings` and `index.units` (`kept_subset`), in place."""
    a.building = np.searchsorted(index.buildings, a.building).astype(np.int32)
    a.unit = np.where(
        a.unit >= 0, np.searchsorted(index.units, np.maximum(a.unit, 0)), -1
    ).astype(np.int32)
    return a


def listed_rows(frame: pd.DataFrame, path: Path) -> tuple[np.ndarray, dict]:
    """A mask over rows: the buildings of the audit ids listed in the file at
    `path`, one a line; with a record of the listing."""
    text = Path(path).read_text()
    listed = {line.strip() for line in text.splitlines() if line.strip()}
    found = frame.audit_id.isin(listed).to_numpy()
    if not found.any():
        raise SystemExit(
            f"none of the {len(listed)} audit ids in {path} are in the dataset"
        )
    keep = frame.building.isin(frame.building[found]).to_numpy()
    record = {
        "listed": len(listed),
        "found": int(found.sum()),
        "rows": int(keep.sum()),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    return keep, record


def present_terms(config: model.ModelConfig, groups, line: bool) -> list[str]:
    """Contribution terms of a design in display order (terms the design does
    not have are identically zero and are left out)."""
    names = ["market", *dict.fromkeys(groups)]
    names += ["bedroom_market_curve"] if config.bedroom_time else []
    names += ["building"]
    names += ["building_drift"] if config.building_walk or config.building_trend else []
    names += ["line"] if line else []
    names += ["building_bedroom_premium"] if config.bedroom_slope else []
    names += ["building_feature_slopes"] if config.feature_slopes else []
    names += ["unit"] if config.units else []
    return names


def normalized_weights(log_w: np.ndarray) -> np.ndarray:
    """(draws, rows) log weights -> weights summing to 1 over draws."""
    w = np.exp(log_w - log_w.max(0, keepdims=True))
    return w / w.sum(0, keepdims=True)


def psis_log_weights(loglik):
    """(draws, rows) log densities -> Pareto-smoothed log importance weights
    proportional to 1 / p(y_i | draw), (draws, rows), and Pareto k per row."""
    from arviz_stats.base import array_stats

    # arviz_stats' psislw takes the log-likelihood and negates it internally.
    log_w, k = array_stats.psislw(np.asarray(loglik, float).T, axis=-1)
    return np.asarray(log_w).T, np.asarray(k, float)


def weighted_quantiles(values, weights, probabilities=PROBABILITIES):
    """values, weights: (draws, rows) -> (len(probabilities), rows): the
    smallest value whose cumulative weight reaches each probability."""
    order = np.argsort(values, axis=0)
    ordered = np.take_along_axis(values, order, axis=0)
    cumulative = np.cumsum(np.take_along_axis(weights, order, axis=0), axis=0)
    cumulative /= cumulative[-1:]
    cols = np.arange(values.shape[1])
    out = np.empty((len(probabilities), values.shape[1]))
    for q, p in enumerate(probabilities):
        index = np.minimum((cumulative < p).sum(0), values.shape[0] - 1)
        out[q] = ordered[index, cols]
    return out


def loo_unit_levels(y, rest, seg, n_seg, params, key, *, t_units, bed_group=None):
    """Leave-own-row-out unit levels for rows sorted into whole units.

    y: (rows,) log rent less offset; rest: (draws, rows) predictor without the
    unit terms; seg: (rows,) unit segments in [0, n_seg); params: dict of
    (draws,) arrays nu, sigma, unit_scale (and unit_nu for t_units).

    Returns (loglik, level), each (draws, rows): loglik is
    log p(y_i | theta_s, y_{u,-i}) with the unit level integrated, exactly as
    `loo.integrated_loglik`, and level one draw of the unit level from
    p(a | theta_s, y_{u,-i}) on the same grid, uniform within its cell.
    """
    import jax
    import jax.numpy as jnp
    from jax.scipy.special import logsumexp

    from .collect import student_t_logpdf

    lo, hi, n = loo.GRID
    z = jnp.linspace(lo, hi, n, dtype=jnp.float64)
    step = (hi - lo) / (n - 1)
    log_dz = math.log(step)
    ones = jnp.ones(y.shape[0])
    y = jnp.asarray(y)
    seg = jnp.asarray(seg)
    groups = jnp.asarray(
        np.zeros(y.shape[0], np.int32) if bed_group is None else bed_group
    )

    def one(args):
        rest_s, p, k = args
        # One residual scale, or (noise_by_bedrooms) each row's group's.
        sigma = p["sigma"][groups][:, None] if p["sigma"].ndim else p["sigma"]
        if t_units:
            log_wz = student_t_logpdf(z, jnp.maximum(p["unit_nu"], 1e-3), 1.0)
        else:
            log_wz = -0.5 * z * z - 0.5 * math.log(2 * math.pi)
        w = log_wz + log_dz
        ll = student_t_logpdf(
            (y - rest_s)[:, None] - p["unit_scale"] * z[None, :], p["nu"], sigma
        )  # (rows, grid)
        total = jax.ops.segment_sum(ll, seg, num_segments=n_seg)
        count = jax.ops.segment_sum(ones, seg, num_segments=n_seg)
        log_unit = logsumexp(total + w[None], axis=1)
        # The unit's other rows (none for a unit's only row: the prior).
        others = total[seg] - ll + w[None]
        log_rest = jnp.where(count[seg] == 1, 0.0, logsumexp(others, axis=1))
        k_cell, k_jitter = jax.random.split(k)
        cell = jax.random.categorical(k_cell, others, axis=1)
        jitter = jax.random.uniform(
            k_jitter, cell.shape, minval=-step / 2, maxval=step / 2
        )
        return log_unit[seg] - log_rest, p["unit_scale"] * (z[cell] + jitter)

    names = ["nu", "sigma", "unit_scale"] + (["unit_nu"] if t_units else [])
    p = {k: jnp.asarray(params[k]) for k in names}
    keys = jax.random.split(key, rest.shape[0])
    loglik, level = jax.lax.map(one, (jnp.asarray(rest), p, keys))
    return np.asarray(loglik), np.asarray(level)


# Posterior predictive intervals for the ask itself (Student-t noise included),
# as (name, lower, upper) probabilities.
PREDICTIVE = (("95", 0.025, 0.975), ("80", 0.10, 0.90))


def predictive_quantiles(
    total, sigma, nu, weights, probabilities, iterations=10, tolerance=1e-12
):
    """(len(probabilities), rows) quantiles of the posterior predictive of the
    log ask: the weighted mixture over draws of Student-t(nu_s) noise of scale
    sigma_s around total_s, the distribution `pit` evaluates. Per row, Newton
    steps on the mixture's CDF, kept inside a bracket that starts at the
    smallest and largest of the draws' own p-quantiles (the mixture's lies
    between them) and falls back to bisection when a step leaves it. A row
    stops once its CDF is within `tolerance` of p, so later steps evaluate
    only the rows still moving (on NB9 chunks rows stop after 4 to 7 steps).
    Rows whose CDF is still off by more than 1e-7 after `iterations` steps
    (few heavy draws far apart: Newton can cycle) are finished by bisection
    on their bracket.
    total, weights: (draws, rows); sigma: (draws, 1) or (draws, rows);
    nu: (draws,)."""
    from scipy.special import gammaln, stdtr, stdtrit

    sigma = np.broadcast_to(sigma, total.shape)
    nu_ = nu[:, None]
    # Student-t density constant per draw, over sigma: weights of the pdf.
    const = np.exp(gammaln((nu + 1) / 2) - gammaln(nu / 2)) / np.sqrt(nu * np.pi)
    wpdf = weights * const[:, None] / sigma
    out = np.empty((len(probabilities), total.shape[1]))
    for q, p in enumerate(probabilities):
        own = total + sigma * stdtrit(nu, p)[:, None]  # (draws, rows)
        lo, hi = own.min(0), own.max(0)
        x = (own * weights).sum(0)
        f = np.empty_like(x)
        moving = np.arange(total.shape[1])
        for step in range(iterations + 1):
            t, s_ = total[:, moving], sigma[:, moving]
            z = (x[moving][None] - t) / s_
            f[moving] = (stdtr(nu_, z) * weights[:, moving]).sum(0) - p
            if step == iterations:
                break
            fm, xm = f[moving], x[moving]
            d = (wpdf[:, moving] * (1 + z * z / nu_) ** (-(nu_ + 1) / 2)).sum(0)
            lm = np.where(fm < 0, xm, lo[moving])
            hm = np.where(fm < 0, hi[moving], xm)
            lo[moving], hi[moving] = lm, hm
            newton = xm - fm / np.maximum(d, 1e-300)
            inside = (newton >= lm) & (newton <= hm)
            xm = np.where(inside, newton, 0.5 * (lm + hm))
            going = np.abs(fm) >= tolerance
            x[moving[going]] = xm[going]
            moving = moving[going]
            if not len(moving):
                break
        slow = np.flatnonzero(np.abs(f) > 1e-7)
        if len(slow):
            a = np.where(f[slow] < 0, x[slow], lo[slow])
            b = np.where(f[slow] < 0, hi[slow], x[slow])
            x[slow] = _bisect(
                total[:, slow], sigma[:, slow], nu_, weights[:, slow], p, a, b
            )
        out[q] = x
    return out


# Range atoms per row and the noise tables (`apartments.site.ranges`).
RANGE_ATOMS = 64
NOISE_GRID = 4097
NOISE_SPAN = 60.0


def same_noise(scale, group_sigma, groups):
    """Whether each row's (draws, rows) or (draws, 1) residual scale is its
    group's column of `group_sigma`, so that the group's table in noise.json
    describes the row's noise. A model with row-level noise fails this."""
    scale = np.broadcast_to(scale, (group_sigma.shape[0], len(groups)))
    return bool(np.array_equal(scale, group_sigma[:, groups]))


def atom_columns(table):
    """The row table with the atom columns of a run with `--range-atoms` made
    parquet-ready: the rows of fallback chunks come out of the concat with NaN
    there and exact intervals instead, and get None and a missing group."""
    if "estimate_atoms" in table:
        table["estimate_atoms"] = [
            a if isinstance(a, np.ndarray) else None for a in table.estimate_atoms
        ]
        table["noise_group"] = table.noise_group.astype("Int64")
    return table


def range_atoms(total, weights, k=RANGE_ATOMS):
    """(k, rows) weighted quantiles of the total log rent at (i + 0.5) / k."""
    return weighted_quantiles(total, weights, (np.arange(k) + 0.5) / k)


def noise_tables(sigma, nu, grid=NOISE_GRID, span=NOISE_SPAN) -> dict:
    """noise.json's content: per group of sigma (draws, groups), the CDF of
    Student-t(nu_s) noise scaled by sigma_s,g, averaged over the draws."""
    from scipy.special import stdtr

    groups = {}
    for g in range(sigma.shape[1]):
        half = span * float(np.median(sigma[:, g]))
        e = np.linspace(-half, half, grid)
        cdf = np.empty(grid)
        for lo in range(0, grid, 512):
            z = e[lo : lo + 512, None] / sigma[None, :, g]
            cdf[lo : lo + 512] = stdtr(nu[None, :], z).mean(1)
        groups[str(g)] = {
            "lower": float(e[0]),
            "step": float(e[1] - e[0]),
            "cdf": [round(float(c), 10) for c in cdf],
        }
    return {"grid": grid, "span": span, "groups": groups}


def _bisect(total, sigma, nu_, weights, p, a, b, steps=50):
    """The mixture's p-quantile per row by bisection on the bracket [a, b]."""
    from scipy.special import stdtr

    for _ in range(steps):
        m = 0.5 * (a + b)
        below = (stdtr(nu_, (m[None] - total) / sigma) * weights).sum(0) < p
        a, b = np.where(below, m, a), np.where(below, b, m)
    return 0.5 * (a + b)


def _stats(prefix, values, weights, table):
    mean = (values * weights).sum(0)
    q = weighted_quantiles(values, weights)
    table[prefix] = mean
    table[f"{prefix}_lower_95"], table[f"{prefix}_upper_95"] = q[0], q[2]
    return mean, q


def row_table(
    sub,
    terms,
    log_w,
    pareto_k,
    fitted,
    sigma,
    nu,
    names,
    inputs,
    groups=None,
    with_exact=False,
):
    """One chunk's output rows. terms: the leave-own-row-out log terms
    (draws, rows); log_w: (draws, rows) log importance weights (0 = the
    posterior as is); fitted: (draws, rows) in-sample exp(mu); sigma: the
    residual scale, (draws, 1) or per row (draws, rows); groups: the rows'
    noise groups, to write range atoms in place of the predictive intervals,
    or beside them `with_exact`."""
    from scipy import stats

    weights = normalized_weights(log_w)
    dollars, rent = explain.decompose(terms)
    total = sum(terms.values())
    log_ask = np.log(sub.asking_rent.to_numpy())
    table = {
        "audit_id": sub.audit_id.to_numpy(),
        "unit_id": sub.unit_id.to_numpy(),
        "building": sub.building.to_numpy(),
        "period": sub.period.dt.strftime("%Y-%m-%d").to_numpy(),
        "asking_rent": sub.asking_rent.to_numpy(),
    }
    mean, q = _stats("estimate", rent, weights, table)
    table["estimate_median"] = q[1]
    table["residual_usd"] = table["asking_rent"] - mean
    table["residual_pct"] = table["asking_rent"] / mean - 1.0
    table["pareto_k"] = pareto_k
    cdf = stats.t.cdf((log_ask[None] - total) / sigma, nu[:, None])
    table["pit"] = (cdf * weights).sum(0)
    if groups is not None:
        table["noise_group"] = np.asarray(groups, dtype=np.int64)
        atoms = range_atoms(total, weights).T.astype(np.float32)
        table["estimate_atoms"] = list(atoms)
    if groups is None or with_exact:
        probabilities = [p for _, lo, hi in PREDICTIVE for p in (lo, hi)]
        pred = np.exp(predictive_quantiles(total, sigma, nu, weights, probabilities))
        for i, (name, _, _) in enumerate(PREDICTIVE):
            table[f"estimate_pred_lower_{name}"] = pred[2 * i]
            table[f"estimate_pred_upper_{name}"] = pred[2 * i + 1]
    flat = np.full_like(fitted, 1.0 / fitted.shape[0])
    _stats("fitted_rent", fitted, flat, table)
    for name in names:
        _stats(f"{name}_usd", dollars[name], weights, table)
    table["inputs"] = inputs
    return pd.DataFrame(table, index=sub.index)


def row_inputs(feats: features.Features, rows: np.ndarray) -> list[str]:
    values = feats.values[rows]
    return [
        json.dumps(
            {feats.names[j]: round(float(v[j]), 4) for j in np.flatnonzero(v)},
            separators=(",", ":"),
        )
        for v in values
    ]


def hash_score(values) -> np.ndarray:
    """Each value's place in [0, 1): the first 8 bytes of the sha256 of the
    value as a string, read as a number."""
    unique, index = np.unique(np.asarray(values).astype(str), return_inverse=True)
    score = np.array(
        [
            int.from_bytes(hashlib.sha256(b.encode()).digest()[:8], "big") / 2**64
            for b in unique
        ]
    )
    return score[index]


def building_sample(buildings: np.ndarray, fraction: float | None) -> np.ndarray:
    """A mask over rows, true where the row's building hash falls below
    `fraction` of the range; all true when `fraction` is None."""
    if fraction is None:
        return np.ones(len(buildings), dtype=bool)
    if not 0 < fraction <= 1:
        raise ValueError(f"the building fraction must be in (0, 1], got {fraction}")
    return hash_score(buildings) < fraction


RANGE_SAMPLE_ROWS = 2000
RANGE_SAMPLE_PER_GROUP = 200


def range_sample_rates(
    train_groups, n_groups, rows=RANGE_SAMPLE_ROWS, per_group=RANGE_SAMPLE_PER_GROUP
) -> np.ndarray:
    """(n_groups,) the share of each noise group's rows the range sample takes:
    `rows` over the training rows, or `per_group` over the group's training
    rows where that is higher, at most 1. A group with no training rows gets 1."""
    count = np.bincount(np.asarray(train_groups), minlength=n_groups)
    rate = np.ones(n_groups)
    has = count > 0
    rate[has] = np.minimum(1.0, np.maximum(rows / count.sum(), per_group / count[has]))
    return rate


class RangeSample:
    """The draws behind the predictive intervals of the rows `summarize` picks
    for range-sample.npz, gathered chunk by chunk."""

    def __init__(self, rates: np.ndarray):
        self.rates, self.parts = rates, []

    def add(self, audit_id, group, in_fit, terms, log_w, sigma):
        """One chunk: its rows' audit ids, noise groups and in-fit flags; its
        terms and log weights (draws, rows); sigma (draws, 1) or (draws, rows)."""
        group = np.asarray(group)
        pick = np.flatnonzero(hash_score(audit_id) < self.rates[group])
        if not len(pick):
            return
        total = sum(np.asarray(v)[:, pick] for v in terms.values())
        sigma = np.broadcast_to(np.asarray(sigma), np.shape(log_w))[:, pick]
        self.parts.append(
            {
                "audit_id": np.asarray(audit_id).astype(str)[pick],
                "group": group[pick],
                "in_fit": np.full(len(pick), in_fit),
                "total": total.T.astype(np.float32),
                "weights": normalized_weights(log_w[:, pick]).T.astype(np.float32),
                "sigma": sigma.T.astype(np.float32),
            }
        )

    def arrays(self, nu) -> dict:
        draws = len(nu)
        empty = {
            "audit_id": np.array([], dtype=str),
            "group": np.array([], dtype=int),
            "in_fit": np.array([], dtype=bool),
            **{
                k: np.empty((0, draws), np.float32)
                for k in ("total", "weights", "sigma")
            },
        }
        out = {
            k: np.concatenate([v] + [p[k] for p in self.parts])
            for k, v in empty.items()
        }
        out["nu"] = np.asarray(nu, dtype=np.float32)
        return out


def summary_rows(
    heldout: np.ndarray, keep: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Frame positions of the kept rows in the fit and of the kept held-out rows."""
    return np.flatnonzero(~heldout & keep), np.flatnonzero(heldout & keep)


def chunk_rows(draws: int) -> int:
    """Rows per batch of whole units, so draws x rows x terms stays near 1 GB."""
    return int(min(1024, max(256, 2_250_000 // draws)))


def check_run(result):
    """Refuse runs whose held-out rows could belong to units with no rows in
    the fit, and feature sources or data-rule files that differ now from the
    run's record: the files read today (`run.feature_sources`,
    `data.RULE_SOURCES`), not the paths recorded then."""
    if result["split"] not in SPLITS:
        raise SystemExit(
            f"{result['split']}-split runs are not summarized (splits: {SPLITS})"
        )
    now = run_module.feature_sources(result["feature_set"])
    for key, src in result.get("feature_sources", {}).items():
        if key not in now or now[key]["sha256"] != src["sha256"]:
            raise SystemExit(f"feature source {key} differs from the run's record")
    data.recorded_rules(result)
    name = result.get("model", {}).get("name")
    if name in model.MODELS and model.MODELS[name].area_time:
        # The building tables, kit and rent map have no neighbourhood curve yet.
        raise SystemExit("area_time runs are not summarized yet")


# A new unit's level is at most this many unit scales from zero.
UNIT_CLIP = 40.0


def new_unit_levels(params, n_rows, key, *, t_units):
    """(draws, rows) unit levels from the unit prior: for held-out rows of
    units with no rows in the fit (a row-dropping data rule can remove every
    training row of a held-out row's unit), as for a new apartment."""
    import jax

    draws = np.asarray(params["unit_scale"]).shape[0]
    if t_units:
        nu = np.maximum(np.asarray(params["unit_nu"]), 1e-3)[:, None]
        z = np.asarray(jax.random.t(key, nu, (draws, n_rows)))
    else:
        z = np.asarray(jax.random.normal(key, (draws, n_rows)))
    # exp of a Student-t level has no mean: one draw far out in the tail made a
    # held-out row's estimate $2 trillion (2026-10-08). Clip as the site's
    # estimate form does (`apartments.site.estimate.UNIT_CLIP`).
    z = np.clip(z, -UNIT_CLIP, UNIT_CLIP)
    return np.asarray(params["unit_scale"])[:, None] * z


def verify_run(result, frame, heldout, prep, run_dir, post_units, post_buildings):
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit("dataset differs from the run's recorded dataset")
    recorded = np.load(run_dir / "heldout.npz", allow_pickle=True)["audit_id"]
    if not np.array_equal(frame.audit_id.to_numpy()[heldout], recorded):
        raise SystemExit("held-out rows differ from the run's recorded rows")
    if not (
        np.array_equal(prep.units, post_units)
        and np.array_equal(prep.buildings, post_buildings)
    ):
        raise SystemExit("units or buildings differ from the run's saved draws")


def gate(result, run_dir) -> dict:
    g_max, g_pass, g_method = leaderboard.group_gate(dict(result, _dir=run_dir))
    d = result["diagnostics"]
    return {
        "passes": bool(d["passes"] and g_pass),
        "max_rhat": d["max_rhat"],
        "min_ess": d["min_ess"],
        "divergences": d.get("divergences"),
        "group_rhat_max": g_max,
        "group_rhat_method": g_method,
    }


# Environment for the row-table workers: CPU JAX (they get numpy only, and the
# GPU stays with the main process) and one BLAS thread each, as `_newbuilding`.
WORKER_ENV = {
    "JAX_PLATFORMS": "cpu",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}
# The frame columns `row_table` reads.
ROW_COLUMNS = ["audit_id", "unit_id", "building", "period", "asking_rent"]


class RowTables:
    """`row_table` for each chunk `summarize` hands it, in this process with one
    worker, or else in a pool of that many spawned processes: the predictive
    intervals and weighted quantiles run single-threaded in scipy and numpy and
    take most of a large summary's time (2026-10-17: a 1.6M-row summary passed
    4 hours on one core). At most two chunks per worker wait in the pool, so
    memory stays near that many chunks. Every 100 chunks it logs its progress.

    Use it as a context manager. While the pool is open, WORKER_ENV is set in
    this process's environment, since spawned workers start on demand and read
    it at their first import of JAX; this process read its JAX settings at
    import, so they stay as they were. On an error the pool drops its queued
    chunks."""

    def __init__(self, workers: int = 1):
        self.workers, self.done, self.pending = workers, [], []
        self.pool, self.started, self.chunks = None, time.perf_counter(), 0
        self.saved_env = {}

    def __enter__(self):
        if self.workers > 1:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor

            self.saved_env = {k: os.environ.get(k) for k in WORKER_ENV}
            os.environ.update(WORKER_ENV)
            self.pool = ProcessPoolExecutor(
                self.workers, mp_context=multiprocessing.get_context("spawn")
            )
        return self

    def __exit__(self, kind, error, trace):
        if self.pool is not None:
            self.pool.shutdown(wait=kind is None, cancel_futures=kind is not None)
            self.pool = None
        for k, v in self.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False

    def add(self, sub, terms, *rest):
        sub = sub[ROW_COLUMNS]
        if self.pool is None:
            self.done.append(row_table(sub, terms, *rest))
        else:
            while len(self.pending) >= 2 * self.workers:
                self.done.append(self.pending.pop(0).result())
            terms = {k: np.asarray(v) for k, v in terms.items()}
            self.pending.append(self.pool.submit(row_table, sub, terms, *rest))
        self.chunks += 1
        if self.chunks % 100 == 0:
            print(
                f"{self.chunks} chunks, {time.perf_counter() - self.started:.0f} s",
                flush=True,
            )

    def collect(self) -> list[pd.DataFrame]:
        self.done += [f.result() for f in self.pending]
        self.pending = []
        return self.done


def summarize(
    name: str,
    allow_failing: bool = False,
    workers: int = 1,
    buildings: float | None = None,
    range_sample: bool = False,
    with_atoms: bool = False,
    rows: Path | None = None,
    with_exact: bool = False,
):
    import jax

    jax.config.update("jax_enable_x64", True)
    if rows is None:
        run_dir, result, kept = explain.load_run(name)
    else:
        # The draws are read below, cut to the listed rows' buildings.
        run_dir = explain.RUNS / name
        result, kept = json.loads((run_dir / "result.json").read_text()), None
    gate_status = gate(result, run_dir)
    if not gate_status["passes"] and not allow_failing:
        raise SystemExit(f"{name} fails the convergence gate: {gate_status}")
    check_run(result)
    config = model.MODELS[result["model"]["name"]]
    frame = data.load(Path(result["dataset"]))
    frame, heldout, feats, prep = design.prepared(
        frame, result["split"], data.recorded_rules(result), result["feature_set"]
    )
    post = np.load(run_dir / "posterior.npz", allow_pickle=True)
    verify_run(result, frame, heldout, prep, run_dir, post["units"], post["buildings"])
    # Made from the whole design, also when only some rows are summarized.
    design_set = (
        design_parts.from_design(frame, heldout, feats, prep),
        data.rows_sha256(frame, heldout),
    )
    index = rows_record = None
    if rows is None:
        keep = building_sample(frame.building.to_numpy(), buildings)
    else:
        keep, rows_record = listed_rows(frame, rows)
        building_of = pd.Index(prep.buildings).get_indexer(frame.building[keep])
        unit_of = pd.Index(prep.units).get_indexer(frame.unit_id[keep])
        index = SimpleNamespace(
            buildings=np.unique(building_of[building_of >= 0]),
            units=np.unique(unit_of[unit_of >= 0]),
        )
        kept, standing_in = kept_subset(
            run_dir / "posterior.npz",
            index.buildings,
            index.units,
            len(prep.buildings),
            len(prep.units),
        )
        if np.any(kept.get("line_scale", 0) > 0):
            raise SystemExit("--rows does not cut down line effects yet")
    if rows is None:
        standing_in = stand_ins(kept, len(prep.buildings), len(prep.units))
    if "unit_drift" in kept and "unit_drift" not in standing_in:
        raise SystemExit("unit-drift designs are not supported (drift not integrated)")
    draws = kept["alpha"].shape[0]
    t_units = bool((kept.get("unit_nu", np.zeros(draws)) > 0).all())
    line = bool(np.any(kept.get("line_scale", 0) > 0))
    names = present_terms(config, feats.groups, line)
    fslope_index = [feats.names.index(n) for n in config.feature_slopes]
    params = {k: kept[k] for k in ("nu", "sigma", "unit_scale", "unit_nu") if k in kept}
    train_idx, held_idx = summary_rows(heldout, keep)
    if not len(train_idx):
        raise SystemExit(f"the {buildings} sample of buildings has no rows in the fit")
    sigma, nu = kept["sigma"], kept["nu"]
    n_groups = sigma.shape[1] if sigma.ndim == 2 else 1
    sample = None
    if range_sample:
        # prep.train holds the rows in the fit in frame order; the rates count
        # only those the building sample keeps.
        train_groups = np.asarray(model.noise_group(n_groups, prep.train))
        if len(train_groups) != (~heldout).sum():
            raise AssertionError("prep.train must hold the frame's rows in the fit")
        train_groups = train_groups[keep[~heldout]]
        sample = RangeSample(range_sample_rates(train_groups, n_groups))

    def row_scale(a):
        """(draws, rows) residual scales, or (draws, 1) with one scale."""
        return (
            sigma[:, model.noise_group(sigma.shape[1], a)]
            if sigma.ndim == 2
            else sigma[:, None]
        )

    group_sigma = sigma if sigma.ndim == 2 else sigma[:, None]
    noise = noise_tables(group_sigma, nu) if with_atoms else None
    fallback_chunks = 0

    def atom_groups(a):
        """The rows' noise groups when each row's scale is its group's scale
        in noise.json, else None (the chunk gets the exact intervals)."""
        nonlocal fallback_chunks
        if not with_atoms:
            return None
        groups = np.asarray(model.noise_group(n_groups, a))
        if same_noise(row_scale(a), group_sigma, groups):
            return groups
        fallback_chunks += 1
        return None

    key = jax.random.PRNGKey(SEED)

    def terms_for(mask):
        a = model.row_arrays(prep, frame, mask)
        if index is not None:
            cut_arrays(a, index)
        terms = explain.log_terms(
            kept,
            a,
            feats.groups,
            model.walk_spacing(config),
            config.bedroom_time,
            config.bedroom_slope,
            prep.offset,
            fslope_index,
            unit_line=prep.unit_line,
        )
        return a, terms

    with RowTables(workers) as tables:
        # Rows in the fit, sorted into whole units.
        unit_of = pd.Index(prep.units).get_indexer(frame.unit_id.to_numpy()[train_idx])
        order = np.argsort(unit_of, kind="stable")
        rows_sorted, units_sorted = train_idx[order], unit_of[order]
        chunk = chunk_rows(draws)
        for lo, hi in loo.unit_chunks(units_sorted, chunk):
            rows = np.sort(rows_sorted[lo:hi])  # frame order, as row_arrays returns
            mask = np.zeros(len(frame), dtype=bool)
            mask[rows] = True
            a, terms = terms_for(mask)
            fitted = np.exp(sum(terms.values()))
            rest = sum(v for k, v in terms.items() if k not in loo.UNIT_TERMS)
            _, seg = np.unique(a.unit, return_inverse=True)
            pad = chunk - len(rows)
            # Pad to a fixed shape (one compile); padded rows are their own units.
            key, sub_key = jax.random.split(key)
            loglik, level = loo_unit_levels(
                np.r_[a.y, np.zeros(pad)],
                np.concatenate([rest - prep.offset, np.zeros((draws, pad))], axis=1),
                np.r_[seg, seg.max() + 1 + np.arange(pad)],
                chunk,
                params,
                sub_key,
                t_units=t_units,
                bed_group=np.r_[
                    model.noise_group(n_groups, a), np.zeros(pad, a.bed_group.dtype)
                ],
            )
            loglik, level = loglik[:, : len(rows)], level[:, : len(rows)]
            terms["unit"] = level
            log_w, k = psis_log_weights(loglik)
            if sample is not None:
                sample.add(
                    frame.audit_id.to_numpy()[rows],
                    model.noise_group(n_groups, a),
                    True,
                    terms,
                    log_w,
                    row_scale(a),
                )
            tables.add(
                frame.loc[mask],
                terms,
                log_w,
                k,
                fitted,
                row_scale(a),
                nu,
                names,
                row_inputs(feats, rows),
                atom_groups(a),
                with_exact,
            )
        # Held-out rows: the fit never saw them; the posterior is the estimate.
        for rows in np.array_split(held_idx, max(1, math.ceil(len(held_idx) / chunk))):
            if not len(rows):
                continue
            mask = np.zeros(len(frame), dtype=bool)
            mask[rows] = True
            a, terms = terms_for(mask)
            unseen = np.asarray(a.unit) < 0
            if unseen.any():
                key, sub_key = jax.random.split(key)
                terms["unit"] = np.asarray(terms["unit"], dtype=float).copy()
                terms["unit"][:, unseen] = new_unit_levels(
                    params, int(unseen.sum()), sub_key, t_units=t_units
                )
            fitted = np.exp(sum(terms.values()))
            if sample is not None:
                sample.add(
                    frame.audit_id.to_numpy()[rows],
                    model.noise_group(n_groups, a),
                    False,
                    terms,
                    np.zeros((draws, len(rows))),
                    row_scale(a),
                )
            tables.add(
                frame.loc[mask],
                terms,
                np.zeros((draws, len(rows))),
                np.full(len(rows), np.nan),
                fitted,
                row_scale(a),
                nu,
                names,
                row_inputs(feats, rows),
                atom_groups(a),
                with_exact,
            )
        parts = tables.collect()
    table = atom_columns(pd.concat(parts).sort_index())
    if len(table) != keep.sum() or table.audit_id.duplicated().any():
        raise AssertionError("every summarized row must appear exactly once")
    heldout = heldout[keep]
    table.insert(5, "in_fit", ~heldout)
    fit_rows = np.bincount(prep.train.unit, minlength=len(prep.units))
    unit_index = pd.Index(prep.units).get_indexer(table.unit_id)
    table.insert(6, "unit_fit_rows", np.where(unit_index >= 0, fit_rows[unit_index], 0))
    table.insert(
        8, "estimate_method", np.where(heldout, "heldout", "psis").astype(object)
    )
    return {
        "result": result,
        "run_dir": run_dir,
        "gate": gate_status,
        "design_parts": design_set,
        "draws": draws,
        "names": names,
        "rows": table,
        "market": market_table(kept, prep),
        "buildings": building_table(
            kept, prep, standing_in, None if index is None else index.buildings
        ),
        "coefficients": coefficient_table(kept, feats),
        "k_threshold": loo.k_threshold(draws),
        "buildings_fraction": buildings,
        "rows_sample": rows_record,
        **({"range_sample": sample.arrays(nu)} if sample is not None else {}),
        **(
            {"noise": noise, "range_atoms_fallback_chunks": fallback_chunks}
            if with_atoms
            else {}
        ),
    }


def _summary(x, axis=0):
    """Median over draws and the 95% interval (medians, not means: the Fable
    review framework, Ben 2026-10-10)."""
    q = np.quantile(x, PROBABILITIES, axis=axis)
    return q[1], q[0], q[2]


def market_table(kept, prep) -> pd.DataFrame:
    """The market reference rent per month: a reference apartment in an
    average building (the `market` term), with and without the season."""
    months = np.arange(len(prep.periods))
    calendar = prep.periods.month.to_numpy() - 1
    trend = prep.offset + kept["alpha"][:, None] + kept["trend"][:, months]
    out = {"period": prep.periods.strftime("%Y-%m-%d")}
    out["reference_rent"] = np.median(
        np.exp(trend + kept["season"][:, calendar]), axis=0
    )
    mid, lo, hi = _summary(np.exp(trend))
    out["reference_rent_deseasoned"] = mid
    out["reference_rent_deseasoned_lower_95"] = lo
    out["reference_rent_deseasoned_upper_95"] = hi
    return pd.DataFrame(out)


def building_table(kept, prep, standing_in, index=None) -> pd.DataFrame:
    """Per building of the run, or of the building indexes `index` that the
    kept draws were cut to (`kept_subset`). A term with a stand-in in
    `standing_in` gets no column."""
    rows = np.bincount(prep.train.building, minlength=len(prep.buildings))
    if index is None:
        index = np.arange(len(prep.buildings))
    out = {"building": prep.buildings[index], "fit_rows": rows[index]}
    for key, label in (
        ("building", "level_pct"),
        ("building_trend", "trend_pct_per_year"),
    ):
        if key not in kept or key in standing_in:
            continue
        log_value = kept[key]
        pct = 100.0 * np.expm1(log_value)
        mid, lo, hi = _summary(pct)
        out[label], out[f"{label}_lower_95"], out[f"{label}_upper_95"] = mid, lo, hi
    return pd.DataFrame(out)


def coefficient_table(kept, feats: features.Features) -> pd.DataFrame:
    pct = 100.0 * np.expm1(kept["beta"])
    mid, lo, hi = _summary(pct)
    return pd.DataFrame(
        {
            "feature": feats.names,
            "group": feats.groups,
            "pct": mid,
            "pct_lower_95": lo,
            "pct_upper_95": hi,
            "probability_positive": (kept["beta"] > 0).mean(0),
        }
    )


# The neighbourhood term when the design has more than one neighbourhood column
# (Greenwich Village beside the West Village, `features.greenwich_v1`, and
# Flatiron + Gramercy Park, `features.hood_v1`, or Flatiron and Gramercy Park,
# `features.hoods_v1`).
NEIGHBOURHOODS_TEXT = (
    "Each neighbourhood against Chelsea ({hoods}): the shift of every building's "
    "level there, before the building's own effect."
)
OTHER_HOODS = (
    "the West Village",
    "Greenwich Village",
    "Flatiron + Gramercy Park",
    "Flatiron",
    "Gramercy Park",
)


def terms_record(names, columns=()) -> list[dict]:
    """Label and description of each term; `columns` (the design's feature
    names) picks the neighbourhood text for three neighbourhoods."""
    text = dict(TERM_TEXT)
    if "Greenwich Village" in columns:
        hoods = [h for h in OTHER_HOODS if h.removeprefix("the ") in columns]
        text["neighbourhood"] = NEIGHBOURHOODS_TEXT.format(hoods=", ".join(hoods))
    return [
        {
            "name": n,
            "label": TERM_LABELS.get(n, n.replace("_", " ").capitalize()),
            "description": text.get(n, f"Listing attributes ({n})."),
        }
        for n in names
    ]


def loo_score(run: str) -> dict | None:
    """The run's recorded PSIS-LOO score (the newest), if any."""
    found = sorted(
        loo.LOO_ROOT.glob(f"{run}-*/result.json"), key=lambda p: p.stat().st_mtime
    )
    records = [json.loads(p.read_text()) for p in found]
    records = [r for r in records if r.get("source_run") == run]
    if not records:
        return None
    r = records[-1]
    return {
        "commit": r["commit"],
        "elpd_loo": r["elpd_loo"],
        "elpd_loo_se": r["elpd_loo_se"],
        "pareto_k": r["pareto_k"],
    }


def write(out: dict, out_dir: Path, commit: str, seconds: float) -> Path:
    tmp = out_dir.with_name(out_dir.name + ".tmp")
    tmp.mkdir(parents=True, exist_ok=False)
    out["rows"].to_parquet(tmp / "rows.parquet", index=False)
    out["market"].to_parquet(tmp / "market.parquet", index=False)
    out["buildings"].to_parquet(tmp / "buildings.parquet", index=False)
    out["coefficients"].to_parquet(tmp / "coefficients.parquet", index=False)
    if "range_sample" in out:
        np.savez_compressed(tmp / "range-sample.npz", **out["range_sample"])
    if "noise" in out:
        (tmp / "noise.json").write_text(json.dumps(out["noise"], separators=(",", ":")))
    (tmp / "terms.json").write_text(
        json.dumps(
            terms_record(out["names"], out["coefficients"].feature.tolist()), indent=2
        )
    )
    result = out["result"]
    parts_record = None
    if "design_parts" in out:
        design_set, design_rows_sha256 = out["design_parts"]
        parts_record = design_parts.write(
            design_set,
            tmp / design_parts.FILE,
            result,
            design_rows_sha256,
        )
    rule_files = {}
    for rule in data.recorded_rules(result):
        # Only the rules that drop rows have per-row decisions the site lists
        # (the alias table of unit-labels-v2 and the corrections keep every row).
        if rule in data.DROPPING_RULES:
            name = f"data-rule-{rule}.jsonl"
            shutil.copyfile(data.RULE_SOURCES[rule], tmp / name)
            rule_files[rule] = name
    rows = out["rows"]
    k = rows.pareto_k.to_numpy()
    record = {
        "version": VERSION,
        "run": result["name"],
        "run_commit": result["commit"],
        "commit": commit,
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "seconds": seconds,
        "hardware": hardware(),
        "dataset": result["dataset"],
        "dataset_observations_sha256": result["dataset_observations_sha256"],
        "data_rules": result.get("data_rules", []),
        "data_rule_sources": result.get("data_rule_sources", {}),
        "data_rule_files": rule_files,
        "feature_set": result["feature_set"],
        "feature_sources": result.get("feature_sources", {}),
        "model": result["model"],
        "split": result["split"],
        "sampler": result.get("sampler"),
        "fit_seconds": result["seconds"]["fit_total"],
        "fit_hardware": result["hardware"].get("gpu") or result["hardware"]["cpu"],
        "fit_started_at": result.get("started_at"),
        "draws": out["draws"],
        "gate": out["gate"],
        "psis_loo": loo_score(result["name"]),
        "rows": len(rows),
        "rows_in_fit": int(rows.in_fit.sum()),
        "estimate_pareto_k": {
            "threshold": out["k_threshold"],
            "over_threshold": int(np.nansum(k > out["k_threshold"])),
            "max": float(np.nanmax(k)),
        },
        "terms": out["names"],
        **({"design_parts": parts_record} if parts_record else {}),
        **(
            {"buildings_fraction": out["buildings_fraction"]}
            if out.get("buildings_fraction") is not None
            else {}
        ),
        **(
            {"rows_sample": out["rows_sample"]}
            if out.get("rows_sample") is not None
            else {}
        ),
        **(
            {
                "range_atoms": RANGE_ATOMS,
                "range_atoms_fallback_chunks": out["range_atoms_fallback_chunks"],
            }
            if "noise" in out
            else {}
        ),
        "files": {p.name: data.sha256(p) for p in sorted(tmp.iterdir()) if p.is_file()},
    }
    (tmp / "complete.json").write_text(json.dumps(record, indent=2))
    tmp.rename(out_dir)
    return out_dir


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run")
    parser.add_argument(
        "--allow-failing",
        action="store_true",
        help="summarize a run that fails the convergence gate (recorded)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="processes for the per-chunk row tables (each holds about two chunks)",
    )
    parser.add_argument(
        "--buildings",
        type=float,
        help="summarize only this fraction of buildings, sampled by id hash (needs --out)",
    )
    parser.add_argument(
        "--rows",
        type=Path,
        help="summarize only the buildings of the audit ids in this file, one a line "
        "(needs --out)",
    )
    parser.add_argument(
        "--out", type=Path, help="bundle directory (only with --buildings or --rows)"
    )
    parser.add_argument(
        "--range-sample",
        action="store_true",
        default=os.environ.get("FRONTIER_RANGE_SAMPLE") == "1",
        help="also write range-sample.npz (default with FRONTIER_RANGE_SAMPLE=1)",
    )
    parser.add_argument(
        "--range-atoms",
        action="store_true",
        default=os.environ.get("FRONTIER_RANGE_ATOMS") == "1",
        help="write range atoms and noise.json in place of the predictive "
        "intervals (default with FRONTIER_RANGE_ATOMS=1)",
    )
    parser.add_argument(
        "--with-exact",
        action="store_true",
        help="with --range-atoms and --out, also write the exact predictive intervals",
    )
    args = parser.parse_args(argv)
    if args.buildings is not None and args.rows is not None:
        parser.error("--buildings and --rows don't go together")
    if (args.buildings is None and args.rows is None) != (args.out is None):
        parser.error("--out goes with --buildings or --rows")
    if args.with_exact and not args.range_atoms:
        parser.error("--with-exact needs --range-atoms")
    if args.with_exact and args.out is None:
        parser.error("--with-exact needs --out")
    if args.buildings is not None and not 0 < args.buildings <= 1:
        parser.error("--buildings must be in (0, 1]")
    if args.out is not None and args.out.resolve().is_relative_to(SUMMARIES.resolve()):
        parser.error("--out must be outside the summaries directory")
    dirty = git("status", "--porcelain")
    if dirty:
        raise SystemExit(f"Refusing to run on a dirty working tree:\n{dirty}")
    commit = git("rev-parse", "HEAD")
    out_dir = args.out or SUMMARIES / f"{args.run}-{commit[:7]}"
    if (out_dir / "complete.json").exists():
        raise SystemExit(f"{out_dir} exists")
    t0 = time.perf_counter()
    out = summarize(
        args.run,
        args.allow_failing,
        args.workers,
        args.buildings,
        args.range_sample,
        args.range_atoms,
        args.rows,
        args.with_exact,
    )
    path = write(out, out_dir, commit, time.perf_counter() - t0)
    rows = out["rows"]
    print(
        f"wrote {path}: {len(rows)} rows ({int(rows.in_fit.sum())} in the fit), "
        f"{out['draws']} draws, {time.perf_counter() - t0:.0f} s",
        flush=True,
    )


if __name__ == "__main__":
    main()
