"""Named feature sets, kept separate from model designs.

A feature set maps the flat table plus a training mask to a matrix of named,
grouped columns on the log-rent scale. Anything estimated from data (reference
medians, category levels) uses training rows only. Unknown is always its own
level or indicator, never folded into "no".

Each set has an id that runs record. Change a set's behaviour by adding a new
id, so older leaderboard entries stay reproducible from their commit anyway.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import data as data_module


@dataclass
class Features:
    id: str
    names: list[str]
    groups: list[str]  # contribution group per column, e.g. "bedrooms"
    values: np.ndarray  # (rows, columns) float64
    prior_scale: np.ndarray  # per-column normal prior sd on log scale

    def group_names(self) -> list[str]:
        return list(dict.fromkeys(self.groups))


class _Builder:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.names: list[str] = []
        self.groups: list[str] = []
        self.columns: list[np.ndarray] = []
        self.scales: list[float] = []

    def add(self, group: str, name: str, values, scale: float = 1.0):
        values = np.asarray(values, dtype=np.float64)
        if values.shape != (len(self.frame),) or not np.isfinite(values).all():
            raise ValueError(f"Bad feature column {name}")
        self.names.append(name)
        self.groups.append(group)
        self.columns.append(values)
        self.scales.append(scale)

    def categorical(self, group: str, column, reference: str, scale: float = 1.0):
        series = self.frame[column] if isinstance(column, str) else column
        for level in sorted(set(series.unique()) - {reference}):
            self.add(group, f"{group}={level}", series.eq(level), scale)

    def build(self, id: str) -> Features:
        return Features(
            id,
            self.names,
            self.groups,
            np.column_stack(self.columns),
            np.asarray(self.scales),
        )


def _bedrooms(frame):
    beds = frame.bedrooms.round().clip(0, 5).astype(int)
    return beds.map(lambda b: "5+" if b >= 5 else str(b))


def base_v1(frame: pd.DataFrame, train: np.ndarray) -> Features:
    """Listing attributes as advertised, with explicit unknown levels."""
    b = _Builder(frame)
    beds = _bedrooms(frame)
    b.categorical("bedrooms", beds, reference="1")

    full = frame.full_baths.clip(1, 4).map(lambda n: "4+" if n >= 4 else str(n))
    b.categorical("bathrooms", full.rename("full"), reference="1")
    half = frame.half_baths.map(
        lambda n: "unknown" if pd.isna(n) else ("2+" if n >= 2 else str(int(n)))
    )
    b.categorical("bathrooms", "half=" + half, reference="half=0")

    # Size: log square feet relative to the training median for the same
    # bedroom count. Unknown size gets its own indicator and zero deviation.
    sqft = frame.square_feet
    known = sqft.between(150, 8000)
    log_sqft = np.log(sqft.where(known))
    median = log_sqft[train & known.to_numpy()].groupby(beds[train]).median()
    deviation = (log_sqft - beds.map(median)).where(known, 0.0).fillna(0.0)
    b.add("size", "log_sqft_vs_bedroom_median", deviation)
    b.add("size", "sqft_unknown", ~known)

    # Advertised floor label (a proxy, not a verified physical floor).
    floor = frame.listed_floor.astype("float")
    floor_known = floor.ge(1)
    log_floor = np.log(floor.where(floor_known, 1.0))
    b.add("floor", "log_floor", log_floor)
    b.add("floor", "log_floor_above_6", np.maximum(0, log_floor - np.log(6)))
    b.add("floor", "log_floor_above_15", np.maximum(0, log_floor - np.log(15)))
    b.add("floor", "floor_unknown", ~floor_known)
    b.add("floor", "log_floor_x_no_elevator", log_floor * frame.elevator.eq("no"))

    b.categorical("elevator", "elevator", reference="yes")
    b.categorical("doorman", "doorman", reference="unknown")
    b.categorical("laundry", "laundry", reference="in_building")
    hvac = frame.hvac.where(frame.hvac.isin(["central_ac", "unknown"]), "other")
    b.categorical("hvac", hvac, reference="unknown")
    b.categorical("pets", "pets", reference="unknown")
    for name in data_module.VIEWS:
        b.add("views", f"view_{name}", frame[f"view_{name}"].eq("yes"))
    for name in data_module.WINDOWS:
        b.add("windows", f"window_{name}", frame[f"window_{name}"].eq("yes"))
    b.add(
        "price_basis",
        "current_capture_ask",
        frame.price_basis.ne("historical_initial_own_advertisement_ask"),
    )
    return b.build("base-v1")


FEATURE_SETS = {"base-v1": base_v1}


def build(name: str, frame: pd.DataFrame, train: np.ndarray) -> Features:
    return FEATURE_SETS[name](frame, np.asarray(train, dtype=bool))
