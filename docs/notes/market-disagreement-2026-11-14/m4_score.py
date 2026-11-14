"""Market disagreement, part 4: map the readers' coined causes onto the list, join the key
and score each cause by group.

The mapping `COINED` was written from the labels alone, before this script first opened
`key.parquet` or `draw.parquet`; `labels.json` records the SHA-256 of the labels and the time.
A cause is flagged for group A or C when it has at least 5 reads there and its share is at
least twice its share in B and at least twice its share in R (a share of zero in a control
passes). Shares and differences carry building-clustered SEs, as in S16's `b4_score.py`."""

import glob
import hashlib
import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/market-disagreement-2026-11-14/"
GROUPS = ["A_cheap_slow", "B_cheap_fast", "C_dear_fast", "R_random"]
TEST, CONTROLS = ["A_cheap_slow", "C_dear_fast"], ["B_cheap_fast", "R_random"]
COINED = {
    "income_flag_contradicted": "data_error",
    "loft_character": "loft_ceilings_period",
    "loft_skylight_high_ceilings": "loft_ceilings_period",
    "rent_stabilized": "rent_stabilized",
    "private_park_key_access": "other_building_feature",
}
LIST = {
    "duplex_multilevel", "penthouse_top_floor", "private_outdoor", "views", "renovation",
    "furnished_short_term", "shared_room", "income_restricted_program", "garden_basement",
    "size_mismatch", "luxury_building_missed", "utilities_fees_included", "unit_fault",
    "building_block_fault", "terms", "wrong_unit_joined", "staged_relist", "data_error",
    "none_apparent",
}  # fmt: skip

files = sorted(glob.glob(OUT + "out/batch*.jsonl"))
raw = "".join(open(f).read() for f in files)
lab = pd.DataFrame([json.loads(line) for line in raw.splitlines() if line.strip()])
lab["category"] = lab.cause.map(lambda c: COINED.get(c, c))
unknown = set(lab.category) - LIST - set(COINED.values())
assert not unknown, unknown
assert lab.read_id.is_unique and len(lab) == 400
json.dump(
    {
        "sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "mapped_at": pd.Timestamp.now(tz="America/New_York").isoformat(),
        "coined": COINED,
    },
    open(OUT + "labels.json", "w"),
    indent=1,
)

key = pd.read_parquet(OUT + "key.parquet")
draw = pd.read_parquet(OUT + "draw.parquet")
d = lab.merge(key, on="read_id").merge(draw, on="listing_id")
assert len(d) == 400


def share_se(x, b):
    x = np.asarray(x, float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(x))


def diff_se(x, on, b):
    g = pd.DataFrame({"x": np.asarray(x, float), "on": np.asarray(on, bool), "b": b})
    m1, m0 = g.x[g.on].mean(), g.x[~g.on].mean()
    g["r"] = np.where(g.on, (g.x - m1) / g.on.sum(), -(g.x - m0) / (~g.on).sum())
    t = g.groupby("b").r.sum()
    return float(m1 - m0), float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


rows = []
for cat in d.category.value_counts().index:
    x = d.category == cat
    r = {"cause": cat}
    for g in GROUPS:
        m = d.group == g
        r[g] = int(x[m].sum())
        r[g + "_se"] = share_se(x[m], d.building[m])
    flagged = []
    for g in TEST:
        ok = r[g] >= 5
        for c in CONTROLS:
            m = d.group.isin([g, c])
            diff, se = diff_se(x[m], d.group[m] == g, d.building[m].to_numpy())
            r[f"{g}-{c}"], r[f"{g}-{c}_se"] = diff, se
            ok = ok and r[g] >= 2 * r[c]
        if ok:
            flagged.append(g[0])
    r["flag"] = ",".join(flagged)
    rows.append(r)
tab = pd.DataFrame(rows)
tab.to_csv(OUT + "table.csv", index=False)
d.drop(columns=["evidence"]).to_parquet(OUT + "reads.parquet")
direction = (
    d.groupby(["category", "group"]).direction.value_counts().unstack(fill_value=0)
)
direction.to_csv(OUT + "direction.csv")
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 200)
pd.set_option("display.max_colwidth", 110)
print(tab.round(3).to_string(index=False))
print(direction.to_string())
for cat in sorted(
    set(tab.cause[tab.flag != ""]) | {"unit_fault", "terms", "staged_relist"}
):
    print("\n##", cat)
    s = d[d.category == cat].sort_values("group")
    print(
        s[["group", "days", "cut", "gap1", "direction", "cause_note"]]
        .round(2)
        .to_string(index=False)
    )
