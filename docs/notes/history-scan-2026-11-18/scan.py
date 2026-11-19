"""Scan of ad-text terms against held-out errors of the base model (run b9).

Each held-out ad has a place in its predictive distribution (`cdf`). z is the normal score
of that place: negative when the ask is below the prediction. Buildings are split in two
halves by a hash; terms are ranked on half A and re-measured on half B. For each word and
two-word phrase present in at least MIN_DF ads and MIN_BLD buildings of a half, the scan
prints the mean z of the ads holding it less the half's mean, with a t statistic clustered
by building, and the share of its ads below the 5% point.
"""

import hashlib
import re
import sys

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import norm

RUN = "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz"
TEXTS = "/data1/apartments/tmp/history-scan/texts-b9.parquet"
OUT = "/data1/apartments/tmp/history-scan"
SEED = "history-scan-2026-11-18"
MIN_DF, MIN_BLD = 150, 40
TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?|#")


def half(building: str) -> int:
    return hashlib.sha1((SEED + building).encode()).digest()[0] & 1


def tokens(text: str) -> list[str]:
    t = re.sub(r"\d[\d,.]*", "#", text.lower())
    return TOKEN.findall(t)


def terms(text: str) -> set[str]:
    w = tokens(text)
    return set(w) | {f"{a} {b}" for a, b in zip(w, w[1:])}


def stats(X, z, low, bld):
    """Per column of X: ads, buildings, mean z less the overall mean, clustered t, low share."""
    n = np.asarray(X.sum(0)).ravel()
    zc = z - z.mean()
    s = np.asarray(X.T @ zc).ravel()
    m = s / np.maximum(n, 1)
    B = sparse.csr_matrix((np.ones(len(bld)), (bld, np.arange(len(bld)))))
    C = (B @ X).tocsc()
    S = (B @ sparse.diags(zc) @ X).tocsc()
    nb = np.diff(C.indptr)
    # S and C share a pattern only where S has no exact zero, so align through C's pattern.
    D = (S - C @ sparse.diags(m)).tocsc()
    var = np.asarray(D.multiply(D).sum(0)).ravel() / np.maximum(n, 1) ** 2
    lo = np.asarray(X.T @ low.astype(float)).ravel() / np.maximum(n, 1)
    return n, nb, m, m / np.sqrt(np.maximum(var, 1e-12)), lo


if __name__ == "__main__":
    s = np.load(RUN)
    d = pd.DataFrame(
        {"listing_id": s["listing"], "cdf": s["cdf"], "building": s["building"]}
    )
    t = pd.read_parquet(TEXTS)
    t["listing_id"] = t.listing_id.astype(str)
    d = d.merge(t[["listing_id", "description"]], on="listing_id", how="left")
    d = d[d.description.fillna("").str.len() >= 40].reset_index(drop=True)
    d["z"] = norm.ppf(d.cdf.clip(1e-4, 1 - 1e-4))
    d["half"] = d.building.map(half)
    print(
        "ads with a text",
        len(d),
        "by half",
        d.half.value_counts().to_dict(),
        flush=True,
    )
    sets = [terms(x) for x in d.description]
    a = (d.half == 0).to_numpy()
    df = {}
    for keep, ts in zip(a, sets):
        if keep:
            for w in ts:
                df[w] = df.get(w, 0) + 1
    vocab = sorted(w for w, c in df.items() if c >= MIN_DF)
    index = {w: i for i, w in enumerate(vocab)}
    print("terms", len(vocab), flush=True)
    rows, cols = [], []
    for i, ts in enumerate(sets):
        for w in ts:
            j = index.get(w)
            if j is not None:
                rows.append(i)
                cols.append(j)
    X = sparse.csr_matrix(
        (np.ones(len(rows), np.float32), (rows, cols)), (len(d), len(vocab))
    )
    out = pd.DataFrame({"term": vocab})
    for h, name in ((0, "a"), (1, "b")):
        k = (d.half == h).to_numpy()
        bld = pd.factorize(d.building[k])[0]
        n, nb, m, tt, lo = stats(
            X[k].tocsc(), d.z[k].to_numpy(), (d.cdf[k] < 0.05).to_numpy(), bld
        )
        for c, v in (("n", n), ("bld", nb), ("dz", m), ("t", tt), ("low", lo)):
            out[f"{c}_{name}"] = v
        print(f"half {name}: ads {k.sum()}, low share {(d.cdf[k] < 0.05).mean():.4f}")
    out.to_parquet(f"{OUT}/terms.parquet")
    d[["listing_id", "building", "cdf", "z", "half"]].to_parquet(f"{OUT}/ads.parquet")
    sparse.save_npz(f"{OUT}/X.npz", X)
    ok = out[(out.bld_a >= MIN_BLD)]
    pd.set_option("display.width", 200)
    for label, asc in (
        ("asked below prediction", True),
        ("asked above prediction", False),
    ):
        top = ok.sort_values("t_a", ascending=asc).head(
            int(sys.argv[1]) if len(sys.argv) > 1 else 80
        )
        print(f"\n== half A, {label}")
        print(top.round(3).to_string(index=False))
