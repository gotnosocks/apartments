"""S1: do segments of the market follow paths of their own in 2019 to 2023, beyond L1's
citywide walk and building paths?

Part A moves each held-out ad by the cross-fitted mean gap of its segment and quarter and
rescores L1's predictive. Part B builds a repeat-ad index for each segment from pairs of
consecutive training ads of a unit, on the other half of the buildings, and regresses each
held-out ad's gap on its segment's index change since the unit's previous ad, less the
citywide index's change."""

import json
import sys

import numpy as np
import pandas as pd

import common as c

d = c.rows()
print(d.elevator.value_counts(dropna=False).head(5).to_dict())
print(d.doorman_type.value_counts(dropna=False).head(8).to_dict())
beds = np.clip(d.bedrooms.round(), 0, 3).astype(int)
lift = (d.elevator == True) | d.doorman_type.isin(["full_time", "part_time"])  # noqa: E712
walk = (d.elevator == False) & ~lift  # noqa: E712
size = pd.cut(
    d.square_feet,
    [0, 600, 900, 1200, 1e9],
    labels=["<600", "600-900", "900-1200", "1200+"],
)
d["seg_beds"] = beds.astype(str)
d["seg_zone"] = np.where(d.manhattan, "mn", "out")
d["seg_lift"] = np.where(lift, "lift", np.where(walk, "walkup", "unknown"))
d["seg_size"] = size.astype(str).replace("nan", "none")
d["seg_cell"] = d.seg_beds + "|" + d.seg_zone + "|" + d.seg_lift
d["seg_all"] = "all"
d["q"] = d.day.dt.year * 4 + (d.day.dt.month - 1) // 3
# months and quarter of the unit's previous ad, any row of the dataset
d = d.sort_values(["ukey", "priced", "listing_id"])
same = d.ukey.eq(d.ukey.shift())
d["prev_q"] = np.where(same, d.q.shift(), np.nan)
d["prev_held"] = np.where(same, d.held.shift(), np.nan)
d["prev_y"] = np.where(same, np.log(d.latest_ask.shift()), np.nan)
d = d.sort_index()
# with names on the command line, only those segments and no Part B
ONLY = sys.argv[1:]
SEGS = ONLY or ["seg_all", "seg_beds", "seg_zone", "seg_lift", "seg_size", "seg_cell"]
h = c.heldout(d)
fold = h.fold.to_numpy()
sub = (pd.util.hash_array(h.building.astype(str).to_numpy() + "#") % 2).astype(int)
yr = h.day.dt.year
win = ((yr >= 2019) & (yr <= 2023)).to_numpy()
era = ((yr >= 2020) & (yr <= 2022)).to_numpy()
rest = win & ~era
gap = h.gap.to_numpy()
print("window ads", win.sum(), "era", era.sum(), "rest", rest.sum())


def cell_shift(seg, ks=(3, 10, 30, 100, 300)):
    """Cross-fitted shrunk mean gap of each ad's segment and quarter: estimated on the
    other half of the buildings, with k chosen on an inner split of that half."""
    key = h[seg].astype(str) + "@" + h.q.astype(str)
    out = np.zeros(len(h))
    picked = {}
    for f in (0, 1):
        est = (fold != f) & win

        def means(mask):
            g = pd.DataFrame({"k": key[mask], "g": gap[mask]}).groupby("k").g
            return g.sum(), g.size()

        # choose k on the estimation half: fit on one inner half, score the other
        err = {}
        for k in ks:
            e = 0.0
            for s in (0, 1):
                sm, n = means(est & (sub != s))
                tgt = est & (sub == s)
                kk = key[tgt]
                dl = (
                    sm.reindex(kk).fillna(0) / (n.reindex(kk).fillna(0) + k)
                ).to_numpy()
                e += float(((gap[tgt] - dl) ** 2).sum())
            err[k] = e
        k = min(err, key=err.get)
        picked[f] = k
        sm, n = means(est)
        tgt = (fold == f) & win
        kk = key[tgt]
        out[tgt] = (sm.reindex(kk).fillna(0) / (n.reindex(kk).fillna(0) + k)).to_numpy()
    return out, picked


def msg(x, m, clip=None):
    x = x[m]
    if clip is not None:
        x = np.clip(x, -clip, clip)
    return float(np.mean(x**2))


dr = c.Draws()
idx = np.flatnonzero(win)
res = {"n_window": int(win.sum()), "n_era": int(era.sum()), "segments": {}}
gains = {}
for clip in (None, 0.4):
    tag = "raw" if clip is None else "clip0.4"
    res[f"msg_era_{tag}"] = msg(gap, era, clip)
    res[f"msg_rest_{tag}"] = msg(gap, rest, clip)
res["cov_era"] = float(h.in80[era].mean())
res["cov_rest"] = float(h.in80[rest].mean())
for seg in SEGS:
    dl, k = cell_shift(seg)
    g1 = gap - dl
    r = {"k": k}
    for clip in (None, 0.4):
        tag = "raw" if clip is None else "clip0.4"
        ex = res[f"msg_era_{tag}"] - res[f"msg_rest_{tag}"]
        r[f"share_excess_removed_{tag}"] = (
            res[f"msg_era_{tag}"] - msg(g1, era, clip)
        ) / ex
        r[f"msg_rest_after_{tag}"] = msg(g1, rest, clip)
    e = dr.gain(idx, delta=dl)
    gains[seg] = e
    r["elpd_gain_window"] = float(e.sum())
    r["elpd_se_window"] = c.cluster_se(e, h.building.values[idx])
    if seg != "seg_all" and "seg_all" in gains:
        inc = e - gains["seg_all"]
        r["over_quarter"] = float(inc.sum())
        r["over_quarter_se"] = c.cluster_se(inc, h.building.values[idx])
    ee = e[era[idx]]
    r["elpd_gain_era"] = float(ee.sum())
    r["elpd_se_era"] = c.cluster_se(ee, h.building.values[idx][era[idx]])
    cov1 = (h.y >= h.lo + dl) & (h.y <= h.hi + dl)
    r["cov_era_after"] = float(cov1[era].mean())
    r["sd_shift_era"] = float(dl[era].std())
    res["segments"][seg] = r
    print(seg, json.dumps(r), flush=True)

pd.DataFrame(gains).assign(listing_id=h.listing_id.values[idx]).to_parquet(
    c.OUT + "s1_gains.parquet"
)
if ONLY:
    json.dump(res, open(c.OUT + "s1_" + "_".join(ONLY) + ".json", "w"), indent=1)
    sys.exit()

# Part B: segment repeat-ad indices from training pairs, cross-fitted by building half
tr = d[~d.held & d.prev_q.notna() & (d.prev_held == False)].copy()  # noqa: E712
tr = tr[(tr.q >= 2016 * 4) & (tr.prev_q >= 2016 * 4) & (tr.q > tr.prev_q)]
tr["dy"] = np.clip(np.log(tr.latest_ask) - tr.prev_y, -0.5, 0.5)
tr["fold"] = (pd.util.hash_array(tr.building.astype(str).to_numpy()) % 2).astype(int)
Q0, Q1 = 2016 * 4, 2026 * 4 + 3
nq = Q1 - Q0 + 1


def index(pairs, ridge=1.0):
    """Repeat-sales index by quarter: dy = I[q] - I[prev_q], I[Q0] = 0, ridge on steps."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import lsqr

    n = len(pairs)
    r = np.r_[np.arange(n), np.arange(n)]
    cidx = np.r_[pairs.q.to_numpy() - Q0, pairs.prev_q.to_numpy().astype(int) - Q0]
    v = np.r_[np.ones(n), -np.ones(n)]
    X = coo_matrix((v, (r, cidx)), shape=(n, nq)).tocsr()
    # smoothness ridge: ridge * (I[q] - I[q-1]) rows, plus pin I[Q0]
    D = coo_matrix(
        (
            np.r_[np.full(nq - 1, ridge), np.full(nq - 1, -ridge), [100.0]],
            (
                np.r_[np.arange(nq - 1), np.arange(nq - 1), [nq - 1]],
                np.r_[np.arange(1, nq), np.arange(nq - 1), [0]],
            ),
        ),
        shape=(nq, nq),
    ).tocsr()
    from scipy.sparse import vstack

    A = vstack([X, D])
    b = np.r_[pairs.dy.to_numpy(), np.zeros(nq)]
    return lsqr(A, b, atol=1e-10, btol=1e-10, iter_lim=5000)[0]


hp = h[np.isfinite(h.prev_q)].copy()
hp = hp[(hp.prev_q >= Q0) & (hp.q <= Q1)]
part_b = {}
for seg in ["seg_beds", "seg_zone", "seg_lift", "seg_cell"]:
    pred = np.full(len(hp), np.nan)
    for f in (0, 1):
        est = tr[tr.fold != f]
        city = index(est)
        for s, grp in est.groupby(seg):
            if len(grp) < 2000:
                continue
            ix = index(grp) - city
            m = (hp.fold.values == f) & (hp[seg].values == s)
            pred[m] = ix[hp.q.values[m] - Q0] - ix[hp.prev_q.values[m].astype(int) - Q0]
    ok = np.isfinite(pred)
    m_all = ok & ((hp.day.dt.year >= 2019) & (hp.day.dt.year <= 2023)).to_numpy()
    sl, se, a0 = c.wls_slope(
        hp.gap.values[m_all], pred[m_all], hp.building.values[m_all]
    )
    part_b[seg] = {
        "n": int(m_all.sum()),
        "slope": sl,
        "se": se,
        "sd_pred": float(np.nanstd(pred[m_all])),
        "p5_p95": [
            float(np.nanpercentile(pred[m_all], 5)),
            float(np.nanpercentile(pred[m_all], 95)),
        ],
    }
    print("B", seg, json.dumps(part_b[seg]), flush=True)
res["part_b"] = part_b
json.dump(res, open(c.OUT + "s1.json", "w"), indent=1)
