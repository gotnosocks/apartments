"""S1, part C: does a segment's own path add anything once its static level is counted?

The segment by quarter shift of `s1_segments.py` mixes a fixed offset of the segment's
held-out ads with a path of its own. This script fits the means one after another on one half of
the buildings, each on what the earlier ones left:

1. a quarter mean;
2. a segment mean, then a quarter mean;
3. a segment mean, a quarter mean, then a segment by quarter mean.

Each mean is shrunk to zero by n / (n + k), with k picked on an inner split of the same half.
The script applies the sum to the other half and rescores L1's predictive on the held-out ads of 2019 to
2023. The gain of design 3 over design 2 is the segment's path."""

import json

import numpy as np
import pandas as pd

import common as c

KS = (3, 10, 30, 100, 300, 1000)

d = c.rows()
beds = np.clip(d.bedrooms.round(), 0, 3).astype(int)
lift = (d.elevator == True) | d.doorman_type.isin(["full_time", "part_time"])  # noqa: E712
walk = (d.elevator == False) & ~lift  # noqa: E712
d["seg_beds"] = beds.astype(str)
d["seg_zone"] = np.where(d.manhattan, "mn", "out")
d["seg_lift"] = np.where(lift, "lift", np.where(walk, "walkup", "unknown"))
d["seg_cell"] = d.seg_beds + "|" + d.seg_zone + "|" + d.seg_lift
d["q"] = (d.day.dt.year * 4 + (d.day.dt.month - 1) // 3).astype(str)
h = c.heldout(d)
h["pos"] = np.arange(len(h))
yr = h.day.dt.year
h = h[(yr >= 2019) & (yr <= 2023)].reset_index(drop=True)
gap = h.gap.to_numpy()
fold = h.fold.to_numpy()
sub = c.subfold(h.building)
bld = h.building.to_numpy()


def means(r, key, m, k):
    g = pd.DataFrame({"k": key[m], "g": r[m]}).groupby("k").g
    return g.sum(), g.size(), k


def apply(fit, key):
    sm, n, k = fit
    return (sm.reindex(key).fillna(0) / (n.reindex(key).fillna(0) + k)).to_numpy()


def sequential(keys):
    out = np.zeros(len(h))
    picked = []
    for f in (0, 1):
        est, tgt = fold != f, fold == f
        r = gap.copy()
        for key in keys:
            err = {}
            for k in KS:
                err[k] = 0.0
                for s in (0, 1):
                    t = est & (sub == s)
                    err[k] += float(
                        (
                            (r[t] - apply(means(r, key, est & (sub != s), k), key[t]))
                            ** 2
                        ).sum()
                    )
            k = min(err, key=err.get)
            fit = means(r, key, est, k)
            out[tgt] += apply(fit, key[tgt])
            r[est] -= apply(fit, key[est])
            picked.append(k)
    return out, picked


dr = c.Draws()
idx = h.pos.to_numpy()


def full(x):
    """A shift over the window's ads, spread onto all held-out ads (zero elsewhere)."""
    z = np.zeros(len(dr.y))
    z[idx] = x
    return z


q = h.q.astype(str).to_numpy()
base, kq = sequential([q])
e_q = dr.gain(idx, delta=full(base))
res = {
    "n": len(h),
    "quarter": {"gain": float(e_q.sum()), "se": c.cluster_se(e_q, bld), "k": kq},
}
print(json.dumps(res), flush=True)
for seg in ("seg_beds", "seg_zone", "seg_lift", "seg_cell"):
    s = h[seg].astype(str).to_numpy()
    sq = np.char.add(np.char.add(s.astype("U16"), "@"), q.astype("U8"))
    d2, k2 = sequential([s, q])
    d3, k3 = sequential([s, q, sq])
    e2 = dr.gain(idx, delta=full(d2))
    e3 = dr.gain(idx, delta=full(d3))
    r = {
        "static_over_quarter": [float((e2 - e_q).sum()), c.cluster_se(e2 - e_q, bld)],
        "path_over_static": [float((e3 - e2).sum()), c.cluster_se(e3 - e2, bld)],
        "k_static": k2,
        "k_path": k3,
        "sd_path_part": float((d3 - d2).std()),
        "in80_after": float(((h.y >= h.lo + d3) & (h.y <= h.hi + d3)).mean()),
    }
    res[seg] = r
    print(seg, json.dumps(r), flush=True)
res["in80_before"] = float(h.in80.mean())
json.dump(res, open(c.OUT + "s1b.json", "w"), indent=1)
