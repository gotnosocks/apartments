"""Screen the `b0bedtext` flags against L2's held-out predictions on the latest split.

    python docs/notes/bed-text-2026-11-16/screen.py DATASET RUN [UNREAD]

DATASET is the copy `rentfrontier.b0bedtext` wrote, RUN is L2's run directory with
`pred_scores.npz`, and UNREAD is an optional file of building ids, one a line, limiting a
second table to held-out ads in those buildings.

For each flag I print the count of training and held-out rows, the share of flagged held-out
ads with the ask above the 99th or below the 1st percentile of L2's predictive distribution,
and the mean and median of z, the ask less L2's median over the spread implied by L2's
quartiles. Income-restricted ads are left out of the held-out figures. A last table splits
the combined flag by the coded bedroom count.
"""

import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import norm

FLAGS = ("bed_flex_at", "bed_text_fewer", "smaller", "bed_text_more")


def table(h: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    out = []
    groups = [(f, h[h[f]]) for f in FLAGS] + [("all", h)]
    if by:
        groups = [(f"smaller, {by}={k:g}", g) for k, g in h[h.smaller].groupby(by)]
    for name, g in groups:
        out.append(
            {
                "rows": name,
                "ads": len(g),
                "above_99": round(100 * (g.cdf > 0.99).mean(), 2),
                "below_01": round(100 * (g.cdf < 0.01).mean(), 2),
                "mean_z": round(g.z.mean(), 3),
                "median_z": round(g.z.median(), 3),
                "mean_log_miss": round(g.miss.mean(), 4),
            }
        )
    return pd.DataFrame(out)


def main(argv):
    dataset, run = argv[:2]
    cols = [
        "listing_id",
        "building",
        "bedrooms",
        "income_restricted",
        *FLAGS[:2],
        FLAGS[3],
    ]
    rows = pq.read_table(f"{dataset}/rows.parquet", columns=cols).to_pandas()
    rows["smaller"] = rows.bed_flex_at | rows.bed_text_fewer
    d = np.load(f"{run}/pred_scores.npz")
    held = d["heldout"]
    print(
        pd.DataFrame(
            {
                "train": rows.loc[~held, list(FLAGS)].sum(),
                "held": rows.loc[held, list(FLAGS)].sum(),
            }
        ).to_string()
    )
    h = rows[held].reset_index(drop=True)
    assert (h.listing_id.astype(str).to_numpy() == d["listing"].astype(str)).all()
    qs = list(d["quantiles"])
    iqr = d["q"][:, qs.index(0.75)] - d["q"][:, qs.index(0.25)]
    h["miss"] = d["y"] - d["pred"]
    h["z"] = h.miss / (iqr / (norm.ppf(0.75) - norm.ppf(0.25)))
    h["cdf"] = d["cdf"]
    h = h[~h.income_restricted.fillna(False).astype(bool)]
    print("\nheld-out ads, income-restricted left out")
    print(table(h).to_string(index=False))
    print(table(h, "bedrooms").to_string(index=False))
    if len(argv) > 2:
        unread = set(open(argv[2]).read().split())
        print("\nheld-out ads in the unread buildings")
        print(table(h[h.building.isin(unread)]).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:])
