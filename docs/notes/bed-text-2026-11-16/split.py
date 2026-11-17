"""Split the bedroom-text pool's elpd change on unflagged held-out ads by the unit mean.

    python docs/notes/bed-text-2026-11-16/split.py DATASET L2_RUN BEDTEXT_RUN

I rebuild the model's unit-mean column from the dataset with the model's own functions,
then print the paired elpd difference, clustered by building, for the held-out ads without
either flag: those with a unit mean of 0, and those with a unit mean above 0, whose earlier
ads in the unit carried the flag. The last group is the unflagged held-out ads whose unit
has a flagged training ad of any day, the rows the `bedunit` model's unit column marks.
"""

import sys

import numpy as np
import pyarrow.parquet as pq

from rentfrontier.building_zones_floor_asof3_unitmean import unit_groups
from rentfrontier.building_zones_kitchen_sink import past_means
from rentfrontier.drift_building_phase_unitkn_level_bedtext import flag
from rentfrontier.drift_building_phase_unitkn_level_bedunit import ever


def clustered(d, building):
    _, cl = np.unique(building, return_inverse=True)
    sums = np.bincount(cl, weights=d - d.mean())
    return float(np.sqrt(len(sums) / (len(sums) - 1) * np.sum(sums**2)))


def main(argv):
    dataset, old, new = argv
    a, b = np.load(f"{old}/pred_scores.npz"), np.load(f"{new}/pred_scores.npz")
    cols = ["listing_id", "building", "unit_id", "price_at", "bed_flex_at"]
    cols += ["bed_text_fewer", "bed_text_more"]
    frame = pq.read_table(f"{dataset}/rows.parquet", columns=cols).to_pandas()
    held = a["heldout"]
    x = flag(frame)[:, None]
    group = unit_groups(frame)
    um = past_means(x, group, frame.price_at, ~held)[held, 0]
    marked = ever(x[:, 0], group, ~held)[held] > 0
    h = frame[held].reset_index(drop=True)
    assert (h.listing_id.astype(str).to_numpy() == a["listing"].astype(str)).all()
    own = x[held, 0] > 0
    more = h.bed_text_more.fillna(False).to_numpy(bool)
    building = a["building"].astype(str)
    d = b["elpd"] - a["elpd"]
    shift = b["pred"] - a["pred"]
    groups = {
        "no flag, unit mean 0": ~own & ~more & (um == 0),
        "no flag, unit mean above 0": ~own & ~more & (um > 0),
        "flag, unit mean below 1": own & (um < 1),
        "flag, unit mean 1": own & (um == 1),
        "no flag, unit ever flagged": ~own & marked,
    }
    for name, m in groups.items():
        print(
            f"{name:28s} ads {m.sum():7d}  elpd diff {d[m].sum():8.1f}"
            f"  SE {clustered(d[m], building[m]):6.1f}"
            f"  mean unit mean {um[m].mean():.3f}  mean pred shift {shift[m].mean():+.4f}"
            f"  mean miss L2 {(a['y'][m] - a['pred'][m]).mean():+.4f}"
            f" new {(b['y'][m] - b['pred'][m]).mean():+.4f}"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
