"""Why each row's previous ad changes: the old rule's previous ad, worked out again from
each fit's dataset, was another piece of the apartment, a held-out ad of the fit, or an
ad of the same day. Needs the frontier package on PYTHONPATH."""

from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import drift_diagnostics as dd

R = Path("/data1/apartments/frontier/runs")
NEW = "/data1/apartments/tmp/diag-prev/new/ads.parquet"
diag = pd.read_parquet(NEW, columns=["listing_id", "source"])
RUNS = (
    ("drift-building-b0-latest-67d14e17-b9", "latest"),
    ("drift-building-b0-market-67d14e17-n9", "market"),
)
for name, src in RUNS:
    f, held = dd._rows(R / name)
    keep = set(diag.listing_id[diag.source == src])
    # The old rule: the row before, by day then price_at, in the apartment's history.
    key = dd.apartment(f)
    on = key.notna().to_numpy()
    k = f[on].assign(_key=key, _pos=np.arange(len(f))[on])
    k = k.sort_values(["_key", "latest_day", "price_at"], kind="stable")
    k["_prev"] = k.groupby("_key", sort=False)._pos.shift(1)
    prevpos = k._prev.reindex(f.index)
    new = dd.previous(f, held)
    hi = np.flatnonzero(held)
    rows = pd.DataFrame(
        {
            "lid": f.listing_id.iloc[hi].astype(str).to_numpy(),
            "pp": prevpos.iloc[hi].to_numpy(),
        }
    )
    rows = rows[rows.lid.isin(keep)]
    has = rows.pp.notna()
    p = rows.pp[has].astype(int).to_numpy()
    me = hi[rows.index[has]]
    unit = f.unit_id.astype(str).to_numpy()
    day = pd.to_datetime(f.latest_day).to_numpy()
    piece, was_held, same_day = unit[p] != unit[me], held[p], day[p] == day[me]
    print(src, "rows", len(rows), "old prev", int(has.sum()))
    print(
        "  old prev is another piece",
        int(piece.sum()),
        "| a held-out ad of the fit",
        int(was_held.sum()),
        "(same piece",
        int((was_held & ~piece).sum()),
        ")",
        "| same day",
        int(same_day.sum()),
        "| any of these",
        int((piece | was_held | same_day).sum()),
    )
    nv = new.latest_ask.to_numpy()[rows.index.to_numpy()]
    print("  new prev present", int(np.isfinite(nv).sum()))
