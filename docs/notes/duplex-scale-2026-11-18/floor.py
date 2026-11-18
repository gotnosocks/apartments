"""Free check: the duplex mark split by the ad's floor, on the base model's held-out ads.

Joins the text mark `duplex` and the ad's floor (the physical floor, else the labelled one)
to the held-out predictions of `drift-building-b0-latest-67d14e17-b9`, with income ads
left out. For each half of the buildings it prints the mean log gap and the shares below
the 10% point and above the 90% point by elevator, floor and mark. It then scores four
marks as single terms on the standardized gap: the cross-validated share explained
against the 95% point of 100 shuffles of the mark.

Run from the repo root: python docs/notes/duplex-scale-2026-11-18/floor.py
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

ROWS = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse/rows.parquet"
)
RUN = "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz"
ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
HALVES = "/data1/apartments/tmp/low-outliers-2026-11-18/held_b9.parquet"


def cv(z, x, fold):
    """The share of `z`'s variance a slope on `x` explains on folds it was not fit on."""
    pred = np.empty_like(z)
    for k in range(5):
        tr = fold != k
        b = np.linalg.lstsq(np.c_[np.ones(tr.sum()), x[tr]], z[tr], rcond=None)[0]
        pred[~tr] = b[0] + b[1] * x[~tr]
    return 1 - ((z - pred) ** 2).sum() / ((z - z.mean()) ** 2).sum()


if __name__ == "__main__":
    fr = pd.read_parquet(
        ROWS, columns=["listing_id", "duplex", "income_restricted", "building"]
    )
    p = np.load(RUN, allow_pickle=True)
    h = fr[p["heldout"]].reset_index(drop=True)
    assert (h.listing_id.to_numpy() == p["listing"]).all()
    qs = list(p["quantiles"])
    iqr = p["q"][:, qs.index(0.75)] - p["q"][:, qs.index(0.25)]
    h["gap"] = p["y"] - p["pred"]
    h["cdf"] = p["cdf"]
    h["z"] = np.clip(h.gap / (iqr / (2 * norm.ppf(0.75))), -6, 6)
    h = h[~h.income_restricted.fillna(False).astype(bool)]
    a = pd.read_parquet(
        ADS, columns=["listing_id", "physical_floor", "label_floor", "elevator"]
    )
    a = a.drop_duplicates("listing_id")
    a["listing_id"] = a.listing_id.astype(h.listing_id.dtype)
    h = h.merge(a, on="listing_id", how="left")
    half = pd.read_parquet(HALVES, columns=["listing_id", "half"])
    half["listing_id"] = half.listing_id.astype(h.listing_id.dtype)
    h = h.merge(half, on="listing_id").reset_index(drop=True)
    f = h.physical_floor.fillna(h.label_floor)
    h["fl"] = np.select(
        [f.isna(), f <= 1, f == 2, f == 3], ["unknown", "1", "2", "3"], "4+"
    )
    h["el"] = h.elevator.fillna(False).astype(bool)
    h["dup"] = h.duplex.fillna(False).astype(bool)
    table = h.groupby(["half", "el", "fl", "dup"]).agg(
        n=("gap", "size"),
        gap=("gap", "mean"),
        low=("cdf", lambda c: (c < 0.1).mean()),
        high=("cdf", lambda c: (c > 0.9).mean()),
    )
    print(table.round(4).to_string())

    terms = {
        "duplex, floor 1": h.dup & (h.fl == "1"),
        "floor 1": h.fl == "1",
        "duplex": h.dup,
        "duplex, floor 6+": h.dup & (f >= 6),
    }
    rng = np.random.default_rng(20261118)
    for name in ("read", "unread"):
        m = (h.half == name).to_numpy()
        u = h[m]
        b = u.building.unique()
        fold = u.building.map(
            dict(zip(b, rng.permutation(np.arange(len(b)) % 5)))
        ).to_numpy()
        z = u.z.to_numpy()
        for k, v in terms.items():
            x = v[m].to_numpy(float)
            e = cv(z, x, fold)
            n95 = np.quantile(
                [cv(z, rng.permutation(x), fold) for _ in range(100)], 0.95
            )
            print(
                f"{name:7s} {k:18s} n {int(x.sum()):5d} mean z {z[x > 0].mean():+.3f} "
                f"others {z[x == 0].mean():+.3f} explained {e:+.5f} null95 {n95:+.5f} "
                f"{'pass' if e > max(0, n95) else 'fail'}"
            )
