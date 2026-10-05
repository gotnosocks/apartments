"""The declared held-out splits.

Both are reproduced from their written definitions so that results pair with
the promoted model's held-out rows by audit_id:

- rows: 10% of all rows, drawn from units listed more than once; each such
  unit keeps one training row. Seed 20260922.
- units: every row of about 10% of units, drawn from buildings with at least
  three units; each building keeps at least one training unit. Same seed.

- latest: each of a random set of re-listed units' most recent listing, 10% of all
  rows (units with two or more rows; seed as above). No training row comes after
  a held-out row in its unit, so no training row's features can read a held-out
  ask through features built from the same unit's earlier listings (Ben,
  2026-10-05: leak-free feature evaluation; docs/leak-free-scoring.md). It is
  drawn after the data rules, so the units are the merged ones.

The promoted model's runs additionally dropped a few held-out rows outside its
training floor range or time horizon. Paired comparisons use the intersection
of held-out audit_ids, which `reference.py` checks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 20260922
FRACTION = 0.10


def row_split(data: pd.DataFrame, fraction=FRACTION, seed=SEED) -> np.ndarray:
    """Boolean held-out mask for the row split."""
    rng = np.random.default_rng(seed)
    counts = data.unit_id.map(data.unit_id.value_counts())
    keep = pd.Series(False, index=data.index)
    kept = data[counts.ge(2)].groupby("unit_id").sample(1, random_state=seed).index
    keep[kept] = True
    candidates = data.index[counts.ge(2) & ~keep]
    chosen = rng.choice(candidates, size=round(fraction * len(data)), replace=False)
    return data.index.isin(chosen)


def unit_split(data: pd.DataFrame, fraction=FRACTION, seed=SEED) -> np.ndarray:
    """Boolean held-out mask for the unit split."""
    units = data.groupby("unit_id").building.first()
    per_building = units.value_counts()
    eligible = units[units.map(per_building).ge(3)].index.to_numpy()
    chosen = set(
        np.random.default_rng(seed).choice(
            np.sort(eligible), size=round(fraction * len(units)), replace=False
        )
    )
    for _, members in units.reset_index().groupby("building").unit_id:
        members = sorted(members)
        if set(members) <= chosen:
            chosen.discard(members[0])
    return data.unit_id.isin(chosen).to_numpy()


def latest_split(data: pd.DataFrame, fraction=FRACTION, seed=SEED) -> np.ndarray:
    """Boolean held-out mask for the latest-listing split."""
    at = pd.to_datetime(data.price_at, utc=True)
    order = data.assign(_at=at).sort_values(["unit_id", "_at", "audit_id"])
    counts = order.unit_id.map(order.unit_id.value_counts())
    last = order[counts.ge(2)].groupby("unit_id").tail(1)
    if last.empty:
        return np.zeros(len(data), dtype=bool)
    # A unit whose two latest listings share a date has no single latest one
    # (features that read earlier listings order ties by frame position).
    tied = (
        order[order.unit_id.isin(last.unit_id)]
        .groupby("unit_id")
        ._at.apply(lambda t: len(t) > 1 and t.iloc[-1] == t.iloc[-2])
    )
    last = last[~last.unit_id.map(tied).to_numpy()]
    size = min(round(fraction * len(data)), len(last))
    chosen = np.random.default_rng(seed).choice(
        np.sort(last.audit_id.to_numpy()), size=size, replace=False
    )
    return data.audit_id.isin(set(chosen)).to_numpy()


def no_split(data: pd.DataFrame, fraction=FRACTION, seed=SEED) -> np.ndarray:
    """No held-out rows: the analysis fit on all data (residuals, contributions)."""
    return np.zeros(len(data), dtype=bool)


SPLITS = {
    "rows": row_split,
    "units": unit_split,
    "latest": latest_split,
    "all": no_split,
}
# Splits drawn after the data rules (on merged units and kept rows).
AFTER_RULES = {"latest"}
