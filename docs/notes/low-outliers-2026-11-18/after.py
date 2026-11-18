"""The unmarked open ads of a backtest, split by the layout marks on their apartment's
training rows, with the paired elpd difference between two runs on each part.

    python docs/notes/low-outliers-2026-11-18/after.py BASE_RUN NEW_RUN

An unmarked ad codes the same counts as its apartment's previous ad. Its apartment may
still hold marked training rows: the count changed in an earlier ad and stayed.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import drift_building_bedtext_layout as layout
from rentfrontier import drift_deals, drift_score


def clustered(d, building):
    _, cl = np.unique(building, return_inverse=True)
    sums = np.bincount(cl, weights=d - d.mean())
    return float(np.sqrt(len(sums) / max(len(sums) - 1, 1) * np.sum(sums**2)))


def main(argv):
    base, new = Path(argv[0]), Path(argv[1])
    frame, h, held = drift_deals._held_frame(base)
    x = layout.changes(frame, ~held) > 0
    whole = frame.unit_id.astype(str).str.replace(layout.PIECE, "", regex=True)
    key = (frame.building.astype(str) + "|" + whole).to_numpy()
    known = frame.unit_id.notna().to_numpy()
    t = pd.DataFrame(x[~held & known], columns=layout.COLUMNS)
    t["key"] = key[~held & known]
    t["rows"] = 1
    g = t.groupby("key").sum()
    got = g.reindex(key[held])
    rows = got.rows.fillna(0).to_numpy()
    up = (got[["ad:beds_up_prev", "ad:baths_up_prev"]].sum(1) > 0).to_numpy()
    down = (got[["ad:beds_down_prev", "ad:baths_down_prev"]].sum(1) > 0).to_numpy()
    rows = np.where(known[held], rows, 0)
    unmarked = ~x[held].any(1)
    d = drift_score.score_run(new)["elpd"] - drift_score.score_run(base)["elpd"]
    bld = h.building.astype(str).to_numpy()
    sets = {
        "no training row of the apartment": unmarked & (rows == 0),
        "training rows, none marked": unmarked & (rows > 0) & ~up & ~down,
        "training rows marked up only": unmarked & up & ~down,
        "training rows marked down only": unmarked & down & ~up,
        "training rows marked both ways": unmarked & up & down,
    }
    for name, m in sets.items():
        print(
            f"{name:34s} ads {m.sum():5d} elpd {d[m].sum():+7.1f}"
            f" (SE {clustered(d[m], bld[m]):.1f}) mean {d[m].mean():+.4f}"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
