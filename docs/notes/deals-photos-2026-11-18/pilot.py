"""Image read of the low outliers, part 3: agreement of two readers on the pilot batches.

Reads `reads/A/batch_NN.jsonl` and `reads/B/batch_NN.jsonl` for the labels both readers
wrote, and prints the share of ad-category pairs marked alike, each category's count from
each reader, the share of ads with grades within 1 point, and agreement on the plan fields.
"""

import json
import sys
from pathlib import Path

import pandas as pd

OUT = Path("/data1/apartments/tmp/deals-photos-2026-11-18")
CATS = (
    "dark_or_shaft low_ceiling awkward_layout tiny_or_windowless_bedroom kitchen_poor "
    "bath_poor worn_finishes ground_or_basement street_noise_cues other_unit_or_renderings "
    "room_only unfinished occupied_clutter walkup_or_stairs few_or_poor_photos"
).split()
PLAN = "plan_bedrooms plan_windowless plan_flex plan_through plan_levels".split()


def reads(name):
    rows = []
    for path in sorted((OUT / "reads" / name).glob("batch_*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows).drop_duplicates("label").set_index("label")


if __name__ == "__main__":
    a, b = reads(sys.argv[1]), reads(sys.argv[2])
    both = a.index.intersection(b.index)
    a, b = a.loc[both], b.loc[both]
    print(len(both), "ads read by both")
    same = total = 0
    for c in CATS:
        x = a.categories.map(lambda v: c in v)
        y = b.categories.map(lambda v: c in v)
        same += (x == y).sum()
        total += len(x)
        print(
            f"  {c:28s} {sys.argv[1]} {x.sum():3d} {sys.argv[2]} {y.sum():3d} both {(x & y).sum():3d}"
        )
    print(f"ad-category pairs alike: {100 * same / total:.1f}%")
    for g in ("condition", "light"):
        x, y = pd.to_numeric(a[g]), pd.to_numeric(b[g])
        ok = x.notna() & y.notna()
        print(
            f"{g}: within 1 point {100 * ((x - y).abs()[ok] <= 1).mean():.1f}%, "
            f"equal {100 * (x == y)[ok].mean():.1f}%, means {x[ok].mean():.2f} {y[ok].mean():.2f}, "
            f"corr {x[ok].corr(y[ok]):.2f}"
        )
    plan = a.plan.astype(bool) & b.plan.astype(bool)
    print(plan.sum(), "ads with a plan read by both")
    for f in PLAN:
        x, y = a[f][plan], b[f][plan]
        alike = (x == y) | (x.isna() & y.isna())
        print(f"  {f:16s} alike {100 * alike.mean():.1f}%")
