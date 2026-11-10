"""Shared loaders for the drift fit reports and the artifact extract."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

RUNS = Path("/data1/apartments/frontier/runs")
REF = Path("/data1/apartments/tmp/conference-followups")
REFS = {
    "fit4": "unitmean-latest.npz",
    "fit8": "cap64-latest.npz",
    "ks_a": "ks-latest.npz",
}
GROUPS = ("studio", "one_bedroom", "two_bedroom", "three_plus")
GAP_EDGES = (0.5, 1, 2, 3, 5, 8)
YEAR = 365.25


def result(run):
    return json.loads((RUNS / run / "result.json").read_text())


def scores(run):
    z = np.load(RUNS / run / "pred_scores.npz", allow_pickle=True)
    return {k: z[k] for k in z.files}


def ref(name):
    z = np.load(REF / REFS[name], allow_pickle=True)
    return {k: z[k] for k in z.files}


def held_frame(run):
    """The run's dataset rows, its held-out mask, and per held-out row: years since the
    unit's last training ad (inf if none), whether another unit of the building has a
    training ad within 183 days of the row's day, and the unit key."""
    r = result(run)
    frame = pd.read_parquet(
        Path(r["dataset"]) / "rows.parquet",
        columns=[
            "listing_id",
            "building",
            "unit_id",
            "neighbourhood",
            "latest_ask",
            "latest_day",
            "bedrooms",
        ],
    )
    held = np.load(RUNS / run / "posterior.npz")["heldout"]
    assert len(held) == len(frame)
    none = frame.unit_id.isna().to_numpy()
    key = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
    key[none] = "#row" + pd.Series(np.flatnonzero(none), index=key.index[none]).astype(
        str
    )
    frame["unit_key"] = key
    frame["day"] = pd.to_datetime(frame.latest_day)
    train = frame[~held]
    h = frame[held].reset_index(drop=True)
    last = train.groupby("unit_key").day.max()
    gap = (h.day - h.unit_key.map(last)).dt.days / YEAR
    h["gap"] = gap.fillna(np.inf).to_numpy()
    # Another unit of the building with a training ad within 183 days of the row's day:
    # the building's training ads in the window outnumber the unit's own.
    day_n = (frame.day - pd.Timestamp("2000-01-01")).dt.days.to_numpy()
    hday = day_n[held]
    h["bld_near"] = window_count(frame.building, held, day_n, hday) > window_count(
        frame.unit_key, held, day_n, hday
    )
    return frame, held, h


def window_count(group, held, day_n, hday, w=183):
    """Per held-out row, the training rows of its group with a day within w days."""
    codes, uniq = pd.factorize(group)
    big = np.int64(100_000)
    tk = np.sort(codes[~held].astype(np.int64) * big + day_n[~held])
    hk = codes[held].astype(np.int64) * big + hday
    return np.searchsorted(tk, hk + w, side="right") - np.searchsorted(tk, hk - w)


def gap_bins(gap, edges=GAP_EDGES):
    labels = [f"<{edges[0]}"] + [f"{a}-{b}" for a, b in zip(edges[:-1], edges[1:])]
    labels += [f"{edges[-1]}+", "no training ad"]
    idx = np.searchsorted(np.asarray(edges), gap, side="right")
    idx = np.where(np.isfinite(gap), idx, len(edges) + 1)
    return idx, labels


def cluster_var(x, g):
    _, inv = np.unique(g, return_inverse=True)
    s = np.bincount(inv, weights=x - x.mean())
    return (s * s).sum()


def diff_se(x, building):
    return float(np.sqrt(len(x) * x.var())), float(np.sqrt(cluster_var(x, building)))


def align(a_listing, b_listing):
    _, ia, ib = np.intersect1d(
        a_listing.astype(str),
        b_listing.astype(str),
        assume_unique=True,
        return_indices=True,
    )
    return ia, ib


def q(x, p=(0.05, 0.5, 0.95)):
    return [float(v) for v in np.quantile(np.asarray(x, float).ravel(), p)]
