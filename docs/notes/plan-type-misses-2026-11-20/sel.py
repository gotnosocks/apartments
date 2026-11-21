"""Pick the buildings to read and write their dossiers, with no rent and no error in them.

Read: the five buildings named in the TODO item, and from half A the new buildings (first ad
at most 3 years before the ad's day) whose held-out ads of 2 or more bedrooms miss together
most (the absolute mean gap, clipped at +-0.5, times the root of the count), 8 from the
backtest's new units and 8 from the latest-split run's units with one training ad. Controls,
mixed in: buildings of the same two pools with the smallest absolute mean gap. Dollar amounts
in the texts are masked. `picked.csv` keeps the key (set, building, role, mean gap); the
dossiers go to readers without it.
"""

import json
import re

import numpy as np
import pandas as pd

from b1 import OUT

NAMED = [
    "the-seren",
    "lawrence-tower",
    "union-channel",
    "420-carroll",
    "12-halsey-street-brooklyn",
]
MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?k?|\b\d[\d,]{3,}(?:\.\d+)?\s?(?=(?:/|per |a )mo)", re.I
)
rng = np.random.default_rng(20261120)


def pool(which: str) -> pd.DataFrame:
    h = pd.read_parquet(OUT / f"{which}_held.parquet")
    h["new_unit"] = h.n_unit == (0 if which == "bt" else 1)
    h["x"] = h.gap.clip(-0.5, 0.5)
    h["set"] = which
    return h


def rank(h: pd.DataFrame, least: int) -> pd.DataFrame:
    m = h[(h.half == "A") & (h.bld_age <= 3) & (h.bedrooms >= 2) & h.new_unit]
    g = m.groupby("building").x.agg(["mean", "size"])
    g = g[(g["size"] >= least) & ~g.index.isin(NAMED)]
    g["score"] = g["mean"].abs() * np.sqrt(g["size"])
    return g.sort_values("score", ascending=False)


def dossier(h: pd.DataFrame, building: str) -> dict:
    g = h[h.building == building]
    big = g[(g.bedrooms >= 2) & g.new_unit]
    if len(big) > 12:
        big = big.sample(12, random_state=1)
    small = g[g.bedrooms < 2]
    if len(small) > 4:
        small = small.sample(4, random_state=1)
    ads = []
    for r in pd.concat([big, small]).sort_values("label").itertuples():
        ads.append(
            {
                "ad": r.listing_id,
                "unit_label": r.label,
                "bedrooms": float(r.bedrooms),
                "full_baths": None if pd.isna(r.full_baths) else float(r.full_baths),
                "half_baths": None if pd.isna(r.half_baths) else float(r.half_baths),
                "coded_square_feet": None if pd.isna(r.square_feet) else r.square_feet,
                "has_floor_plan_image": bool(r.n_plans > 0),
                "month": str(r.day)[:7],
                "text": MONEY.sub("[amount]", r.description or ""),
            }
        )
    return {"building": building, "ads": ads}


if __name__ == "__main__":
    picked = []
    out = []
    pools = {w: pool(w) for w in ("bt", "l2")}
    for w, least in (("bt", 3), ("l2", 4)):
        h = pools[w]
        g = rank(h, least)
        taken = {b for _, b, _, _, _ in picked}
        miss = [b for b in g.index if b not in taken][:8]
        calm = g[~g.index.isin(miss) & ~g.index.isin(taken)]
        calm = list(calm.sort_values("score").index[: 6 if w == "bt" else 4])
        for role, names in (("miss", miss), ("control", calm)):
            for b in names:
                picked.append((w, b, role, g.loc[b, "mean"], int(g.loc[b, "size"])))
                out.append(dossier(h, b))
    h = pools["bt"]
    for b in NAMED:
        m = h[(h.building == b) & (h.bedrooms >= 2) & h.new_unit]
        picked.append(("bt", b, "named", m.x.mean(), len(m)))
        out.append(dossier(h, b))
    p = pd.DataFrame(picked, columns=["set", "building", "role", "mean_gap", "ads"])
    order = rng.permutation(len(out))
    p["group"] = np.argsort(order) % 6
    p.to_csv(OUT / "picked.csv", index=False)
    print(p.round(3).to_string())
    for k in range(6):
        ds = [out[i] for i in order if np.argsort(order)[i] % 6 == k]
        (OUT / f"dossier_{k}.json").write_text(json.dumps(ds, indent=1))
        print(
            k,
            len(ds),
            "buildings",
            sum(len(d["ads"]) for d in ds),
            "ads",
            sum(len(a["text"]) for d in ds for a in d["ads"]),
            "chars",
        )
