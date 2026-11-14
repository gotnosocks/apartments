"""S15, part 1: L1 reading `income_restricted_v2` in place of `income_restricted`,
emulated on L1's held-out ads of the latest split from its saved draws.

For each of L1's 272 kept draws the script takes a held-out ad's location `pred_loc`,
subtracts that draw's coefficient for the old flag where the old flag is set and adds a
shift delta where the new flag is set. The unit sd, the noise scale and nu stay as drawn.
Each ad's log predictive density is rescored on the 48-node grid of `common.Draws`, and its
gain is the rescored density less L1's on the same grid. Ads neither flag marks gain 0.

delta runs over a grid from -0.30 to +0.05. The buildings fall in two halves by the hash of
`common.heldout`; each half takes the delta with the largest total gain over the other half's
marked ads, and the gains of both halves add up to the screen's gain.

SEs are clustered by building over all held-out ads: per-ad gains, zeros included, are
demeaned over the held-out ads, summed by building, and se = sqrt(G / (G - 1) * sum(t^2)).
A part of the split keeps its own ads' gains and zeros elsewhere. For comparison with S14,
`se_within` demeans over the part's own ads instead.

The script also counts the rows, units and buildings each flag marks, and the shares of the
new flag's ads whose unit or building has an ad the new flag leaves unmarked. Results go to
`OUT/f1_screen.json`, and the per-ad table of marked held-out ads to `OUT/f1_heldout.parquet`.

    systemd-run --user --scope -q -p MemoryMax=3G python f1_screen.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

COPY = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags"
)
OUT = Path("/data1/apartments/tmp/income-flag-2026-11-14")
OUT.mkdir(parents=True, exist_ok=True)
GRID = np.round(np.arange(-0.30, 0.0501, 0.01), 2)


def se_sum(x, b):
    """Building-clustered SE of sum(x), with x demeaned over all its entries."""
    x = np.asarray(x, float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    g = len(t)
    return float(np.sqrt(g / (g - 1) * (t**2).sum()))


def lpd(dr, idx, shift):
    """Log predictive density of the held-out ads `idx` with each draw's location moved
    by `shift` (draws, len(idx)), on `common.Draws`'s grid."""
    s = (dr.sig[:, dr.grp[idx]] * dr.fac[:, dr.ph[idx]]).astype(np.float32)
    loc = dr.loc[:, idx] + shift.astype(np.float32)
    usd = dr.usd[:, idx]
    var = usd[:, :, None] ** 2 + (s**2)[:, :, None] * dr.ilam
    dev = (dr.y[idx][None, :] - loc)[:, :, None]
    lp = dr.logw - 0.5 * (np.log(var) + dev * dev / var)
    m = lp.max(axis=2, keepdims=True)
    lp = (m[:, :, 0] + np.log(np.exp(lp - m).sum(axis=2))).astype(np.float64)
    n = lp.shape[0]
    return np.logaddexp.reduce(lp, axis=0) - np.log(n) - 0.5 * np.log(2 * np.pi)


d = pd.read_parquet(
    COPY / "rows.parquet",
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "price_at",
        "latest_ask",
        "description_known",
        "income_restricted",
        "income_restricted_v2",
    ],
)
d["listing_id"] = d.listing_id.astype(str)
a = np.load(c.RUN + "pred_scores.npz", allow_pickle=True)
d["held"] = a["heldout"]
d["ukey"] = np.where(
    d.unit_id.isna(),
    "row:" + d.listing_id,
    d.building.astype(str) + "|" + d.unit_id.astype(str),
)
d["old"] = d.income_restricted.astype(bool)
d["new"] = d.income_restricted_v2.astype(bool)
h = c.heldout(d)
res = {"rows": len(d), "heldout": len(h)}

# Counts of rows, units and buildings under each flag.
tr = d[~d.held]
res["counts"] = {
    f"{flag} {part}": {
        "ads": int(x[flag].sum()),
        "units": int(x.ukey[x[flag]].nunique()),
        "buildings": int(x.building[x[flag]].nunique()),
    }
    for flag in ("old", "new")
    for part, x in (("training", tr), ("heldout", h), ("all", d))
}
for part, x in (("training", tr), ("heldout", h)):
    for name, on in (
        ("both", x.old & x.new),
        ("old only", x.old & ~x.new),
        ("new only", ~x.old & x.new),
    ):
        res["counts"][f"{name} {part}"] = {
            "ads": int(on.sum()),
            "units": int(x.ukey[on].nunique()),
            "buildings": int(x.building[on].nunique()),
        }

# Mixed units and buildings under the new flag.
unmarked = ~d.new
known_unmarked = unmarked & d.description_known.astype(bool)
tr_un = tr[~tr.new]
tr_kn = tr_un[tr_un.description_known.astype(bool)]
hn = h[h.new]
mixed = {
    "heldout": {
        "ads": len(hn),
        "unit_has_unmarked_training": float(hn.ukey.isin(tr_un.ukey).mean()),
        "unit_has_unmarked_training_known": float(hn.ukey.isin(tr_kn.ukey).mean()),
        "unit_has_training": float(hn.ukey.isin(tr.ukey).mean()),
        "building_has_unmarked_training": float(
            hn.building.isin(tr_un.building).mean()
        ),
    }
}
# For a training row, any other row of its unit or building counts.
un_u = d.groupby("ukey").new.agg(["size", "sum"])
un_b = d.groupby("building").new.agg(["size", "sum"])
kn_u = d[known_unmarked].groupby("ukey").size()
tn = tr[tr.new]
others_unmarked_u = (un_u["size"] - un_u["sum"]).reindex(tn.ukey).to_numpy()
others_unmarked_b = (un_b["size"] - un_b["sum"]).reindex(tn.building).to_numpy()
mixed["training"] = {
    "ads": len(tn),
    "unit_has_unmarked": float((others_unmarked_u > 0).mean()),
    "unit_has_unmarked_known": float(
        (kn_u.reindex(tn.ukey).fillna(0).to_numpy() > 0).mean()
    ),
    "unit_has_other_row": float((un_u["size"].reindex(tn.ukey).to_numpy() > 1).mean()),
    "building_has_unmarked": float((others_unmarked_b > 0).mean()),
}
res["mixed"] = mixed

# Each held-out ad's unit history under the new flag: its training rows all marked, some, none.
tr_u = tr.groupby("ukey").new.agg(["size", "sum"])
hu = tr_u.reindex(h.ukey)
n_tr = hu["size"].fillna(0).to_numpy()
n_mk = hu["sum"].fillna(0).to_numpy()
h["history"] = np.select(
    [n_tr == 0, n_mk == n_tr, n_mk > 0], ["no training row", "all", "some"], "none"
)
h["tr_rows"], h["tr_marked"] = n_tr, n_mk

# The emulation.
post = np.load(c.RUN + "posterior.npz", allow_pickle=True)
names = list(post["names"])
beta = post["kept/beta"][..., names.index("flag:income_restricted")].reshape(-1)
res["old_coefficient"] = {
    "draws": int(beta.size),
    "mean": float(beta.mean()),
    "sd": float(beta.std(ddof=1)),
    "q05": float(np.quantile(beta, 0.05)),
    "q95": float(np.quantile(beta, 0.95)),
}
dr = c.Draws()
assert dr.loc.shape == (beta.size, len(h))
old, new = h.old.to_numpy(), h.new.to_numpy()
idx = np.flatnonzero(old | new)
o, n_ = old[idx].astype(np.float64), new[idx].astype(np.float64)
base = lpd(dr, idx, np.zeros((beta.size, len(idx))))
gains = {}
for dl in GRID:
    shift = -beta[:, None] * o[None, :] + dl * n_[None, :]
    gains[float(dl)] = lpd(dr, idx, shift) - base
fold = h.fold.to_numpy()[idx]
picked, per = {}, np.zeros(len(idx))
for f in (0, 1):
    tot = {dl: float(g[fold != f].sum()) for dl, g in gains.items()}
    picked[f] = max(tot, key=tot.get)
    per[fold == f] = gains[picked[f]][fold == f]
grid_total = {dl: float(g.sum()) for dl, g in gains.items()}
res["delta_by_half"] = {str(f): v for f, v in picked.items()}
res["delta_all_ads"] = max(grid_total, key=grid_total.get)
res["grid_total"] = {f"{k:+.2f}": v for k, v in grid_total.items()}
res["halves"] = {
    str(f): {"ads": int((fold == f).sum()), "gain": float(per[fold == f].sum())}
    for f in (0, 1)
}

g_all = np.zeros(len(h))
g_all[idx] = per
h["gain"] = g_all
b = h.building.to_numpy()
parts = {
    "all": old | new,
    "both": old & new,
    "old only": old & ~new,
    "new only": ~old & new,
    "new flag": new,
}
for hist in ("all", "some", "none", "no training row"):
    parts[f"new flag, history {hist}"] = new & (h.history.to_numpy() == hist)
    parts[f"new only, history {hist}"] = ~old & new & (h.history.to_numpy() == hist)
res["gain"] = {}
for name, on in parts.items():
    x = np.where(on, g_all, 0.0)
    within = g_all[on]
    res["gain"][name] = {
        "ads": int(on.sum()),
        "buildings": int(pd.Series(b[on]).nunique()),
        "gain": float(x.sum()),
        "se": se_sum(x, b),
        "se_within": se_sum(within, b[on]) if on.sum() > 1 else None,
        "mean_gap": float(h.gap.to_numpy()[on].mean()) if on.any() else None,
    }
# Each part's gain at the delta picked on all ads, for reference.
best = gains[res["delta_all_ads"]]
res["gain_at_delta_all_ads"] = {
    name: float(best[on[idx]].sum()) for name, on in parts.items()
}
# Each part's total over the grid, its best delta in sample, and the spread of its gaps.
gap = h.gap.to_numpy()
res["part_grid"] = {}
for name in ("both", "new only", "new flag"):
    on = parts[name][idx]
    tot = {dl: float(g[on].sum()) for dl, g in gains.items()}
    x = gap[idx][on]
    res["part_grid"][name] = {
        "best_delta": max(tot, key=tot.get),
        "best_total": max(tot.values()),
        "total": {f"{k:+.2f}": v for k, v in tot.items()},
        "gap_quantiles": {
            str(q): float(np.quantile(x, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)
        },
        "share_gap_below": {
            str(t): float((x < t).mean()) for t in (-0.5, -0.3, -0.2, -0.1)
        },
        "share_in80": float(h.in80.to_numpy()[idx][on].mean()),
    }
    print(name, json.dumps(res["part_grid"][name]["gap_quantiles"]), flush=True)
for name, v in res["gain"].items():
    print(f"{name}: {json.dumps(v)}", flush=True)
print("delta by half", picked, "on all ads", res["delta_all_ads"])
print("old coefficient", res["old_coefficient"])
print(json.dumps(res["counts"], indent=1))
print(json.dumps(res["mixed"], indent=1))
json.dump(res, open(OUT / "f1_screen.json", "w"), indent=1)
h.loc[old | new].to_parquet(OUT / "f1_heldout.parquet")
