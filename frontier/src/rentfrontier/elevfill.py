"""The building's elevator as of the row's day.

Many listings leave the elevator field unstated though an earlier listing in
the same building stated it. `asof_elevator` fills an unstated field with the
building's latest stated value from strictly earlier days, so a row never
reads a later listing. Reads no rents."""

import numpy as np
import pandas as pd


def asof_elevator(frame: pd.DataFrame) -> pd.DataFrame:
    """The row's elevator ("yes", "no" or "unknown") and its source: "own"
    when the row states it, "building" when filled from an earlier listing in
    the building, else "none"."""
    day = pd.to_datetime(frame.price_at, utc=True).dt.floor("D")
    stated = frame.elevator.ne("unknown").to_numpy()
    rows = pd.DataFrame(
        {
            "building": frame.building.to_numpy(),
            "day": day.to_numpy(),
            "value": frame.elevator.to_numpy(),
            "i": np.arange(len(frame)),
        }
    )
    latest = (
        rows[stated]
        .sort_values(["day", "i"], kind="stable")
        .groupby(["building", "day"], sort=False)
        .value.last()
        .reset_index()
        .sort_values("day", kind="stable")
    )
    found = pd.merge_asof(
        rows[["building", "day", "i"]].sort_values("day", kind="stable"),
        latest,
        on="day",
        by="building",
        allow_exact_matches=False,
    ).sort_values("i")
    earlier = found.value.to_numpy()
    filled = ~stated & pd.notna(earlier)
    elevator = np.where(
        stated, frame.elevator.to_numpy(), np.where(filled, earlier, "unknown")
    )
    source = np.where(stated, "own", np.where(filled, "building", "none"))
    return pd.DataFrame({"elevator": elevator, "source": source}, index=frame.index)
