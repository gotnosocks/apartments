"""Free checks behind the design of the slow unit level, on L2's saved held-out predictions and
the training rows alone.

Part A rescores L2's exact predictive after a cross-fitted correction b * m of each held-out
ad's location, with `m` the unit's training record of the gap screen (`h.parquet`). The slope b
is fitted on one half of the buildings and applied to the other, in these forms:

  static     b0 * m                              a factor on the record at every lag
  linear     b1 * m * L                          a correction growing with the lag L in years
  both       (b0 + b1 * L) * m
  decay(T)   b * m * (1 - exp(-L / T))           a slow decay of time constant T years

with L the years from the unit's previous ad (training-visible dates) to the ad.

Part B reads the training rows alone. Each training ad gets a residual r: its log ask less a
monthly index, less the mean of the other units' adjusted asks in its building, bedroom count
and year (the stand-in of `h1_history.py`, ad by ad). For every pair of training ads of one
unit, the script takes r_i * r_j and averages it by the lag between the two ads. Under L2's
kernel the covariance falls from ss^2 + sd^2 near lag 0 to a floor of ss^2 after about 8 years
(tau 2.6 years); a covariance still falling from 6 to 11 years is a lasting level that decays.

    systemd-run --user --scope -q -p MemoryMax=3G --setenv=OMP_NUM_THREADS=2 \
        /data1/apartments/venvs/bridge-frontier/bin/python screen.py <worktree>
"""

import json
import sys

import numpy as np
import pandas as pd

WT = sys.argv[1]
sys.path.insert(0, WT + "/docs/notes/causal-screens-2026-11-13")
import common as c  # noqa: E402

c.RUN = (
    "/data1/apartments/frontier/runs/"
    "drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn/"
)
GAP = "/data1/apartments/tmp/sprint-20261114/gap-screen/"
OUT = "/data1/apartments/tmp/sprint-20261114/unit-record/"
res = {}

# ---------------------------------------------------------------- part B, training pairs
d = pd.read_parquet(
    c.DATA,
    columns=["listing_id", "building", "unit_id", "price_at", "latest_ask", "bedrooms"],
)
d["held"] = np.load(c.RUN + "pred_scores.npz")["heldout"]
t = d[~d.held & (d.latest_ask > 0) & d.unit_id.notna()].copy()
del d
t["priced"] = t.price_at.dt.tz_convert(None)
t["ukey"] = t.building.astype(str) + "|" + t.unit_id.astype(str)
t["ly"] = np.log(t.latest_ask.astype(float))
t["mon"] = t.priced.dt.year * 12 + t.priced.dt.month
t["yr"] = t.priced.dt.year
dev = t.ly - t.groupby("ukey").ly.transform("mean")
idx = dev.groupby(t.mon).mean()
idx = idx.reindex(range(t.mon.min(), t.mon.max() + 1)).interpolate().bfill().ffill()
t["adj"] = t.ly - idx.reindex(t.mon).to_numpy()
cell = ["building", "bedrooms", "yr"]
g = t.groupby(cell).adj
t["gsum"], t["gn"] = g.transform("sum"), g.transform("size")
u = t.groupby(["ukey", *cell]).adj
t["usum"], t["un"] = u.transform("sum"), u.transform("size")
t["others"] = t.gn - t.un
t = t[t.others >= 3].copy()
t["r"] = t.adj - (t.gsum - t.usum) / t.others
t["ty"] = (t.priced - pd.Timestamp("2010-01-01")).dt.days / 365.25
t = (
    t[["ukey", "building", "ty", "r"]]
    .sort_values(["ukey", "ty"])
    .reset_index(drop=True)
)
size = t.groupby("ukey").ukey.transform("size").to_numpy()
t = t[(size >= 2) & (size <= 20)].reset_index(drop=True)
first = np.r_[0, np.flatnonzero(t.ukey.to_numpy()[1:] != t.ukey.to_numpy()[:-1]) + 1]
n = np.diff(np.r_[first, len(t)])
ty, r = t.ty.to_numpy(), t.r.to_numpy()
bld = pd.factorize(t.building)[0]
EDGES = [0, 0.25, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13]
acc = {k: [] for k in range(len(EDGES) - 1)}
for k in range(1, 20):
    sel = first[n > k]
    for j in range(k):
        # pairs (j, k) within each unit of more than k ads
        a, b = sel + j, sel + k
        lag = ty[b] - ty[a]
        bin_ = np.searchsorted(EDGES, lag, side="right") - 1
        ok = (bin_ >= 0) & (bin_ < len(EDGES) - 1)
        for q in np.unique(bin_[ok]):
            m = ok & (bin_ == q)
            acc[q].append(pd.DataFrame({"p": r[a[m]] * r[b[m]], "b": bld[a[m]]}))
tab = {}
for q, parts in acc.items():
    if not parts:
        continue
    p = pd.concat(parts)
    tab[f"{EDGES[q]}-{EDGES[q + 1]}"] = {
        "pairs": int(len(p)),
        "cov": float(p.p.mean()),
        "se": c.cluster_se(p.p, p.b) / len(p),
    }
res["B_training_pair_cov"] = tab
res["B_var"] = float(np.mean(r**2))
print(json.dumps(tab, indent=1), flush=True)
del t, acc

# ---------------------------------------------------------------- part A, held-out rescoring
h = pd.read_parquet(GAP + "h.parquet")
dr = c.Draws()
assert len(h) == len(dr.y)
gap, fold, b = h.gap.to_numpy(), h.fold.to_numpy(), h.building.to_numpy()
mc = h.m.clip(-0.4, 0.4).fillna(0).to_numpy()
have = h.m.notna().to_numpy()
L = h.since.fillna(0).to_numpy() / 12
allidx = np.arange(len(h))


def crossfit(cols):
    """Each ad's correction from a least-squares fit of the gap on an intercept and `cols`
    over the other half's ads with a record; the intercept is fitted and left out."""
    out = np.zeros(len(h))
    coefs = []
    for f in (0, 1):
        est = have & (fold != f)
        X = np.column_stack([np.ones(est.sum())] + [v[est] for v in cols])
        beta = np.linalg.lstsq(X, gap[est], rcond=None)[0]
        tgt = have & (fold == f)
        out[tgt] = np.column_stack([v[tgt] for v in cols]) @ beta[1:]
        coefs.append([float(x) for x in beta[1:]])
    return out, coefs


forms = {"static": [mc], "linear": [mc * L], "both": [mc, mc * L]}
for T in (5, 10, 20, 40, 80):
    forms[f"decay{T}"] = [mc * (1 - np.exp(-L / T))]
gains = {}
for name, cols in forms.items():
    delta, coefs = crossfit(cols)
    gg = dr.gain(allidx, delta=delta)
    gains[name] = gg
    res["A_" + name] = {
        "gain": float(gg.sum()),
        "se": c.cluster_se(gg, b),
        "coefs": coefs,
    }
    print(name, res["A_" + name], flush=True)
for a_, b_ in [("both", "static"), ("both", "linear")]:
    dd = gains[a_] - gains[b_]
    res[f"A_{a_}_over_{b_}"] = [float(dd.sum()), c.cluster_se(dd, b)]
json.dump(res, open(OUT + "screen.json", "w"), indent=1)
