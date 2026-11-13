"""L1, the building model with a noise scale for each lease phase
(`rentfrontier.drift_building_phase`), with a path in time for each market segment around the
citywide walk.

L1 moves every ask in the city along one weekly walk. In S1 of the causal screens
(`docs/notes/causal-screens-2026-11-13.md`), studios, family units, Manhattan and the other
boroughs went through 2020 to 2023 on paths of their own. A unit's level carries its segment's
gap at one date, so a gap that opens and closes leaves the unit's ads above its level in some
years and below it in others. Here a segment is a bedroom group (studio, 1, 2, 3+) in a zone
(Manhattan, outer), eight in all, and each segment's path is piecewise linear between the
starts of calendar quarters.

For a row i in segment s_i at time t_i, and h_j(t) the hat weight of quarter start j (the
weights of the two quarter starts around a row sum to 1), this design adds a column for each
segment k and quarter start j:

    x_kj(i) = h_j(t_i) * (1[s_i = k] - p_kj),

with p_kj the share of segment k among the rows weighted by h_j, over all the frame's rows. A
row's mean gains sum_j h_j(t_i) * (delta_{s_i,j} - sum_k p_kj delta_kj): its segment's path
less the share-weighted mean of the paths, so the citywide walk keeps the market's average and
each segment's path holds its deviation from it. A row's columns come from its date, its
bedroom group and its site alone, so building a held-out row's columns uses no rent.

Each segment's coefficients take a Gaussian process prior over the quarter starts, with a
squared exponential covariance given a value of 0 at 2024-01-01: a unit's level holds its
segment's gap there, and the path moves it in other years. The squared amplitude has an
InvGamma(SEG_AMP) prior and the log lengthscale in years a Normal(SEG_LS) prior. The sampler
draws the coefficients with the design's other global columns, and the processes' amplitudes
and lengthscales with the floor curves'.

    python -m rentfrontier.run --model drift-building-phase-segment --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import sys

import numpy as np
import pandas as pd

from . import drift, drift_building_phase, two_zone
from .drift_building_phase import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    EDGES,
    GROUPS,
    HYP,
    KEPT,
    LEVEL_DOF,
    PHASES,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    make_sampler,
    months_since_previous,
    phase_index,
    site_rows,
    site_zone,
    split_index,
    subset,
    wave_matrix,
    years,
)

NAME = "drift-building-phase-segment"
# The bedroom groups of `b0.Design.group`, in order.
BEDS = ("studio", "1br", "2br", "3br+")
# The date at which every segment's path is held at 0 by its prior.
REFERENCE = pd.Timestamp("2024-01-01")
# InvGamma prior of a path's squared amplitude: a median amplitude of about 2% in log rent.
SEG_AMP = (2.0, 7e-4)
# Normal prior of a path's log lengthscale in years: a median of a year.
SEG_LS = (0.0, 0.5)
YEAR_DAYS = 365.25


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """L1's design of `frame`, with each segment's path columns."""
    return segment_paths(drift_building_phase.design(frame, start, held=held, **kw))


def segment_index(d: Design) -> np.ndarray:
    """Each row's segment, its zone's place in `d.surfaces` times len(BEDS) plus its bedroom
    group."""
    return site_zone(d)[d.site] * len(BEDS) + d.group


def segment_names(d: Design) -> list[str]:
    """The segments' names, `zone:beds`, in `segment_index` order."""
    return [f"{s['name']}:{b}" for s in d.surfaces for b in BEDS]


def quarter_starts(d: Design) -> pd.DatetimeIndex:
    """The calendar quarter starts from the last one on or before the grid start to the first
    one on or after the design's last row."""
    t = years(d)
    last = d.start + pd.Timedelta(days=float(t.max()) * YEAR_DAYS)
    first = pd.Timestamp(d.start).to_period("Q").start_time
    end = pd.Timestamp(last).to_period("Q").start_time
    if end < last:
        end = (pd.Timestamp(last).to_period("Q") + 1).start_time
    return pd.date_range(first, end, freq="QS")


def hat_weights(t: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """The (rows, knots) weights of linear interpolation at times `t` between the increasing
    `knots`, which bracket every t."""
    j = np.clip(np.searchsorted(knots, t, side="right") - 1, 0, len(knots) - 2)
    w = (t - knots[j]) / (knots[j + 1] - knots[j])
    H = np.zeros((len(t), len(knots)))
    rows = np.arange(len(t))
    H[rows, j] = 1 - w
    H[rows, j + 1] = w
    return H


def path_design(d: Design, knots: np.ndarray, labels: list[str]) -> Design:
    """`d` with the centered hat columns of the segments at `knots`, in years from the grid
    start, named `seg:{segment}:{label}` segment by segment in `segment_index` order.

    A knot with rows of a single segment, or of none, centers to 0 on every row, so its columns
    are left out, as `building_zones_kitchen_sink.append` leaves out a column with no rows set.
    Each segment's columns are built twice: a first pass finds the columns to keep, and a
    second fills them into the combined array. The host then holds the design once, beside a
    single segment's columns. On L1's data the combined array takes about 10 GB."""
    H = hat_weights(years(d), knots)
    seg = segment_index(d)
    segments = segment_names(d)
    weight = H.sum(axis=0)
    share = np.stack([H[seg == k].sum(axis=0) for k in range(len(segments))], axis=1)
    share /= np.where(weight > 0, weight, 1.0)[:, None]

    def block(k):
        b = H * ((seg == k)[:, None] - share[:, k])
        b[np.abs(b) < 1e-12] = 0.0
        return b

    names = [f"seg:{s}:{t}" for s in segments for t in labels]
    set_rows = np.concatenate(
        [(block(k) != 0).sum(axis=0) for k in range(len(segments))]
    )
    have = set(d.names)
    keep = [j for j, n in enumerate(names) if n not in have and set_rows[j] > 0]
    x = np.empty((len(H), d.x.shape[1] + len(keep)))
    x[:, : d.x.shape[1]] = d.x
    at = d.x.shape[1]
    for k in range(len(segments)):
        mine = [j - k * len(labels) for j in keep if j // len(labels) == k]
        if mine:
            x[:, at : at + len(mine)] = block(k)[:, mine]
            at += len(mine)
    return dataclasses.replace(
        d,
        x=x,
        names=list(d.names) + [names[j] for j in keep],
        count=dict(d.count) | {n: int(c) for n, c in zip(names, set_rows)},
    )


def segment_paths(d: Design) -> Design:
    """`d` with a centered hat column for each segment and quarter start, as in the module's
    docstring."""
    q = quarter_starts(d)
    knots = np.asarray((q - pd.Timestamp(d.start)).days, float) / YEAR_DAYS
    return path_design(d, knots, [f"{t.year}q{t.quarter}" for t in q])


def _quarter_years(name: str) -> float:
    """The years from REFERENCE to the quarter start in a path column's name."""
    q = pd.Period(name.rsplit(":", 1)[1].upper(), freq="Q").start_time
    return (q - REFERENCE).days / YEAR_DAYS


def segment_spec(names) -> list[dict]:
    """A Gaussian process prior for each segment with path columns in `names`, in the order of
    their first column, each with its segment's name."""
    out = {}
    for c in names:
        if c.startswith("seg:"):
            out.setdefault(c.rsplit(":", 1)[0], []).append(c)
    return [
        dict(
            name=seg,
            cols=cols,
            x=np.array([_quarter_years(c) for c in cols]),
            amp=SEG_AMP,
            ls=SEG_LS,
        )
        for seg, cols in out.items()
    ]


def gp_spec(names) -> list[dict]:
    """The floor curves' processes, then the segments' paths', so a process keeps its place
    in `gp_amp` and `gp_ls` among the floor curves."""
    return drift_building_phase.gp_spec(names) + segment_spec(names)


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """`drift.run` with L1's local-drift terms and the segments' processes beside the floor
    curves'."""
    return drift.run(
        d,
        priors,
        settings,
        log,
        checkpoint,
        gp=gp_spec(d.names),
        groups=drift.groups_of(d, GROUPS),
    )


def _segment_extras(trace: dict, names) -> dict:
    """Each segment path's amplitude and lengthscale draws, by name."""
    first = len(drift_building_phase.gp_spec(names))
    out = {}
    for k, spec in enumerate(segment_spec(names)):
        for q in ("gp_amp", "gp_ls"):
            out[f"{q}[{spec['name']}]"] = np.asarray(trace[q])[..., first + k]
    return out


def diagnostics(trace: dict, names) -> dict:
    """L1's convergence table, with each segment path's amplitude and lengthscale."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = drift.diagnostics(trace, names)
    rows = out["per_quantity"]
    for n, x in _segment_extras(trace, names).items():
        rows[n] = {"rhat": split_rhat(x), "ess": ess(x)}
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
    """L1's summary, with each segment path's amplitude and lengthscale."""
    out = drift.summarize(kept, names)
    out["segment_gp"] = {
        n: two_zone._q(x) for n, x in _segment_extras(kept, names).items()
    }
    return out


def run_record(d: Design) -> dict:
    """L1's record, with the segments, their quarter starts and the paths' priors."""
    seg = segment_index(d)
    cols = [n for n in d.names if n.startswith("seg:")]
    return drift_building_phase.run_record(d) | {
        "segments": {
            "names": segment_names(d),
            "rows": np.bincount(seg, minlength=len(segment_names(d))).tolist(),
            "quarter_starts": [str(q.date()) for q in quarter_starts(d)],
            "columns": len(cols),
            "reference": str(REFERENCE.date()),
            "amp2_invgamma": list(SEG_AMP),
            "log_ls_normal": list(SEG_LS),
        }
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model drift-building-phase-segment`: fit on the split's training
    rows and save the run."""
    drift.main_run(
        argv, name=NAME, sample=run, spec=sys.modules[__name__], level_dof=LEVEL_DOF
    )
