"""N4: the precision of each stratum, the draft rule and the whole pool, from the readers' answers.

I join the readers' answers (`reads/labels_K.jsonl`) to the key of `n3_draw.py`. A read counts
as a hit when the reader answered `commercial`. Live/work and unclear answers stay in the
denominator, and I also give the live/work share and the share with unclear reads left out.

Each read carries its cell's pool over its cell's take as a weight. For a set of cells I take
the weighted share of hits and give it a Wilson interval at the Kish effective size of its
weights, (sum w)^2 / sum w^2, which equals the number of reads when every weight is the same.
The sets are the strata, the draft rule's cells (`+`), the unmarked cells with an own signal
(`-`), all cells with an own signal, and the whole pool. As a post hoc look I also split the
reads with an own signal by each kind of backing they have.
"""

import glob
import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/nonresidential-2026-11-14/"
Z = 1.959963984540054


def wilson(p, n):
    if n == 0:
        return [float("nan"), float("nan")]
    den = 1 + Z**2 / n
    mid = (p + Z**2 / (2 * n)) / den
    half = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / den
    return [round(float(mid - half), 3), round(float(mid + half), 3)]


def share(g, col="hit"):
    w = g.weight
    p = float((w * g[col]).sum() / w.sum())
    n_eff = float(w.sum() ** 2 / (w**2).sum())
    return {
        "reads": len(g),
        "pool": int(g.drop_duplicates("cell").pool.sum()),
        "hits": int(g[col].sum()),
        "share": round(p, 3),
        "n_eff": round(n_eff, 1),
        "wilson95": wilson(p, n_eff),
    }


rows = [
    json.loads(s)
    for f in sorted(glob.glob(OUT + "reads/labels_*.jsonl"))
    for s in open(f)
]
lab = pd.DataFrame(rows)
assert lab.answer.isin(["residential", "commercial", "live_work", "unclear"]).all()
r = pd.read_parquet(OUT + "key.parquet").merge(lab, on="read_id", validate="1:1")
assert len(r) == 60
r["hit"] = r.answer == "commercial"
r["lw"] = r.answer == "live_work"
r["base"] = r.cell.str.rstrip("+-").str.replace(r"_(?:lot|other)$", "", regex=True)
own = r.cell.str.endswith(("+", "-"))
sets = {
    **{f"cell {k}": r[r.cell == k] for k in sorted(r.cell.unique())},
    **{f"stratum {k}": r[r.base == k] for k in sorted(r.base.unique())},
    "draft rule (+ cells)": r[r.cell.str.endswith("+")],
    "own signal, unmarked (- cells)": r[r.cell.str.endswith("-")],
    "own signal, all": r[own],
    "whole pool": r,
}
res = {"answers": r.answer.value_counts().to_dict(), "sets": {}}
for k, g in sets.items():
    known = g[g.answer != "unclear"]
    res["sets"][k] = share(g) | {
        "live_work_share": share(g, "lw")["share"],
        "share_without_unclear": share(known)["share"] if len(known) else None,
        "answers": g.answer.value_counts().to_dict(),
    }
res["post_hoc_by_kind"] = {}
for k in ["k_label", "k_other", "k_lot"]:
    g = r[own & r[k]]
    res["post_hoc_by_kind"][k] = {
        "reads": len(g),
        "hits": int(g.hit.sum()),
        "answers": g.answer.value_counts().to_dict(),
    }
r.drop(columns=["base"]).to_parquet(OUT + "reads.parquet", index=False)
json.dump(res, open(OUT + "precision.json", "w"), indent=1)
for k, v in res["sets"].items():
    print(
        f"{k:34s} reads {v['reads']:2d} pool {v['pool']:6d} hits {v['hits']:2d} "
        f"share {v['share']:.3f} {v['wilson95']} lw {v['live_work_share']:.3f}"
    )
print(json.dumps(res["post_hoc_by_kind"], indent=1))
