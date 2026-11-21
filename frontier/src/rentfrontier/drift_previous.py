"""Each held-out ad's previous ad of its unit in a drift fit's own dataset.

The diagnostics table (`rentfrontier.drift_diagnostics`) and the Deals table
(`rentfrontier.drift_deals`) both take their `prev_*` columns from here. It sits in its own
module so that both can import it at the top: `drift_diagnostics` imports `drift_deals`, so
`drift_deals` can't import `drift_diagnostics` at the top without a circular import.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def previous(frame: pd.DataFrame, held: np.ndarray) -> pd.DataFrame:
    """For each held-out row, the ask, day and bedrooms of its unit's previous ad in the
    fit's own dataset: the latest training row of the same building and unit_id dated
    strictly before it, the later `price_at` winning a tie of days. The unit is the
    model's, so the pieces "~1", "~2" of an apartment are not read together, and a
    held-out row is never another's previous ad (`docs/leak-free-scoring.md`). Missing
    where there is no such row. One row per held-out row, in their order."""
    held = np.asarray(held, bool)
    unit = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
    day = pd.to_datetime(frame.latest_day)
    known = frame.unit_id.notna().to_numpy() & day.notna().to_numpy()
    cols = ["latest_ask", "latest_day", "bedrooms"]
    left = pd.DataFrame({"_key": unit, "_day": day})[held & known].reset_index()
    order = ["_day"] + (["price_at"] if "price_at" in frame else [])
    right = frame.loc[~held & known, [*cols, *order[1:]]]
    right = right.assign(_key=unit[~held & known], _day=day[~held & known])
    found = pd.merge_asof(
        left.sort_values("_day", kind="stable"),
        right.sort_values(order, kind="stable")[["_key", "_day", *cols]],
        on="_day",
        by="_key",
        allow_exact_matches=False,
    )
    return found.set_index("index")[cols].reindex(frame.index[held])


def previous_columns(frame: pd.DataFrame, held: np.ndarray) -> dict[str, np.ndarray]:
    """`previous` as the columns `prev_ask`, `prev_day` (a "YYYY-MM-DD" string, or None)
    and `prev_bedrooms`, one value per held-out row in their order. The diagnostics table
    and the Deals table (`drift_deals.deals`) both take them from here."""
    before = previous(frame, held)
    day = pd.to_datetime(before.latest_day).dt.strftime("%Y-%m-%d")
    return {
        "prev_ask": before.latest_ask.to_numpy(float),
        "prev_day": day.where(day.notna(), None).to_numpy(object),
        "prev_bedrooms": before.bedrooms.to_numpy(float),
    }
