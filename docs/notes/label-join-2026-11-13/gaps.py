"""L1's held-out ads in units v18 splits, at 175 Spencer Street and elsewhere, and their
difference from L1's other held-out ads, with SEs clustered by building; and a check that the
copy's split is L1's."""

import json

import numpy as np
import pandas as pd

S = "/data1/apartments/tmp/sprint-20261113/label-join"
L1 = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1"
OUT = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-labeljoin"


def cluster_se(x, b):
    """SE of the sum of `x` about its mean, clustered by `b`."""
    x = np.asarray(x, dtype=float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


def diff_se(x, a, b):
    """SE of the mean of `x` where `a` holds less its mean elsewhere, with both groups clustered
    together by `b`: each building sums its ads' parts of the difference."""
    x = np.asarray(x, dtype=float)
    a = np.asarray(a, dtype=bool)
    part = np.where(a, (x - x[a].mean()) / a.sum(), -(x - x[~a].mean()) / (~a).sum())
    t = pd.Series(part).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


s = np.load(f"{L1}/pred_scores.npz", allow_pickle=True)
held = s["heldout"]
u = pd.read_parquet(f"{S}/l1_units.parquet", columns=["insplit", "split17", "split18"])
insplit = u.insplit.fillna(False).to_numpy(bool)
change = (u.split17 != u.split18).fillna(False).to_numpy(bool)
copy = pd.read_parquet(f"{OUT}/rows.parquet", columns=["carried_heldout", "building"])
carried = copy.carried_heldout.to_numpy(bool)
print(
    "carried within L1's held-out",
    bool((carried <= held).all()),
    int(held.sum()),
    int(carried.sum()),
)
b = s["building"].astype(str)
spencer = np.char.find(b, "175-spencer") >= 0
print("spencer buildings", sorted(set(b[spencer])))
gap = s["y"] - s["pred"]
res = {}
h_in = insplit[held]
h_carried = carried[held]
for name, mask in (
    ("in_split_units", h_in),
    ("in_split_at_spencer", h_in & spencer),
    ("in_split_elsewhere", h_in & ~spencer),
    ("other_ads", ~h_in),
    ("in_split_dropped_from_carried", h_in & ~h_carried),
):
    n = int(mask.sum())
    if n < 2:
        res[name] = {"n": n}
        continue
    res[name] = {
        "n": n,
        "buildings": int(len(set(b[mask]))),
        "gap_pct": round(100 * float(gap[mask].mean()), 2),
        "gap_se_pct": round(100 * cluster_se(gap[mask], b[mask]) / n, 2),
        "sq_gap": round(float((gap[mask] ** 2).mean()), 5),
        "sq_gap_se": round(cluster_se(gap[mask] ** 2, b[mask]) / n, 5),
        "elpd": round(float(s["elpd"][mask].mean()), 3),
    }
res["in_split_minus_other"] = {
    "gap_pct": round(100 * float(gap[h_in].mean() - gap[~h_in].mean()), 2),
    "gap_se_pct": round(100 * diff_se(gap, h_in, b), 2),
    "sq_gap": round(float((gap[h_in] ** 2).mean() - (gap[~h_in] ** 2).mean()), 5),
    "sq_gap_se": round(diff_se(gap**2, h_in, b), 5),
    "elpd": round(float(s["elpd"][h_in].mean() - s["elpd"][~h_in].mean()), 3),
    "elpd_se": round(diff_se(s["elpd"], h_in, b), 3),
}
rows_spencer = copy.building.astype(str).str.contains("175-spencer").to_numpy()
res["rows"] = {
    "changing_unit": int(change.sum()),
    "changing_unit_at_spencer": int((change & rows_spencer).sum()),
    "in_split_units": int(insplit.sum()),
    "in_split_units_at_spencer": int((insplit & rows_spencer).sum()),
    "heldout_changing_unit_at_spencer": int((change & rows_spencer & held).sum()),
}
print(json.dumps(res, indent=1))
json.dump(res, open(f"{S}/gaps.json", "w"), indent=1)
