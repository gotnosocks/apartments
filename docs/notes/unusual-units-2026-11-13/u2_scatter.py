"""S14, part 2: do penthouses, garden apartments and townhouse floors scatter wider around L1's
median, as duplexes do?

For each mark of `u1_text.py`, and for S7's duplex mark beside it, the script counts the rows and
units the mark covers in L1's dataset and among L1's held-out ads. On the held-out ads it reads:

1. the gap from L1's median against the rest, overall and within building;
2. the clipped squared gap and 80% coverage against the rest, as `s7b_spread.py` computes
   them, and the clipped squared gap within building;
3. the multiplier m on L1's noise scale and unit sd, picked on one half of the buildings and
   scored on the other, both ways, as `s7d_scale.py` does. The null runs the same search on as
   many held-out ads drawn at random from those with none of the four marks.

The within-building reads use only buildings with at least two held-out ads. A building with
n held-out ads leaves an ad's gap less the building's mean at (n-1)/n of the ad's variance
about that mean, so the script multiplies the squared gap less the building's mean by n/(n-1).
For the gap it subtracts the mean of the building's other held-out ads, which is the gap less
the building's mean times n/(n-1).

Each kind is also read without the ads S7's duplex pattern marks, against the other ads it
leaves unmarked, since D1 already widens the duplexes. A search picks one m for the duplex
ads and a kind's ads together, as a shared mark in D1 would, and scores what that adds over
the duplex ads alone.

For the text penthouses without duplexes, and for the duplexes without penthouses, the script
also puts an interval on m. It resamples the mark's buildings with replacement 2,000 times
and records the m with the largest total over the resampled ads, and the m each half of the
resampled buildings picks. The profile lists the m whose total is within 2 SEs of the best,
with the SE of each total's difference from the best clustered by building.

An ad's log predictive density depends only on its own multiplier, so the script rescores each
held-out ad once per value of m and sums the gains over each group. SEs are clustered by
building, with each sum taken about its mean as in `coop-column-2026-11-13/count.py`."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

OUT = c.OUT + "unusual-units/"
GRID = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0)
KINDS = {"pen": "penthouse", "gar": "garden", "town": "townhouse", "dup": "duplex"}


def cluster_se(x, b):
    """SE of the sum of `x` about its mean, clustered by `b`."""
    x = np.asarray(x, dtype=float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


tx = pd.read_parquet(
    OUT + "u1_text.parquet",
    columns=["listing_id", "pen", "gar", "town", "pen_text", "pen_label"],
)
dup = pd.read_parquet(c.OUT + "s7_text.parquet", columns=["listing_id", "dup_unit"])
dup["listing_id"] = dup.listing_id.astype(str)
d = c.rows()
d["listing_id"] = d.listing_id.astype(str)
d = d.merge(tx, on="listing_id", how="left").merge(dup, on="listing_id", how="left")
d = d.rename(columns={"dup_unit": "dup"})
for k in [*KINDS, "pen_text", "pen_label"]:
    d[k] = d[k].fillna(False).astype(bool)
d["any3"] = d.pen | d.gar | d.town
h = c.heldout(d)
h["sq"] = h.gap.clip(-0.4, 0.4) ** 2
n_b = h.groupby("building").gap.transform("size").to_numpy()
loo = np.where(n_b >= 2, n_b / np.maximum(n_b - 1, 1), np.nan)
h["wsq"] = c.within(h.gap.clip(-0.4, 0.4), h.building) ** 2 * loo
h["wgap"] = c.within(h.gap, h.building) * loo
h["single"] = n_b == 1
b = h.building.to_numpy()
res = {"rows": len(d), "heldout": len(h)}

# counts and overlaps
res["counts"] = {
    k: {
        "rows": int(d[k].sum()),
        "row_share": float(d[k].mean()),
        "units": int(d.ukey[d[k]].nunique()),
        "heldout": int(h[k].sum()),
        "heldout_share": float(h[k].mean()),
        "heldout_units": int(h.ukey[h[k]].nunique()),
    }
    for k in [*KINDS, "any3"]
}
res["counts"]["pen"]["heldout_text"] = int(h.pen_text.sum())
res["counts"]["pen"]["heldout_label"] = int(h.pen_label.sum())
res["counts"]["pen"]["heldout_label_only"] = int((h.pen_label & ~h.pen_text).sum())
res["overlap_rows"] = {
    f"{a}&{z}": int((d[a] & d[z]).sum()) for a in KINDS for z in KINDS if a < z
}
res["overlap_heldout"] = {
    f"{a}&{z}": int((h[a] & h[z]).sum()) for a in KINDS for z in KINDS if a < z
}


def combo(x):
    on = [KINDS[k] for k in ("pen", "gar", "town", "dup") if x[k]]
    return "+".join(on) if on else "none"


h["combo"] = h[list(KINDS)].apply(combo, axis=1)
res["joint"] = [
    {
        "cell": k,
        "n": len(v),
        "gap": float(v.gap.mean()),
        "sq": float(v.sq.mean()),
        "in80": float(v.in80.mean()),
    }
    for k, v in h.groupby("combo")
]
print(pd.DataFrame(res["joint"]).round(4).to_string(), flush=True)


def contrast(on, rest):
    """The marked ads against the rest, on the ads in `on | rest`."""
    m = on | rest
    x, o, bb = h[m], on[m], b[m]
    return {
        "n_on": int(o.sum()),
        "gap_on": float(x.gap[o].mean()),
        "gap_diff": c.cluster_mean_diff(x.gap.to_numpy(), o, bb),
        "within_gap_diff": c.cluster_mean_diff(x.wgap.to_numpy(), o, bb),
        "single_on": float(x.single[o].mean()),
        "single_off": float(x.single[~o].mean()),
        "wsq_on": float(x.wsq[o].mean()),
        "wsq_off": float(x.wsq[~o].mean()),
        "sq_on": float(x.sq[o].mean()),
        "sq_off": float(x.sq[~o].mean()),
        "sq_diff": c.cluster_mean_diff(x.sq.to_numpy(), o, bb),
        "within_sq_diff": c.cluster_mean_diff(x.wsq.to_numpy(), o, bb),
        "in80_on": float(x.in80[o].mean()),
        "in80_off": float(x.in80[~o].mean()),
        "in80_diff": c.cluster_mean_diff(x.in80.to_numpy(float), o, bb),
    }


mk = {k: h[k].to_numpy() for k in [*KINDS, "any3", "pen_text", "pen_label"]}
nodup = ~mk["dup"]
groups = {k: (mk[k], ~mk[k]) for k in [*KINDS, "any3"]}
for k in ("pen", "gar", "town", "any3"):
    groups[k + "_nodup"] = (mk[k] & nodup, ~mk[k] & nodup)
groups["pen_label_only"] = (mk["pen_label"] & ~mk["pen_text"], ~mk["pen"])
groups["pen_text"] = (mk["pen_text"], ~mk["pen"])
groups["pen_text_nodup"] = (mk["pen_text"] & nodup, ~mk["pen"] & nodup)
groups["dup_nopen"] = (mk["dup"] & ~mk["pen"], ~mk["dup"] & ~mk["pen"])
res["spread"] = {k: contrast(on, rest) for k, (on, rest) in groups.items()}
for k, v in res["spread"].items():
    print(k, json.dumps(v), flush=True)

# the multiplier m: rescore each ad once per m
none4 = ~(mk["pen"] | mk["gar"] | mk["town"] | mk["dup"])
rng = np.random.default_rng(20261114)
search = {k: np.flatnonzero(groups[k][0]) for k in groups}
for k in ("pen", "gar", "town", "pen_nodup", "gar_nodup", "town_nodup", "any3_nodup"):
    search["null_" + k] = np.sort(
        rng.choice(np.flatnonzero(none4), len(search[k]), replace=False)
    )
for k in ("pen", "gar", "town", "pen_text"):
    search["dup_or_" + k] = np.flatnonzero(mk["dup"] | mk[k])
idx = np.unique(np.concatenate(list(search.values())))
dr = c.Draws()
base = dr.elpd(idx)
gains = {}
for m in GRID[1:]:
    scale = np.ones(len(h), dtype=np.float32)
    scale[idx] = m
    gains[m] = dr.elpd(idx, scale=scale) - base
    print("m", m, flush=True)
del dr
gains[1.0] = np.zeros(len(idx))
pos = pd.Series(np.arange(len(idx)), index=idx)
fold = h.fold.to_numpy()


def crossfit(sel):
    """m picked on one half of the buildings for the ads `sel`, and each ad's gain under the
    m picked on the other half."""
    p = pos.loc[sel].to_numpy()
    f = fold[sel]
    picked, per_ad = {}, np.zeros(len(sel))
    for half in (0, 1):
        tot = {m: float(gains[m][p][f != half].sum()) for m in GRID}
        picked[half] = max(tot, key=tot.get)
        per_ad[f == half] = gains[picked[half]][p][f == half]
    return picked, per_ad


res["scale"] = {}
for k, sel in search.items():
    picked, per_ad = crossfit(sel)
    p = pos.loc[sel].to_numpy()
    out = {
        "n": len(sel),
        "grid_total": {str(m): float(gains[m][p].sum()) for m in GRID},
        "picked": picked,
        "crossfit_gain": float(per_ad.sum()),
        "se": cluster_se(per_ad, b[sel]),
    }
    if k.startswith("dup_or_"):
        # what the kind's ads add to a mark on the duplex ads alone
        extra = ~mk["dup"][sel]
        inc = per_ad.copy()
        inc[~extra] -= crossfit(search["dup"])[1]
        out["gain_on_extra"] = float(per_ad[extra].sum())
        out["gain_on_dup"] = float(per_ad[~extra].sum())
        out["increment"] = float(inc.sum())
        out["increment_se"] = cluster_se(inc, b[sel])
    res["scale"][k] = out
    print(k, json.dumps(out), flush=True)


def interval(sel, draws=2000):
    """The m picked on the mark's ads `sel` across resamples of its buildings, and the
    profile of m within 2 SEs of the best total."""
    p = pos.loc[sel].to_numpy()
    g = np.stack([gains[m][p] for m in GRID], axis=1)
    bid, bi = np.unique(b[sel], return_inverse=True)
    per_b = np.zeros((len(bid), len(GRID)))
    np.add.at(per_b, bi, g)
    half = np.zeros(len(bid), dtype=int)
    half[bi] = fold[sel]
    grid = np.asarray(GRID)
    w = np.stack(
        [
            np.bincount(boot.integers(0, len(bid), len(bid)), minlength=len(bid))
            for _ in range(draws)
        ]
    ).astype(float)
    whole = grid[(w @ per_b).argmax(axis=1)]
    halves = np.concatenate(
        [grid[((w * (half == f)) @ per_b).argmax(axis=1)] for f in (0, 1)]
    )
    tot = g.sum(axis=0)
    best = int(tot.argmax())
    se = [cluster_se(g[:, j] - g[:, best], b[sel]) for j in range(len(GRID))]
    q = [0.025, 0.975]
    return {
        "n": len(sel),
        "buildings": len(bid),
        "best": float(grid[best]),
        "whole_interval": np.quantile(whole, q, method="inverted_cdf").tolist(),
        "whole_counts": {str(m): int((whole == m).sum()) for m in GRID},
        "halves_interval": np.quantile(halves, q, method="inverted_cdf").tolist(),
        "halves_counts": {str(m): int((halves == m).sum()) for m in GRID},
        "profile": [m for j, m in enumerate(GRID) if tot[best] - tot[j] <= 2 * se[j]],
        "total_less_best": {
            str(m): float(tot[j] - tot[best]) for j, m in enumerate(GRID)
        },
        "se_less_best": {str(m): se[j] for j, m in enumerate(GRID)},
    }


boot = np.random.default_rng(20261116)
res["interval"] = {k: interval(search[k]) for k in ("pen_text_nodup", "dup_nopen")}
for k, v in res["interval"].items():
    print(k, json.dumps(v), flush=True)
json.dump(res, open(OUT + "u2_scatter.json", "w"), indent=1, default=float)
