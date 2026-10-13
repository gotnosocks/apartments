"""Compact linear ceiling: the as-of increment over C's own columns from the
top 5, 10 and 20 as-of columns, chosen inside the lot folds.

The rows are the new-building rung's training rows, without the five suspect
buildings (101+ rows on a lot with no residential units on record). In each
of the 5 lot folds the script:

    1. regresses the residual and every candidate column on C's own columns
       (training folds only);
    2. picks columns by greedy forward selection on what is left, adding at
       each step the column whose addition cuts the training sum of squares
       most;
    3. fits C's own columns plus the first 5, 10 or 20 picks by least squares
       and predicts the held-out fold.

Candidates are the as-of columns of held_data_ceiling.py (mean-filled), plus
one indicator for each distinct missing pattern. The increment is the change
in the board miss against C's own columns alone, row- and building-weighted
(each row weighs 1 / its building's rows), with 90% lot-cluster bootstrap
intervals. The script also selects once on all rows, for naming only.

    python held_data_ceiling_compact.py PER_ROW_FILE

Writes compact.json beside the other ceiling outputs.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import held_data_ceiling as hc  # noqa: E402
from held_data_ceiling_lotcheck import wmedian  # noqa: E402
from rentfrontier import explained, features  # noqa: E402

SIZES = (5, 10, 20)


def candidates(x, names):
    """Mean-filled, standardized columns plus one indicator per distinct
    missing pattern."""
    miss = np.isnan(x)
    filled = np.where(miss, np.nanmean(x, 0), x)
    cols, out = [], []
    for j, n in enumerate(names):
        if filled[:, j].std() > 0:
            cols.append(filled[:, j])
            out.append(n)
    seen = {}
    for j, n in enumerate(names):
        if miss[:, j].any() and not miss[:, j].all():
            key = np.packbits(miss[:, j]).tobytes()
            if key not in seen:
                seen[key] = n
                cols.append(miss[:, j].astype(float))
                out.append(f"no value: {n}")
    z = np.column_stack(cols)
    return (z - z.mean(0)) / z.std(0), out


def greedy(xo, z, r, k):
    """Forward selection of k columns of z on r, after partialling out xo."""
    a = xo.T @ xo + explained.RIDGE * np.eye(xo.shape[1])
    coef = np.linalg.solve(a, xo.T @ np.column_stack([z, r]))
    rest = np.column_stack([z, r]) - xo @ coef
    zt, rt = rest[:, :-1], rest[:, -1]
    g, c = zt.T @ zt, zt.T @ rt
    picked = []
    for _ in range(k):
        best, gain = None, -np.inf
        for j in range(z.shape[1]):
            if j in picked:
                continue
            s = picked + [j]
            v = c[s] @ np.linalg.solve(g[np.ix_(s, s)] + 1e-9 * np.eye(len(s)), c[s])
            if v > gain:
                best, gain = j, v
        picked.append(best)
    return picked


def ols(x, y):
    return np.linalg.solve(x.T @ x + explained.RIDGE * np.eye(x.shape[1]), x.T @ y)


def main(per_row_file):
    _, frame, heldout = hc._load_frame()
    base = features.build(hc.BASE, frame, ~heldout)
    own = pd.DataFrame(base.values, index=frame.audit_id)
    per = pd.read_parquet(per_row_file)
    per = per[per.rung == "new building"]
    flag = (per.row_bin == "101+") & (per.unitsres == 0)
    per = per[~flag].reset_index(drop=True)
    table = pd.read_parquet(hc.OUT / "features.parquet").set_index("audit_id")
    fam = json.loads((hc.OUT / "families.json").read_text())
    asof = [c for c, f in fam.items() if f in hc.AS_OF]
    xo = explained._design(hc._fill(own.loc[per.audit_id].to_numpy(float)))
    z, znames = candidates(table.loc[per.audit_id, asof].to_numpy(float), asof)
    print(f"rows {len(per)}, own {xo.shape[1]}, candidates {z.shape[1]}", flush=True)

    y, med = per.y.to_numpy(), per["median"].to_numpy()
    r = y - med
    lots = per.bbl.where(per.bbl.notna() & (per.bbl != "")).to_numpy()
    folds, groups = hc.lot_folds(
        per.building.to_numpy(), lots, np.random.default_rng(hc.SEED)
    )
    _, b_idx, b_n = np.unique(per.building, return_inverse=True, return_counts=True)
    w_b = 1.0 / b_n[b_idx]

    p_own = np.empty_like(r)
    p_k = {k: np.empty_like(r) for k in SIZES}
    picks = {k: [] for k in SIZES}
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        p_own[te] = xo[te] @ ols(xo[tr], r[tr])
        order = greedy(xo[tr], z[tr], r[tr], max(SIZES))
        for k in SIZES:
            s = order[:k]
            x = np.column_stack([xo, z[:, s]])
            p_k[k][te] = x[te] @ ols(x[tr], r[tr])
            picks[k].append([znames[j] for j in s])
        print(f"fold {f}: {[znames[j] for j in order[:10]]}", flush=True)

    def row_miss(q, i):
        return 100 * np.median(np.abs(np.exp(med[i] + q[i] - y[i]) - 1))

    def bld_miss(q, i):
        return 100 * wmedian(np.abs(np.exp(med[i] + q[i] - y[i]) - 1), w_b[i])

    result = {"rows": int(len(r)), "candidates": len(znames)}
    for k in SIZES:
        for weighting, miss in (("row", row_miss), ("building", bld_miss)):
            d = hc.boot(
                lambda i: miss(p_k[k], i) - miss(p_own, i),
                groups,
                np.random.default_rng(6),
                200,
            )
            result[f"top {k} / {weighting}"] = d
            print(
                f"top {k:2d} {weighting:8s} {d[0]:+.3f} pp [{d[1]:+.3f}, {d[2]:+.3f}]",
                flush=True,
            )
        counts = pd.Series([n for fold in picks[k] for n in fold]).value_counts()
        result[f"top {k} / picked in folds"] = counts.to_dict()
    order = greedy(xo, z, r, max(SIZES))
    result["all-row order"] = [znames[j] for j in order]
    print("all-row order:", result["all-row order"], flush=True)
    (hc.OUT / "compact.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
