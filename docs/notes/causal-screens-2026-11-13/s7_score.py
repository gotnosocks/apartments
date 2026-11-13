"""S7, part 2: do duplex apartments and stated outdoor sizes ask more than L1 predicts?

L1 has no duplex column, so for a unit with earlier ads its unit level carries the duplex,
and a duplex should show in the gap mainly where the held-out ad is the unit's first. The script
splits held-out ads by that and reads:

1. the gap and the within-building gap of ads matched by `s7_text.py`'s duplex pattern
   against the rest, with and without a stated size;
2. a cross-fitted shift by duplex and first-ad status, rescored with L1's predictive;
3. the same contrast on the new units of the backtest j9;
4. for ads with the private outdoor flag, the within-building gap by the stated outdoor size.

With the readers' labels in `s7_labels.parquet`, the script also scores the pattern's precision and
recall against them."""

import json
import os

import numpy as np
import pandas as pd

import common as c

tx = pd.read_parquet(c.OUT + "s7_text.parquet")
tx["listing_id"] = tx.listing_id.astype(str)
fl = pd.read_parquet(
    "/data1/apartments/tmp/outlier-sprint/qual/flags.parquet",
    columns=["listing_id", "private_outdoor"],
)
fl["listing_id"] = fl.listing_id.astype(str)
d = c.rows()
d["listing_id"] = d.listing_id.astype(str)
d = d.merge(tx[["listing_id", "dup_unit", "out_sqft"]], on="listing_id", how="left")
d = d.merge(fl, on="listing_id", how="left")
d = d.sort_values(["ukey", "priced", "listing_id"])
d["first"] = ~d.ukey.eq(d.ukey.shift())
d = d.sort_index()
h = c.heldout(d)
h["dup"] = h.dup_unit.fillna(False).astype(bool)
h["sized"] = h.square_feet.notna()
h["wgap"] = c.within(h.gap, h.building)
bld = h.building.to_numpy()
res = {
    "n": len(h),
    "dup_share": float(h.dup.mean()),
    "first_share": float(h["first"].mean()),
}


def contrast(x, col):
    out = {}
    for name, g in (("first", x[x["first"]]), ("repeat", x[~x["first"]])):
        for sz, gg in (("all", g), ("sized", g[g.sized]), ("unsized", g[~g.sized])):
            on = gg[col].to_numpy()
            if on.sum() < 30:
                continue
            b = gg.building.to_numpy()
            out[f"{name}_{sz}"] = {
                "n_on": int(on.sum()),
                "gap_on": float(gg.gap[on].mean()),
                "diff": c.cluster_mean_diff(gg.gap.to_numpy(), on, b),
                "within_diff": c.cluster_mean_diff(gg.wgap.to_numpy(), on, b),
            }
    return out


res["dup"] = contrast(h, "dup")
print(json.dumps(res["dup"]), flush=True)

dr = c.Draws()
key = h.dup.astype(str) + "|" + h["first"].astype(str)
dl, k = c.crossfit_shift(
    h.gap.to_numpy(), key.to_numpy(), h.fold.to_numpy(), c.subfold(h.building)
)
e = dr.gain(np.arange(len(h)), delta=dl)
# counted over a first-ad or repeat shift fitted the same way
e0 = dr.gain(
    np.arange(len(h)),
    delta=c.crossfit_shift(
        h.gap.to_numpy(),
        h["first"].astype(str).to_numpy(),
        h.fold.to_numpy(),
        c.subfold(h.building),
    )[0],
)
inc = e - e0
on = h.dup.to_numpy()
res["shift"] = {
    "elpd_gain": float(e.sum()),
    "over_first": float(inc.sum()),
    "se": c.cluster_se(inc, bld),
    "gain_dup": float(inc[on].sum()),
    "gain_dup_se": c.cluster_se(inc[on], bld[on]),
    "k": k,
}
print(json.dumps(res["shift"]), flush=True)
del dr

# outdoor size among ads with the private outdoor flag
po = h[h.private_outdoor.fillna(False).astype(bool)].copy()
po["size_bin"] = pd.cut(
    po.out_sqft, [0, 100, 300, 700, 5000], labels=["<100", "100-300", "300-700", "700+"]
)
po["size_bin"] = po.size_bin.astype(str).replace("nan", "unstated")
po["wgap"] = c.within(po.gap, po.building)
rows = []
for (fst, sb), g in po.groupby(["first", "size_bin"]):
    rows.append(
        {
            "first": bool(fst),
            "size": sb,
            "n": len(g),
            "gap": float(g.gap.mean()),
            "se": c.cluster_se(g.gap.to_numpy(), g.building.to_numpy()) / len(g),
            "wgap": float(g.wgap.mean()),
        }
    )
res["outdoor"] = rows
st = po[po.out_sqft.notna()]
res["outdoor_slope_log2"] = {
    name: c.wls_slope(g.wgap, np.log2(g.out_sqft), g.building)[:2] + (len(g),)
    for name, g in (("first", st[st["first"]]), ("repeat", st[~st["first"]]))
    if len(g) >= 30
}
print(pd.DataFrame(rows).to_string(), json.dumps(res["outdoor_slope_log2"]), flush=True)

# the backtest j9's new units
J9 = "/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9/"
r9 = json.load(open(J9 + "result.json"))
z9 = np.load(J9 + "posterior.npz")
d9 = pd.read_parquet(
    r9["dataset"] + "/rows.parquet", columns=["listing_id", "building", "latest_ask"]
)
h9 = d9[z9["heldout"]].reset_index(drop=True)
y9 = z9["kept/pred_y"]
assert np.allclose(np.log(h9.latest_ask.to_numpy(float)), y9, atol=1e-6)
h9["gap"] = y9 - z9["kept/pred_loc"].reshape(-1, len(y9)).mean(axis=0)
h9["listing_id"] = h9.listing_id.astype(str)
h9 = h9.merge(tx[["listing_id", "dup_unit"]], on="listing_id", how="left")
on9 = h9.dup_unit.fillna(False).astype(bool).to_numpy()
w9 = c.within(h9.gap, h9.building)
res["j9"] = {
    "n": len(h9),
    "n_dup": int(on9.sum()),
    "diff": c.cluster_mean_diff(h9.gap.to_numpy(), on9, h9.building.to_numpy()),
    "within_diff": c.cluster_mean_diff(w9, on9, h9.building.to_numpy()),
}
print("j9", json.dumps(res["j9"]), flush=True)

lab = c.OUT + "s7_labels.parquet"
if os.path.exists(lab):
    lb = pd.read_parquet(lab).merge(
        pd.read_parquet(c.OUT + "s7_picks.parquet"), on="read_id"
    )
    lb = lb.merge(
        tx[["listing_id", "dup_unit", "out_sqft"]].rename(
            columns={"out_sqft": "parsed"}
        ),
        on="listing_id",
    )
    dl_ = lb[lb["sample"] != "outdoor_size"]
    tp = (dl_.dup_unit & dl_.duplex_unit).sum()
    res["readers"] = {
        "precision": float(tp / dl_.dup_unit.sum()),
        # recall from the unmatched draws, weighted back to their shares of all ads
        "unmatched_duplex_random": float(
            dl_[dl_["sample"] == "unmatched_random"].duplex_unit.mean()
        ),
        "unmatched_duplex_weak": float(
            dl_[dl_["sample"] == "unmatched_weak"].duplex_unit.mean()
        ),
    }
    # recall: matched duplexes over those plus the duplexes the readers find in each
    # unmatched stratum, scaled to the stratum's count among the ads the draws came from
    base = tx[tx.listing_id.isin(set(d.listing_id)) & (tx.desc_len > 80)]
    rest = ~base.dup_unit & ~base.dup
    rr = res["readers"]
    found = rr["precision"] * base.dup_unit.sum()
    missed = (
        rr["unmatched_duplex_random"] * (rest & ~base.weak).sum()
        + rr["unmatched_duplex_weak"] * (rest & base.weak).sum()
    )
    rr["recall"] = float(found / (found + missed))
    o = lb[lb["sample"] == "outdoor_size"]
    res["readers"]["outdoor_size_agrees"] = float(
        (np.abs(o.outdoor_sqft - o.parsed) <= 0.05 * o.parsed).mean()
    )
    print("readers", json.dumps(res["readers"]), flush=True)
json.dump(res, open(c.OUT + "s7.json", "w"), indent=1, default=float)
