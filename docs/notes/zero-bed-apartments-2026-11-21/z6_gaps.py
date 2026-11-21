"""Question 3: does the miscoding move the model? Held-out errors of the latest split.

Run: `drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt` (189,647 held-out
ads; its dataset `b0-b3ddebf19af1dc1e-...-closingraise-bedtext`). The gap is the log ask less
the predictive median (`y - pred`). The 95% interval is `q[:, 0]` to `q[:, 7]`.

The mark is coded from counts and text only, on held-out ads coded 0 bed in the run's rows:
- `T`: the run dataset's own `bed_text_more` and `bed_text` >= 2;
- `U_strict`, `U_clean`, `U_any`: the unit's other typed ads in the live build
  (`zeros.parquet` of `z2_marks.py`);
- `in_ledger`: an active ledger entry names the ad now (reported apart, since a set there
  has already changed or dropped the row).
For each group: ads, mean gap with its building-clustered SE, SD of the gap, the share above
the 97.5% and below the 2.5% quantile, and 95% coverage, per half of buildings.
"""

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUT = Path("/data1/apartments/tmp/zero-bed")
RUN = Path(
    "/data1/apartments/frontier/runs/"
    "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"
)
ROWS = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet"
)
SEED = "commercial-sweep-2026-11-20"


def half(b: str) -> str:
    return "AB"[hashlib.sha1((SEED + b).encode()).digest()[0] & 1]


def clse(x: np.ndarray, b: np.ndarray) -> float:
    """Building-clustered SE of the mean of `x`."""
    n = len(x)
    if n < 2:
        return float("nan")
    r = pd.Series(x - x.mean()).groupby(b).sum()
    k = len(r)
    if k < 2:
        return float("nan")
    return math.sqrt(k / (k - 1) * float((r**2).sum())) / n


def summary(g: pd.DataFrame) -> dict:
    x = g.gap.to_numpy()
    return dict(
        ads=len(g),
        bld=g.building.nunique(),
        mean=round(float(x.mean()), 3) if len(g) else np.nan,
        se=round(clse(x, g.building.to_numpy()), 3),
        sd=round(float(x.std()), 3) if len(g) else np.nan,
        hi_tail=round(float((g.cdf > 0.975).mean()), 3),
        lo_tail=round(float((g.cdf < 0.025).mean()), 3),
        cover95=round(float(g.inside.mean()), 3),
    )


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    z = np.load(RUN / "pred_scores.npz")
    h = z["heldout"]
    R = pq.read_table(
        ROWS,
        columns=["listing_id", "building", "bedrooms", "bed_text", "bed_text_more"],
    ).to_pandas()
    R = R[h].reset_index(drop=True)
    assert (R.listing_id.astype(str).to_numpy() == z["listing"]).all()
    R["listing_id"] = R.listing_id.astype(str)
    R["gap"] = z["y"] - z["pred"]
    R["cdf"] = z["cdf"]
    R["inside"] = (z["y"] >= z["q"][:, 0]) & (z["y"] <= z["q"][:, 7])
    R["half"] = R.building.fillna("").map(half)
    Z = pd.read_parquet(
        OUT / "zeros.parquet",
        columns=["listing_id", "u2", "u1", "u0", "in_ledger"],
    )
    R = R.merge(Z, on="listing_id", how="left")
    zero = R.bedrooms == 0
    R["T"] = zero & R.bed_text_more.fillna(False).astype(bool) & (R.bed_text >= 2)
    u2 = R.u2.fillna(0) > 0
    R["U_any"] = zero & u2
    R["U_clean"] = zero & u2 & (R.u1.fillna(0) == 0)
    R["U_strict"] = R.U_clean & (R.u0.fillna(0) == 0)
    R["led"] = R.in_ledger.astype("boolean").fillna(False).astype(bool)
    print(
        "held-out",
        len(R),
        "coded 0",
        int(zero.sum()),
        "coded 0 now in ledger",
        int((zero & R.led).sum()),
    )
    groups = {
        "all held-out": R.index == R.index,
        "all coded 0": zero,
        "coded 0, no mark": zero & ~R["T"] & ~R.U_any,
        "T": R["T"],
        "U_strict": R.U_strict,
        "U_strict, not T": R.U_strict & ~R["T"],
        "U_clean": R.U_clean,
        "U_any": R.U_any,
        "U_any, not T": R.U_any & ~R["T"],
        "T or U_strict": R["T"] | R.U_strict,
        "T or U_any (the mark)": R["T"] | R.U_any,
    }
    for name, sub in [
        ("both halves, not in ledger", ~R.led),
        ("half A", ~R.led & (R.half == "A")),
        ("half B", ~R.led & (R.half == "B")),
        # The 2026-11-12 sprint chose its ads partly by their gap, so leaving the ledger's
        # ads out conditions the groups above on a set chosen by rent. These keep them in.
        ("both halves, ledger-named ads kept in", R.index == R.index),
        ("half A, ledger-named ads kept in", R.half == "A"),
        ("half B, ledger-named ads kept in", R.half == "B"),
    ]:
        t = pd.DataFrame({k: summary(R[v & sub]) for k, v in groups.items()}).T
        print(f"\n== {name}\n" + t.to_string())
    t = pd.DataFrame(
        {k: summary(R[v & R.led]) for k, v in groups.items() if k != "all held-out"}
    ).T
    print("\n== coded 0 in the run and named by the ledger since\n" + t.to_string())
    for k in ("T", "U_strict", "U_any"):
        print(
            k,
            "held-out bed_text values",
            R[R[k] & ~R.led].bed_text.value_counts().to_dict(),
        )
