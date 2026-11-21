"""Precision of each mark on the blind reads, by half of the buildings.

Each read carries the weight of its stratum (pool over reads), so a mark's precision is the
weighted share of its read rows answered commercial or placeholder. Wilson intervals use the
Kish effective size. Rule forms are compared on half A and checked on half B.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("/data1/apartments/tmp/commercial-sweep")
HERE = Path(__file__).resolve().parent


def wilson(p, n, z=1.96):
    if n <= 0:
        return (np.nan, np.nan)
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def prec(x, hit):
    if len(x) == 0:
        return dict(reads=0, hits=0, precision=np.nan, lo=np.nan, hi=np.nan)
    w = x.w.to_numpy()
    h = hit(x).to_numpy()
    p = float((w * h).sum() / w.sum())
    neff = w.sum() ** 2 / (w * w).sum()
    lo, hi = wilson(p, neff)
    return dict(
        reads=len(x),
        hits=int(h.sum()),
        precision=round(p, 3),
        lo=round(lo, 2),
        hi=round(hi, 2),
    )


if __name__ == "__main__":
    L = pd.concat(
        [pd.read_json(p, lines=True) for p in sorted(OUT.glob("labels_*.ndjson"))]
    )
    D = pd.read_parquet(OUT / "draw.parquet").merge(L, on="read_id", how="left")
    assert D.answer.notna().all(), D[D.answer.isna()].read_id.tolist()
    D["w"] = D["pool"] / D.groupby("stratum").read_id.transform("size")
    M = pd.read_parquet(OUT / "marks.parquet")
    lab = M.set_index("listing_id")
    D["commercial_label"] = D.label.fillna("").str.contains(
        r"store|retail|comm|office|\bprof|shop|garage|parking", case=False
    )
    D["n_ratio_text"] = D.m_ratio & D.m_text
    print("answers by stratum")
    print(pd.crosstab(D.stratum, D.answer, margins=True))
    com = lambda x: x.answer == "commercial"  # noqa: E731
    bad = lambda x: x.answer.isin(["commercial", "placeholder"])  # noqa: E731
    ph = lambda x: x.answer == "placeholder"  # noqa: E731
    rows = []
    for name, sel, hit in (
        ("ratio: commercial or placeholder", D.m_ratio, bad),
        ("ratio: commercial", D.m_ratio, com),
        ("ratio with a text word", D.n_ratio_text, bad),
        ("ratio without a text word", D.m_ratio & ~D.m_text, bad),
        ("text: commercial", D.m_text, com),
        ("text without ratio: commercial", D.m_text & ~D.m_ratio, com),
        ("short: placeholder", D.m_short, ph),
        ("short coded 0 bed: placeholder", D.m_short & (D.bed == 0), ph),
        ("short coded 1+ bed: placeholder", D.m_short & (D.bed > 0), ph),
    ):
        for h in ("A", "B", "all"):
            x = D[sel & ((D.half == h) if h != "all" else True)]
            rows.append({"set": name, "half": h, **prec(x, hit)})
    T = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(T.to_string(index=False))
    print("\nby stratum and half, commercial or placeholder (unweighted counts)")
    print(
        D.assign(bad=bad(D))
        .groupby(["stratum", "half"])
        .agg(reads=("bad", "size"), bad=("bad", "sum"))
        .unstack()
        .fillna(0)
        .astype(int)
    )
    print("\nratio reads by text word, label and half")
    r = D[D.m_ratio]
    print(
        r.assign(bad=bad(r))
        .groupby(["half", "m_text", "commercial_label"])
        .agg(reads=("bad", "size"), bad=("bad", "sum"))
    )
    print("\nratio reads by ratio band and half (commercial or placeholder / reads)")
    r = r.assign(band=pd.cut(r.ratio, [3, 4, 6, 10, 1000]))
    print(
        r.assign(bad=bad(r))
        .groupby(["half", "band"], observed=True)
        .agg(reads=("bad", "size"), bad=("bad", "sum"))
    )
    D.drop(columns=["w"]).to_parquet(OUT / "reads.parquet")
    T.to_csv(HERE / "precision.csv", index=False)
    D[["read_id", "listing_id", "stratum", "half", "answer", "quote", "why"]].to_csv(
        HERE / "reads.csv", index=False
    )
    json.dump(
        {k: int(v) for k, v in D.answer.value_counts().items()},
        open(HERE / "answers.json", "w"),
    )
