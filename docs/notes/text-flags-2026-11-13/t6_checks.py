"""Text flags, step 6: checks of the note's numbers after review.

I take L1's coefficients for its three text flags from `posterior.npz`, both over the 272
kept draws, which L1's predictions use, and over all 10,880 traced draws.

I count the fresh sample's read ads that are among L1's held-out ads of the latest split, by
flag, part of the draw and label, so the note can say how many of the read ads the gap
comparison of `t5_gap.py` includes.

Last I count the listings at three edges of the new patterns, matched on every description
with `common.match_all` and set against the flags of `t3_flags.parquet`:

- `income_restricted_v2` marks ads saying "no income caps" or "no income restrictions";
- `shared_space_v2` marks ads of buildings converted from an SRO or formerly one, spelled out
  as "single room occupancy";
- `shared_space_v2` misses "I'm looking for a roommate" written with a curly apostrophe.

The counts go to `OUT/t6_checks.json`.

    python t6_checks.py   # inside systemd-run --user --scope -p MemoryMax=3G
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from common import OUT, ROWS, match_all, read_labels

RUN = Path("/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1")
EDGES = {
    "income_v2": re.compile(r"\bno income (?:caps?|restrict)"),
    "shared_v2": re.compile(
        r"(?:converted|conversion) (?:from|of) (?:an? |the )?(?:former )?"
        r"(?:sro|single[- ]room)|former(?:ly)? (?:an? )?single[- ]room[- ]occupancy"
    ),
    "not shared_v2": re.compile(
        r"(?:i’m|we’re) (?:looking for|seeking|searching for) (?:a |an |one )?"
        r"(?:\w+ )?(?:roommate|roomate|housemate|flatmate)\b"
    ),
}

out = {"coefficients": {}}
post = np.load(RUN / "posterior.npz", allow_pickle=True)
names = list(post["names"])
for name in ("flag:income_restricted", "flag:shared_space", "flag:rent_stabilized"):
    i = names.index(name)
    for draws in ("kept", "trace"):
        x = post[f"{draws}/beta"][..., i].ravel()
        q5, q95 = np.quantile(x, [0.05, 0.95])
        out["coefficients"][f"{name} {draws}"] = {
            "draws": int(x.size),
            "mean": float(x.mean()),
            "q05": float(q5),
            "q95": float(q95),
        }
        print(f"{name} {draws} ({x.size}): {x.mean():+.4f} ({q5:+.4f} to {q95:+.4f})")

lab = read_labels("eval")
held = pd.read_parquet(ROWS, columns=["listing_id", "held"])
held["listing_id"] = held.listing_id.astype(str)
lab = lab.merge(held, on="listing_id", how="left", validate="many_to_one")
read_held = (
    lab[lab.held.fillna(False).astype(bool)]
    .groupby(["flag", "stratum"])
    .label.value_counts()
    .unstack(fill_value=0)
)
print("\nRead ads among L1's held-out ads:")
with pd.option_context("display.width", 200):
    print(read_held)
out["read_heldout"] = {
    f"{flag}: {stratum}": {k: int(v) for k, v in row.items()}
    for (flag, stratum), row in read_held.iterrows()
}

m = match_all({f"edge {k}": rx for k, rx in EDGES.items()})
t3 = pd.read_parquet(
    OUT / "t3_flags.parquet", columns=["listing_id", "income_v2", "shared_v2"]
)
m = m.merge(t3, on="listing_id", how="left", validate="one_to_one")
out["edges"] = {}
for key in EDGES:
    edge = m[f"edge {key}"].fillna(False).astype(bool).to_numpy()
    col = key.removeprefix("not ")
    flag = m[col].fillna(False).astype(bool).to_numpy()
    on = edge & (~flag if key.startswith("not ") else flag)
    out["edges"][key] = {"edge": int(edge.sum()), "edge_and_flag_side": int(on.sum())}
    print(
        f"edge {key}: {edge.sum():,} listings, {on.sum():,} of them on that side of the flag"
    )
(OUT / "t6_checks.json").write_text(json.dumps(out, indent=2))
