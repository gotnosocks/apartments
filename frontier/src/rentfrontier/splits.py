"""The two declared held-out splits.

Both are reproduced from their written definitions so that results pair with
the promoted model's held-out rows by audit_id:

- rows: 10% of all rows, drawn from units listed more than once; each such
  unit keeps one training row. Seed 20260922.
- units: every row of about 10% of units, drawn from buildings with at least
  three units; each building keeps at least one training unit. Same seed.

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
    chosen = rng.choice(
        candidates, size=int(round(fraction * len(data))), replace=False
    )
    return data.index.isin(chosen)


def unit_split(data: pd.DataFrame, fraction=FRACTION, seed=SEED) -> np.ndarray:
    """Boolean held-out mask for the unit split."""
    units = data.groupby("unit_id").building.first()
    per_building = units.value_counts()
    eligible = units[units.map(per_building).ge(3)].index.to_numpy()
    chosen = set(
        np.random.default_rng(seed).choice(
            np.sort(eligible), size=int(round(fraction * len(units))), replace=False
        )
    )
    for _, members in units.reset_index().groupby("building").unit_id:
        members = sorted(members)
        if set(members) <= chosen:
            chosen.discard(members[0])
    return data.unit_id.isin(chosen).to_numpy()


SPLITS = {"rows": row_split, "units": unit_split}
