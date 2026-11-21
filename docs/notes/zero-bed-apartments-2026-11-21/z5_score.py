"""Question 2: precision of the mark from the 40 blind reads.

A read counts as a hit when its `best_count` is 2 or more. Precision is given per stratum with
a Wilson interval, and pooled over the mark by stratum weight (the stratum's share of the
13,089 marked rows) with a normal interval on the stratified variance. Also per form: `T`
(the two text strata), `U_strict` (rows of the strata with every other ad at 2 or more, and
text rows that also meet it), `U_any`. The reads go to `reads.csv` beside this script.
"""

import json
import math
from pathlib import Path

import pandas as pd

OUT = Path("/data1/apartments/tmp/zero-bed")
HERE = Path(__file__).resolve().parent
COUNT = {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5+": 5}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def stratified(D: pd.DataFrame, W: pd.Series) -> tuple[float, float, float]:
    """Pool-weighted precision over the strata in `D`, weights `W` (rows per stratum)."""
    g = D.groupby("stratum").hit.agg(["sum", "size"])
    w = W[g.index] / W[g.index].sum()
    p = g["sum"] / g["size"]
    est = float((w * p).sum())
    # a stratum read at 0 or 1 still carries variance: use the Wilson centre for it
    pc = (g["sum"] + 1.92) / (g["size"] + 3.84)
    se = math.sqrt(float((w**2 * pc * (1 - pc) / g["size"]).sum()))
    return est, max(0.0, est - 1.96 * se), min(1.0, est + 1.96 * se)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    L = pd.concat(
        [
            pd.read_json(p, lines=True, dtype=str)
            for p in sorted(OUT.glob("labels_*.ndjson"))
        ]
    )
    D = pd.read_parquet(OUT / "draw.parquet").merge(L, on="read_id", how="left")
    assert D.best_count.notna().all() and len(D) == 40
    D["best"] = D.best_count.map(COUNT)
    D["hit"] = D.best >= 2
    m = pd.read_parquet(
        OUT / "marked.parquet", columns=["listing_id", "stratum", "U_strict"]
    )
    D = D.merge(m[["listing_id", "U_strict"]], on="listing_id", how="left")
    W = m.stratum.value_counts()
    print("best_count by stratum")
    print(pd.crosstab(D.stratum, D.best_count).to_string())
    print("\nsame_apartment by stratum")
    print(pd.crosstab(D.stratum, D.same_apartment).to_string())
    rows = []
    for s, g in D.groupby("stratum"):
        lo, hi = wilson(int(g.hit.sum()), len(g))
        rows.append(
            (
                s,
                int(W[s]),
                len(g),
                int(g.hit.sum()),
                round(lo, 2),
                round(hi, 2),
                int(g[g.half == "A"].hit.sum()),
                int(g[g.half == "B"].hit.sum()),
            )
        )
    print("\nprecision by stratum (Wilson 95%)")
    print(
        pd.DataFrame(
            rows,
            columns=[
                "stratum",
                "pool",
                "read",
                "hit",
                "lo",
                "hi",
                "hit A of 5",
                "hit B of 5",
            ],
        ).to_string(index=False)
    )
    for name, sel in [
        ("mark (all strata)", D.stratum.notna()),
        ("T (text strata)", D.stratum.str.startswith("text")),
        ("U_any (unit strata and text and unit)", D.stratum != "text only"),
    ]:
        est, lo, hi = stratified(D[sel], W)
        print(f"{name}: pooled precision {est:.2f} (95% {lo:.2f} to {hi:.2f})")
    g = D[D.U_strict.fillna(False)]
    lo, hi = wilson(int(g.hit.sum()), len(g))
    print(
        f"U_strict reads {len(g)} hits {int(g.hit.sum())} (Wilson {lo:.2f} to {hi:.2f})"
    )
    t = D[D.bed_text.notna() & D.stratum.str.startswith("text")]
    print(
        "text strata: best equals bed_text",
        int((t.best == t.bed_text.clip(upper=5)).sum()),
        "of",
        len(t),
    )
    u = D[D.u2_min.notna() & D.hit]
    print(
        "hits with a unit count: best equals u2_min",
        int((u.best == u.u2_min.clip(upper=5)).sum()),
        "of",
        len(u),
    )
    keep = [
        "read_id",
        "listing_id",
        "building",
        "half",
        "stratum",
        "bed_text",
        "u2",
        "u1",
        "u0",
        "u2_min",
        "lister",
        "text_count",
        "same_apartment",
        "best_count",
        "quote",
        "reason",
    ]
    D[keep].sort_values("read_id").to_csv(HERE / "reads.csv", index=False)
    print(json.dumps({"reads": len(D), "hits": int(D.hit.sum())}))
