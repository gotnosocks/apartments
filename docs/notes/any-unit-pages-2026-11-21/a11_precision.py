"""Precision of each mark on the blind reads, by half, with Wilson 95% intervals.

A read counts as a hit when the reader answered "several". Unclear reads count against the
mark (a strict precision); the share among clear reads is given beside it. Writes
`reads.csv` (key joined to the answers).
"""

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("/data1/apartments/tmp/any-unit")
HERE = Path(__file__).resolve().parent


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 2), round(min(1.0, c + h), 2))


if __name__ == "__main__":
    L = pd.concat(
        pd.read_json(p, lines=True) for p in sorted(OUT.glob("labels_*.ndjson"))
    )
    K = pd.read_parquet(OUT / "read_key.parquet")
    D = K.merge(L, on="read_id", how="left")
    assert D.answer.notna().all() and len(D) == 60, D[D.answer.isna()].read_id.tolist()
    D.sort_values("read_id").drop(columns=["unit_id"]).to_csv(
        HERE / "reads.csv", index=False
    )
    print(pd.crosstab(D.stratum, D.answer, margins=True))
    rows = []
    sets = {
        "text": D.m_text,
        "overlap": D.m_overlap,
        "either": D.m_text | D.m_overlap,
        "unmarked": ~(D.m_text | D.m_overlap),
    }
    for name, sel in sets.items():
        for h in ("A", "B", "all"):
            x = D[sel & ((D.half == h) if h != "all" else True)]
            k, n = int((x.answer == "several").sum()), len(x)
            nc = int((x.answer != "unclear").sum())
            rows.append(
                dict(
                    set=name,
                    half=h,
                    reads=n,
                    several=k,
                    unclear=int((x.answer == "unclear").sum()),
                    precision=round(k / n, 2) if n else np.nan,
                    wilson=wilson(k, n),
                    among_clear=round(k / nc, 2) if nc else np.nan,
                    wilson_clear=wilson(k, nc),
                )
            )
    print(pd.DataFrame(rows).to_string(index=False))
    print(
        "\nthe-rheingold reads:",
        D[D.building == "the-rheingold"].answer.value_counts().to_dict(),
    )
    print(
        "text reads outside the-rheingold:",
        D[D.m_text & (D.building != "the-rheingold")].answer.value_counts().to_dict(),
    )
